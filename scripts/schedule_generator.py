"""
schedule_generator.py
─────────────────────
Builds the three day-to-day pages from the Google Sheet:

  docs/index.html     today (rotation, meals, bookings), then the next six days
  docs/weekly.html    this week: numbers, occupancy, room grid, sources
  docs/upcoming.html  arrivals for the next eight weeks

GitHub Actions runs it and publishes docs/.

    python schedule_generator.py
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import date, timedelta

import clock
import pages
from auth import get_worksheet
from bookings import Booking, load_bookings
from config import PREPAID_SOURCES, ROOMS, SPLIT_PAYMENT_SOURCES

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
log = logging.getLogger(__name__)

ROOM_LOOKS = {
    "Laurasie de la Cour": {"emoji": "🐴", "bg": "#F5E0E3", "color": "#7A3040"},  # rose
    "Tibert de la Cour":   {"emoji": "🦌", "bg": "#FAE8DC", "color": "#7A3F2E"},  # warm orange
    "Léon de la Cour":     {"emoji": "🦚", "bg": "#DDE8E5", "color": "#2A4A44"},  # blue-green
    "Odette de la Cour":   {"emoji": "🦢", "bg": "#F5F2EE", "color": "#4A3828"},  # off-white
}
NEUTRAL_LOOK = {"emoji": "🛏", "bg": "#F1EFE7", "color": "#4A5D4E"}


def run():
    bookings = [b for b in load_bookings(get_worksheet()) if not b.is_cancelled]
    today = clock.today()
    monday = today - timedelta(days=today.weekday())

    pages.write("index.html", daily_page(bookings, today))
    pages.write("weekly.html", weekly_page(bookings, monday))
    pages.write("upcoming.html", upcoming_page(bookings, today))


# ── Pages ─────────────────────────────────────────────────────────────────────

def daily_page(bookings: list[Booking], today: date) -> str:
    here_today = [b for b in bookings if b.is_present_on(today)]
    arriving = [b for b in here_today if b.arrival == today]
    leaving = [b for b in here_today if b.departure == today and b.arrival != today]
    staying = [b for b in here_today if b.arrival != today and b.departure != today]

    return pages.render(
        "index.html",
        **CARD_HELPERS,
        today=today,
        turnover_rooms=sorted(rooms_of(arriving) & rooms_of(leaving)),
        meals=meals_to_prepare(here_today, today),
        today_groups=[
            ("⬆ Arrivées", "arrival", arriving),
            ("⬇ Départs", "departure", leaving),
            ("🏠 En séjour", "staying", staying),
        ],
        next_days=[next_day(bookings, today, offset) for offset in range(1, 7)],
    )


def weekly_page(bookings: list[Booking], monday: date) -> str:
    sunday = monday + timedelta(days=6)
    week_days = [monday + timedelta(days=i) for i in range(7)]
    arriving = [b for b in bookings if b.arrival and monday <= b.arrival <= sunday]
    leaving = [b for b in bookings if b.departure and monday <= b.departure <= sunday]
    returning = [b for b in arriving if b.is_repeat_guest]

    return pages.render(
        "weekly.html",
        week_start=monday,
        week_end=sunday,
        week_days=week_days,
        stats=[
            (len(arriving), "Arrivées cette semaine"),
            (len(leaving), "Départs cette semaine"),
            (f"{sum(b.amount for b in arriving):,.0f} €", "Revenus estimés"),
            (len(returning), "Clients Fidèles"),
            (sum(1 for b in arriving if b.has_table_dhotes), "🍽️ Table d'hôtes"),
            (sum(1 for b in arriving if b.has_breakfast), "🥐 Petit-déjeuner"),
        ],
        occupancy=[occupancy(bookings, day) for day in week_days],
        room_grid=[room_grid_row(bookings, room, week_days) for room in ROOMS],
        sources=Counter(b.source for b in arriving).most_common(),
        repeat_guests=returning,
    )


def upcoming_page(bookings: list[Booking], today: date) -> str:
    days_to_next_monday = (7 - today.weekday()) % 7 or 7
    first_monday = today + timedelta(days=days_to_next_monday)
    weeks = []
    for i in range(8):
        start = first_monday + timedelta(weeks=i)
        end = start + timedelta(days=6)
        weeks.append({
            "start": start,
            "end": end,
            "arrivals": [b for b in bookings if b.arrival and start <= b.arrival <= end],
        })
    return pages.render("upcoming.html", **CARD_HELPERS, weeks=weeks)


# ── Daily page pieces ─────────────────────────────────────────────────────────

def rooms_of(bookings: list[Booking]) -> set:
    return {room for b in bookings for room in b.rooms}


def meals_to_prepare(here_today: list[Booking], today: date) -> list[dict]:
    """
    Covers for tonight's table d'hôtes and this morning's breakfast.
    Guests leaving today skip dinner; room guests arriving today skip breakfast.
    """
    today_text = today.strftime("%d/%m/%Y")
    dinner = [
        b for b in here_today
        if b.has_table_dhotes
        and (not b.table_dhotes_dates or today_text in b.table_dhotes_dates)
        and not (b.departure == today and b.arrival != today)
    ]
    breakfast = [
        b for b in here_today
        if b.has_breakfast and not (b.rooms and b.arrival == today)
    ]
    meals = []
    for label, guests in (("🍽️ Table d'hôtes ce soir", dinner), ("🥐 Petit-déjeuner ce matin", breakfast)):
        if guests:
            meals.append({
                "label": label,
                "covers": sum(b.covers for b in guests),
                "who": " + ".join(f"{b.guest_name or '?'} ({b.covers})" for b in guests),
            })
    return meals


def next_day(bookings: list[Booking], today: date, offset: int) -> dict:
    day = today + timedelta(days=offset)
    return {
        "date": day,
        "label": {1: "⬆ Demain", 2: "⬆ Après-demain"}.get(offset, ""),
        "arrivals": [b for b in bookings if b.arrival == day],
        "departures": [b for b in bookings if b.departure == day and b.arrival != day],
    }


# ── Weekly page pieces ────────────────────────────────────────────────────────

def occupancy(bookings: list[Booking], day: date) -> dict:
    """How many rooms are slept in on the night starting `day`."""
    taken = rooms_of([b for b in bookings if b.sleeps_here_on(day)])
    return {
        "date": day,
        "rooms_taken": len(taken),
        "rooms_total": len(ROOMS),
        "percent": int(len(taken) / len(ROOMS) * 100),
    }


def room_grid_row(bookings: list[Booking], room: str, week_days: list[date]) -> dict:
    """One room across the week: the guest's first name each night, or free."""
    cells = []
    previous_guest = None
    for day in week_days:
        guest = next((first_name(b) for b in bookings
                      if b.sleeps_here_on(day) and room in b.rooms), None)
        cells.append({"guest": guest, "new_guest": guest is not None and guest != previous_guest})
        previous_guest = guest
    return {"name": room.replace(" de la Cour", ""), "look": ROOM_LOOKS.get(room, NEUTRAL_LOOK),
            "cells": cells}


def first_name(booking: Booking) -> str:
    return (booking.guest_name or "?").split()[0]


# ── Booking card helpers (used by templates/_booking_card.html) ───────────────

def payment_tags(booking: Booking) -> list[tuple[str, str]]:
    """(css class, text) of the payment pills. Massages are paid to the masseuse."""
    if booking.source in PREPAID_SOURCES:
        if booking.has_table_dhotes:
            return [("paid", "✅ Chambre payée"), ("to-pay", "💳 Table d'hôtes à régler")]
        return [("paid", "✅ Payé")]
    if booking.source in SPLIT_PAYMENT_SOURCES:
        half = booking.amount / 2
        return [("half-paid", "💳 50% restant" + (f" — {half:,.0f} €" if half > 0 else ""))]
    if booking.source:
        return [("to-pay", "💳 À régler")]
    return []


def room_look(rooms: list[str]) -> dict:
    return ROOM_LOOKS.get(rooms[0], NEUTRAL_LOOK) if len(rooms) == 1 else NEUTRAL_LOOK


CARD_HELPERS = {"payment_tags": payment_tags, "room_look": room_look}


if __name__ == "__main__":
    run()
