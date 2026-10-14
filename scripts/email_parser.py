"""
email_parser.py
───────────────
Copies elloha booking emails from the contact@lafermedelacour.be inbox
into the Google Sheet:

  • New booking   → new row
  • Cancellation  → existing row gets status Cancelled
  • Modification  → existing row gets the new dates / amount

Gmail message ids already handled are kept in processed_emails.json, so an
email is never applied twice.

    python email_parser.py
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import traceback
from datetime import datetime

from bs4 import BeautifulSoup

import sheet
from auth import get_gmail_service, get_worksheet
from config import COLUMNS, ELLOHA_SENDER, ROOMS
from guests import detect_repeat_guest, phone_to_nationality

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
log = logging.getLogger(__name__)

PROCESSED_IDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "processed_emails.json")


def run():
    log.info("Connecting to Gmail and Google Sheets …")
    gmail = get_gmail_service()
    bookings_sheet = SheetMirror(get_worksheet())
    processed_ids = load_processed_ids()

    emails = read_new_emails(gmail, processed_ids)
    # New bookings first, so cancellations and modifications find their row.
    emails.sort(key=lambda email: email[1]["email_type"] != "Booking")

    counts = {"added": 0, "updated": 0, "skipped": 0, "errors": 0}
    for msg_id, parsed in emails:
        try:
            outcome = apply_email(parsed, bookings_sheet, gmail)
            counts[outcome] += 1
            processed_ids.add(msg_id)
        except Exception as exc:
            counts["errors"] += 1
            log.error(f"  ✗ Error applying {msg_id}: {exc}\n" + traceback.format_exc())

    save_processed_ids(processed_ids)
    log.info(f"Done — {counts['added']} added, {counts['updated']} updated, "
             f"{counts['skipped']} skipped, {counts['errors']} errors")


# ── Processed email ids ───────────────────────────────────────────────────────

def load_processed_ids() -> set:
    if not os.path.exists(PROCESSED_IDS_FILE):
        return set()
    with open(PROCESSED_IDS_FILE) as fh:
        return set(json.load(fh))


def save_processed_ids(ids: set) -> None:
    with open(PROCESSED_IDS_FILE, "w") as fh:
        json.dump(sorted(ids), fh, indent=2)


def read_new_emails(gmail, processed_ids: set) -> list[tuple[str, dict]]:
    """(Gmail id, parsed email) for every elloha email not handled yet."""
    stubs = gmail.users().messages().list(
        userId="me", q=f"from:{ELLOHA_SENDER}", maxResults=500).execute().get("messages", [])
    log.info(f"Found {len(stubs)} elloha email(s) in inbox")

    emails, skipped, errors = [], 0, 0
    for stub in stubs:
        if stub["id"] in processed_ids:
            skipped += 1
            continue
        try:
            parsed = read_email(gmail, stub["id"])
        except Exception as exc:
            errors += 1
            log.error(f"  ✗ Error reading message {stub['id']}: {exc}\n" + traceback.format_exc())
            continue
        if parsed is None:
            skipped += 1
        else:
            emails.append((stub["id"], parsed))

    log.info(f"Fetched — {len(emails)} new email(s) to apply, {skipped} skipped, {errors} errors")
    return emails


def read_email(gmail, msg_id: str) -> dict | None:
    """Download one email and parse it; None if it isn't a booking email."""
    msg = gmail.users().messages().get(userId="me", id=msg_id, format="full").execute()
    headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
    return parse_email(
        subject=str(headers.get("Subject", "")),
        body=get_email_text(msg["payload"]),
        received_ts=int(msg.get("internalDate", 0)),
        from_header=headers.get("From", ""),
    )


def find_original_booking(gmail, ref: str) -> dict | None:
    """Search Gmail for the booking email of a reference (when a cancellation arrives first)."""
    stubs = gmail.users().messages().list(
        userId="me", q=f"from:{ELLOHA_SENDER} {ref}", maxResults=10).execute().get("messages", [])
    for stub in stubs:
        try:
            parsed = read_email(gmail, stub["id"])
        except Exception as exc:
            log.error(f"    ✗ Error reading candidate {stub['id']}: {exc}")
            continue
        if parsed and parsed["email_type"] == "Booking" and parsed["reference"] == ref:
            return parsed
    return None


# ── Gmail helpers ─────────────────────────────────────────────────────────────

def _decode_part(data: str) -> str:
    return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")


def get_email_text(payload: dict) -> str:
    """
    Recursively extract readable text from an email payload.
    Prefers the HTML part (richer structure for regex) converted to plain text.
    """
    mime = payload.get("mimeType", "")

    if mime.startswith("multipart/"):
        html_text = plain_text = ""
        for part in payload.get("parts", []):
            result = get_email_text(part)
            if result:
                if "html" in part.get("mimeType", ""):
                    html_text = result
                else:
                    plain_text = result
        return html_text or plain_text

    data = payload.get("body", {}).get("data", "")
    if not data:
        return ""

    content = _decode_part(data)
    if "html" in mime:
        soup = BeautifulSoup(content, "html.parser")
        return soup.get_text(separator="\n", strip=True)
    return content


# ── Parsing helpers ───────────────────────────────────────────────────────────

def _first_group(pattern: str, text: str, flags: int = 0) -> str:
    """Return the first capture group of pattern in text, or empty string."""
    if not isinstance(text, str):
        text = str(text or "")
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else ""


def _parse_amount(text: str) -> float:
    """
    Extract a euro amount from text.
    Handles both French (226,25 €) and English (226.25 €) formats,
    and multiple label styles (Montant total / Montant de la Réservation).
    """
    patterns = [
        r"Montant total\s*([\d\s\u00a0]+[,\.]\d{2})\s*\u20ac",
        r"Montant de la R[ée]servation\s*:\s*([\d\s\u00a0]+[,\.]\d{2})\s*\u20ac",
        r"([\d\s\u00a0]+[,\.]\d{2})\s*\u20ac",   # fallback: any euro amount
    ]
    for pat in patterns:
        raw = _first_group(pat, text)
        if raw:
            try:
                return float(
                    raw.replace("\u00a0", "").replace(" ", "").replace(",", ".")
                )
            except ValueError:
                continue
    return 0.0


def _parse_guest_name(text: str) -> str:
    """Handle both '* Nom : ...' and '* Nom du Client: ...' formats."""
    return _first_group(
        r"\*?\s*Nom(?:\s+du\s+Client)?\s*:\s*(.+?)(?:\n|$)", text
    )


def parse_email(subject: str, body: str, received_ts: int, from_header: str = "") -> dict | None:
    """
    Parse a single elloha email.
    Returns a dict describing the event, or None if unrecognisable.

    For Cancellation / Modification the dict contains only the fields
    that need to be updated on an existing row (+ 'email_type' and 'reference').
    """
    if not isinstance(body, str):
        body = str(body or "")

    subject_lower = subject.lower()

    # ── Email type ────────────────────────────────────────────────────────────
    if "annulation" in subject_lower or "cancellation" in subject_lower:
        email_type = "Cancellation"
    elif "modification" in subject_lower:
        email_type = "Modification"
    elif "r\u00e9servation" in subject_lower or "reservation" in subject_lower:
        email_type = "Booking"
    else:
        return None

    # ── Reference ─────────────────────────────────────────────────────────────
    # Subjects seen in the wild:
    #   "... | U2603113069"         (booking / modification)
    #   "... | P2507272499"         (website booking)
    #   "... | N°U2601252458"       (cancellation from elloha)
    reference = _first_group(r"\|\s*N?°?([A-Z]\d{8,12})", subject)
    if not reference:
        log.warning(f"Could not extract reference from: {subject!r}")
        return None

    # ── Booking source — determined from the From display name ───────────────
    # "BOOKING <no-reply@elloha.com>"       → Booking.com
    # "EXPEDIA <no-reply@elloha.com>"       → Expedia
    # "Ferme de la Cour <no-reply@elloha.com>" → Website
    _from_lower = from_header.lower()
    if "expedia" in _from_lower:
        booking_source = "Expedia"
    elif "booking" in _from_lower:
        booking_source = "Booking.com"
    elif "ferme" in _from_lower or reference.startswith("P"):
        booking_source = "Website"
    else:
        # Fallback: U-prefix historically means Booking.com, P means Website
        booking_source = "Booking.com" if reference.startswith("U") else "Website"

    # ── Received date ─────────────────────────────────────────────────────────
    received_dt  = datetime.fromtimestamp(received_ts / 1000)
    event_date   = received_dt.strftime("%d/%m/%Y")

    # ── For Cancellation: we only need to update status + cancellation_date ───
    if email_type == "Cancellation":
        return {
            "email_type":        "Cancellation",
            "reference":         reference,
            "status":            "Cancelled",
            "cancellation_date": event_date,
            "guest_name":        _parse_guest_name(body),   # for logging only
        }

    # ── Rooms ─────────────────────────────────────────────────────────────────
    found_rooms = [r for r in ROOMS if r in body]

    # ── Dates (first occurrence — email repeats them in the tax/fee section) ──
    arrival_date   = _first_group(
        r"Date d['\u2019\u0027]Arriv[e\u00e9]e?\s*:?\s*(\d{2}/\d{2}/\d{4})", body
    )
    departure_date = _first_group(
        r"Date de D[e\u00e9]part\s*:?\s*(\d{2}/\d{2}/\d{4})", body
    )

    nights = 0
    if arrival_date and departure_date:
        try:
            arr    = datetime.strptime(arrival_date,   "%d/%m/%Y")
            dep    = datetime.strptime(departure_date, "%d/%m/%Y")
            nights = (dep - arr).days
        except ValueError:
            pass

    # ── Amount ────────────────────────────────────────────────────────────────
    amount = _parse_amount(body)

    # ── Guest info ────────────────────────────────────────────────────────────
    guest_name  = _parse_guest_name(body)
    phone       = _first_group(r"\*?\s*T[eé]l[eé]phone\s*:\s*(.+?)(?:\n|$)", body)
    guest_email = _first_group(r"\*?\s*E-mail\s*:\s*(.+?)(?:\n|$)", body)
    nationality = phone_to_nationality(phone)

    # ── For Modification: return only the fields that change ──────────────────
    if email_type == "Modification":
        return {
            "email_type":        "Modification",
            "reference":         reference,
            "status":            "Modified",
            "modification_date": event_date,
            "arrival_date":      arrival_date,
            "departure_date":    departure_date,
            "amount":            amount,
            "nights":            nights,
            "guest_name":        guest_name,   # for logging only
        }

    # ── Table d'hôtes ─────────────────────────────────────────────────────────
    table_dhotes = "table d" in body.lower() and "hôtes" in body.lower()

    # ── New Booking ───────────────────────────────────────────────────────────
    return {
        "booking_source":    booking_source,
        "booking_date":      event_date,
        "email_type":        "Booking",
        "status":            "Confirmed",
        "reference":         reference,
        "room1":             found_rooms[0] if len(found_rooms) > 0 else "",
        "room2":             found_rooms[1] if len(found_rooms) > 1 else "",
        "room3":             found_rooms[2] if len(found_rooms) > 2 else "",
        "room4":             found_rooms[3] if len(found_rooms) > 3 else "",
        "arrival_date":      arrival_date,
        "departure_date":    departure_date,
        "amount":            amount,
        "guest_name":        guest_name,
        "phone":             phone,
        "email":             guest_email,
        "nationality":       nationality,
        "nights":            nights,
        "cancellation_date": "",
        "modification_date": "",
        "notes":             "",
        "repeat_guest":      False,
        "visit_count":       1,
        "table_dhotes":      table_dhotes,
        "breakfast":         True,
    }


# ── Applying emails to the Sheet ──────────────────────────────────────────────

class SheetMirror:
    """The Sheet's rows kept in memory while emails are applied, with each reference's row."""

    def __init__(self, worksheet):
        self.worksheet = worksheet
        self.headers, self.rows = sheet.read_rows(worksheet)
        self.row_number_of = {}
        for i, row in enumerate(self.rows):
            ref = str(row.get("reference") or "").strip()
            if ref:
                self.row_number_of[ref] = i + sheet.FIRST_DATA_ROW
        log.info(f"Sheet has {len(self.rows)} rows, {len(self.row_number_of)} unique references")

    def row_for(self, ref: str) -> dict:
        return self.rows[self.row_number_of[ref] - sheet.FIRST_DATA_ROW]

    def add(self, row: dict) -> None:
        sheet.append_row(self.worksheet, row)
        self.rows.append(row)
        self.row_number_of[row["reference"]] = len(self.rows) - 1 + sheet.FIRST_DATA_ROW

    def update(self, ref: str, updates: dict) -> None:
        sheet.update_cells(self.worksheet, self.row_number_of[ref], updates, self.headers)


def apply_email(parsed: dict, bookings_sheet: SheetMirror, gmail) -> str:
    """Write one parsed email to the Sheet. Returns 'added', 'updated' or 'skipped'."""
    if parsed["email_type"] == "Cancellation":
        return apply_cancellation(parsed, bookings_sheet, gmail)
    if parsed["email_type"] == "Modification":
        return apply_modification(parsed, bookings_sheet)
    return add_booking(parsed, bookings_sheet)


def add_booking(row: dict, bookings_sheet: SheetMirror) -> str:
    ref = row["reference"]
    if ref in bookings_sheet.row_number_of:
        return "skipped"
    row["repeat_guest"], row["visit_count"] = detect_repeat_guest(row, bookings_sheet.rows)
    bookings_sheet.add(row)
    log.info(f"  ✓ Added       {ref}  {row.get('guest_name', '')}")
    return "added"


def apply_cancellation(cancel: dict, bookings_sheet: SheetMirror, gmail) -> str:
    ref = cancel["reference"]
    if ref not in bookings_sheet.row_number_of:
        add_missing_booking(cancel, bookings_sheet, gmail)
    if str(bookings_sheet.row_for(ref).get("status", "")).lower() == "cancelled":
        return "skipped"
    bookings_sheet.update(ref, {"status": "Cancelled", "cancellation_date": cancel["cancellation_date"]})
    log.info(f"  ✓ Cancelled   {ref}  {cancel.get('guest_name', '')}")
    return "updated"


def add_missing_booking(cancel: dict, bookings_sheet: SheetMirror, gmail) -> None:
    """A cancellation for a booking not in the Sheet: add it from Gmail, or as a placeholder."""
    ref = cancel["reference"]
    log.info(f"  ? Original booking for {ref} not in sheet, searching Gmail …")
    booking = find_original_booking(gmail, ref)
    if booking:
        add_booking(booking, bookings_sheet)
        return
    placeholder = {col: "" for col in COLUMNS}
    placeholder.update({
        "booking_source": "Unknown", "booking_date": cancel["cancellation_date"],
        "email_type": "Cancellation", "status": "Cancelled", "reference": ref,
        "cancellation_date": cancel["cancellation_date"], "guest_name": cancel.get("guest_name", ""),
    })
    bookings_sheet.add(placeholder)
    log.warning(f"  ! Added (cancel, no booking email found)  {ref}")


def apply_modification(change: dict, bookings_sheet: SheetMirror) -> str:
    ref = change["reference"]
    if ref not in bookings_sheet.row_number_of:
        log.warning(f"  ! Modification for unknown ref {ref} — skipping")
        return "skipped"
    updates = {"status": "Modified", "modification_date": change["modification_date"]}
    for field in ("arrival_date", "departure_date", "amount", "nights"):
        if change.get(field):
            updates[field] = change[field]
    bookings_sheet.update(ref, updates)
    log.info(f"  ✓ Modified    {ref}  {change.get('guest_name', '')}")
    return "updated"


if __name__ == "__main__":
    run()
