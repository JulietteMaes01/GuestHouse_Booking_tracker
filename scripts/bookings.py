"""
Bookings as the pages see them: one Booking per Sheet row, with real dates,
yes/no fields and numbers instead of raw cell text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

import sheet
from config import BREAKFAST_AUTO_SOURCES, COMMISSIONS, SOURCE_ALIASES

SHEET_DATE_FORMAT = "%d/%m/%Y"
YES_WORDS = ("true", "1", "yes", "oui")

# Notes can start with the table d'hôtes nights, e.g. "[TD: 12/08/2026, 13/08/2026] …"
TABLE_DHOTES_DATES_TAG = re.compile(r"\[TD:\s*([^\]]+)\]\s*")


def is_yes(cell) -> bool:
    return str(cell).strip().lower() in YES_WORDS


def parse_date(cell) -> date | None:
    try:
        return datetime.strptime(str(cell).strip(), SHEET_DATE_FORMAT).date()
    except ValueError:
        return None


def parse_number(cell) -> float | None:
    """'226,25' or '226.25' → 226.25; None when the cell is empty or not a number."""
    try:
        return float(str(cell).strip().replace(",", "."))
    except ValueError:
        return None


@dataclass
class Booking:
    reference: str
    source: str
    status: str
    booked_on: date | None
    arrival: date | None
    departure: date | None
    rooms: list
    guest_name: str
    nationality: str
    amount_text: str        # as typed in the Sheet, shown on the cards
    nights_text: str
    visit_count_text: str
    notes: str
    is_repeat_guest: bool
    has_table_dhotes: bool
    breakfast_booked: bool  # ticked explicitly; see has_breakfast
    guest_count: int        # 0 when not filled in
    massage: str
    cabin: str              # cabin the dishes are delivered to; '' for farm bookings
    dishes: str             # dishes to deliver, one per line

    @classmethod
    def from_row(cls, row: dict) -> Booking:
        source = str(row.get("booking_source", "")).strip()
        guest_count = parse_number(row.get("guest_count", "")) or 0
        return cls(
            reference=str(row.get("reference", "")).strip(),
            source=SOURCE_ALIASES.get(source, source),
            status=str(row.get("status", "")).strip(),
            booked_on=parse_date(row.get("booking_date", "")),
            arrival=parse_date(row.get("arrival_date", "")),
            departure=parse_date(row.get("departure_date", "")),
            rooms=[str(row.get(f"room{i}", "")).strip() for i in range(1, 5)
                   if str(row.get(f"room{i}", "")).strip()],
            guest_name=str(row.get("guest_name", "")),
            nationality=str(row.get("nationality", "")),
            amount_text=str(row.get("amount", "")),
            nights_text=str(row.get("nights", "")),
            visit_count_text=str(row.get("visit_count", "")),
            notes=str(row.get("notes", "")),
            is_repeat_guest=is_yes(row.get("repeat_guest", "")),
            has_table_dhotes=is_yes(row.get("table_dhotes", "")),
            breakfast_booked=is_yes(row.get("breakfast", "")),
            guest_count=max(0, int(guest_count)),
            massage=str(row.get("massage", "")).strip(),
            cabin=str(row.get("cabane", "")).strip(),
            dishes=str(row.get("plats", "")).strip(),
        )

    # ── Status ────────────────────────────────────────────────────────────────

    @property
    def is_cancelled(self) -> bool:
        return self.status.lower() == "cancelled"

    @property
    def is_meal_only(self) -> bool:
        return not self.rooms

    @property
    def is_cabin_order(self) -> bool:
        """Dishes delivered to a cabin, not a stay or a meal at the farm."""
        return bool(self.cabin)

    # ── Dates ─────────────────────────────────────────────────────────────────

    def is_present_on(self, day: date) -> bool:
        """Here at some point that day, arrival and departure days included."""
        return bool(self.arrival and self.departure and self.arrival <= day <= self.departure)

    def sleeps_here_on(self, day: date) -> bool:
        """Spends the night starting that day here."""
        return bool(self.arrival and self.departure and self.arrival <= day < self.departure)

    @property
    def nights(self) -> float:
        nights = parse_number(self.nights_text or 0)
        if nights is not None:
            return nights
        return (self.departure - self.arrival).days if self.departure and self.arrival else 0

    # ── Money ─────────────────────────────────────────────────────────────────

    @property
    def amount(self) -> float:
        return parse_number(self.amount_text) or 0.0

    @property
    def net_amount(self) -> float:
        """Amount after the booking platform's commission."""
        return round(self.amount * (1 - COMMISSIONS.get(self.source, 0.0)), 2)

    # ── Meals ─────────────────────────────────────────────────────────────────

    @property
    def has_breakfast(self) -> bool:
        return self.breakfast_booked or self.source in BREAKFAST_AUTO_SOURCES

    @property
    def table_dhotes_dates(self) -> list:
        """Specific dinner nights ('dd/mm/yyyy') from the notes; empty means every night."""
        match = TABLE_DHOTES_DATES_TAG.search(self.notes)
        return [d.strip() for d in match.group(1).split(",") if d.strip()] if match else []

    @property
    def notes_without_dates_tag(self) -> str:
        return TABLE_DHOTES_DATES_TAG.sub("", self.notes).strip()

    @property
    def covers(self) -> int:
        """People to cook for: the guest count, else 2 for a room and 1 for a meal."""
        return self.guest_count or (1 if self.is_meal_only else 2)


def load_bookings(worksheet) -> list[Booking]:
    """Every row of the Sheet, in Sheet order, cancelled ones included."""
    _, rows = sheet.read_rows(worksheet)
    return [Booking.from_row(row) for row in rows]
