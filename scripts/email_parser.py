"""
email_parser.py
───────────────
Scans the lafermedelacour2016@gmail.com inbox for booking/cancellation/
modification emails from elloha and syncs them to the Google Sheet:

  • New booking     → new row added
  • Cancellation    → existing row updated (status → Cancelled)
  • Modification    → existing row updated (dates / amount / status)

Usage:
    python email_parser.py
"""
import base64
import re
import json
import os
import logging
import traceback
from datetime import datetime

from bs4 import BeautifulSoup
import gspread.utils

# Stores Gmail message IDs that have already been processed,
# so modifications/cancellations are never re-applied on subsequent runs.
_SCRIPT_DIR       = os.path.dirname(os.path.abspath(__file__))
_PROCESSED_ID_FILE = os.path.join(_SCRIPT_DIR, "processed_emails.json")


def _load_processed_ids() -> set:
    if os.path.exists(_PROCESSED_ID_FILE):
        with open(_PROCESSED_ID_FILE) as fh:
            return set(json.load(fh))
    return set()


def _save_processed_ids(ids: set) -> None:
    with open(_PROCESSED_ID_FILE, "w") as fh:
        json.dump(sorted(ids), fh, indent=2)

from auth import get_gmail_service, get_worksheet
from config import ELLOHA_SENDER, ROOMS, COLUMNS

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
log = logging.getLogger(__name__)


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


def fetch_elloha_emails(service, max_results: int = 500) -> list:
    """Return a list of raw Gmail message stubs from elloha."""
    query = f"from:{ELLOHA_SENDER}"
    result = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()
    messages = result.get("messages", [])
    log.info(f"Found {len(messages)} elloha email(s) in inbox")
    return messages


def get_full_message(service, msg_id: str) -> dict:
    return service.users().messages().get(
        userId="me", id=msg_id, format="full"
    ).execute()


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


def parse_email(subject: str, body: str, received_ts: int) -> dict | None:
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
        email_type, status = "Cancellation", "Cancelled"
    elif "modification" in subject_lower:
        email_type, status = "Modification", "Modified"
    elif "r\u00e9servation" in subject_lower or "reservation" in subject_lower:
        email_type, status = "Booking", "Confirmed"
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

    # ── Booking source ────────────────────────────────────────────────────────
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
        "nationality":       "",
        "nights":            nights,
        "cancellation_date": "",
        "modification_date": "",
        "notes":             "",
        "repeat_guest":      False,
        "visit_count":       1,
    }


# ── Repeat-guest detection ────────────────────────────────────────────────────

def _normalize_phone(phone) -> str:
    """Strip all non-digit characters. Accepts str or int."""
    return re.sub(r"\D", "", str(phone or ""))


def detect_repeat_guest(new_row: dict, existing_records: list) -> tuple:
    """
    Return (is_repeat, visit_count) by matching on email or normalised phone.
    Booking.com proxy emails (@guest.booking.com) are never used for matching.
    """
    new_email = str(new_row.get("email") or "").lower()
    new_phone = _normalize_phone(new_row.get("phone") or "")
    use_email = bool(new_email) and "@guest.booking.com" not in new_email

    matches   = 0
    seen_refs = set()

    for rec in existing_records:
        ref = str(rec.get("reference") or "")
        if ref in seen_refs:
            continue
        seen_refs.add(ref)

        existing_email = str(rec.get("email") or "").lower()
        existing_phone = _normalize_phone(rec.get("phone") or "")

        if use_email and existing_email and existing_email == new_email:
            matches += 1
        elif new_phone and existing_phone and existing_phone == new_phone:
            matches += 1

    return matches > 0, matches + 1


# ── Sheet helpers ─────────────────────────────────────────────────────────────

def load_sheet_with_row_numbers(worksheet) -> tuple:
    """
    Returns:
        headers       — list of column names (from row 1)
        records       — list of dicts (one per data row)
        ref_to_rownum — {reference: 1-indexed sheet row number}
    """
    all_values = worksheet.get_all_values()
    if not all_values:
        return [], [], {}

    headers = all_values[0]
    records = []
    ref_to_rownum = {}

    for sheet_row_num, vals in enumerate(all_values[1:], start=2):
        # Pad short rows so zip always covers every header
        while len(vals) < len(headers):
            vals.append("")
        record = dict(zip(headers, vals))
        records.append(record)
        ref = str(record.get("reference") or "").strip()
        if ref:
            ref_to_rownum[ref] = sheet_row_num

    return headers, records, ref_to_rownum


def update_row_fields(worksheet, row_num: int, updates: dict, headers: list) -> None:
    """Update multiple cells in a single batch API call (avoids rate-limit errors)."""
    batch = []
    for field, value in updates.items():
        if field in headers:
            col_idx  = headers.index(field) + 1   # 1-indexed
            cell_a1  = gspread.utils.rowcol_to_a1(row_num, col_idx)
            batch.append({
                "range":  cell_a1,
                "values": [[str(value) if value is not None else ""]],
            })
    if batch:
        worksheet.batch_update(batch, value_input_option="RAW")


def append_new_row(worksheet, row: dict) -> None:
    values = [row.get(col, "") for col in COLUMNS]
    worksheet.append_row(values, value_input_option="RAW")


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    log.info("Connecting to Gmail and Google Sheets …")
    service   = get_gmail_service()
    worksheet = get_worksheet()

    headers, existing_records, ref_to_rownum = load_sheet_with_row_numbers(worksheet)
    existing_refs = set(ref_to_rownum.keys())
    log.info(
        f"Sheet has {len(existing_records)} rows, "
        f"{len(existing_refs)} unique references"
    )

    messages      = fetch_elloha_emails(service)
    processed_ids = _load_processed_ids()

    added = updated = skipped = errors = 0

    for msg_meta in messages:
        if msg_meta["id"] in processed_ids:
            skipped += 1
            continue
        try:
            msg     = get_full_message(service, msg_meta["id"])
            hdr     = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            subject = str(hdr.get("Subject", ""))
            ts      = int(msg.get("internalDate", 0))

            body = get_email_text(msg["payload"])
            row  = parse_email(subject, body, ts)

            if row is None:
                skipped += 1
                continue

            ref        = row["reference"]
            email_type = row["email_type"]

            # ── Cancellation: update existing row ────────────────────────────
            if email_type == "Cancellation":
                if ref in ref_to_rownum:
                    existing = existing_records[ref_to_rownum[ref] - 2]  # 0-indexed
                    if str(existing.get("status", "")).lower() == "cancelled":
                        skipped += 1
                        continue
                    update_row_fields(worksheet, ref_to_rownum[ref], {
                        "status":            "Cancelled",
                        "cancellation_date": row["cancellation_date"],
                    }, headers)
                    log.info(f"  ✓ Cancelled   {ref}  {row['guest_name']}")
                    updated += 1
                else:
                    # Original booking not in sheet — add as a note row
                    full_row = {c: "" for c in COLUMNS}
                    full_row.update({
                        "booking_source":    "Unknown",
                        "booking_date":      row["cancellation_date"],
                        "email_type":        "Cancellation",
                        "status":            "Cancelled",
                        "reference":         ref,
                        "cancellation_date": row["cancellation_date"],
                        "guest_name":        row.get("guest_name", ""),
                    })
                    append_new_row(worksheet, full_row)
                    ref_to_rownum[ref] = len(existing_records) + 2
                    existing_records.append(full_row)
                    existing_refs.add(ref)
                    log.info(f"  ✓ Added (cancel, no original)  {ref}")
                    added += 1

            # ── Modification: update existing row ────────────────────────────
            elif email_type == "Modification":
                if ref in ref_to_rownum:
                    updates = {
                        "status":            "Modified",
                        "modification_date": row["modification_date"],
                    }
                    if row.get("arrival_date"):
                        updates["arrival_date"] = row["arrival_date"]
                    if row.get("departure_date"):
                        updates["departure_date"] = row["departure_date"]
                    if row.get("amount"):
                        updates["amount"] = row["amount"]
                    if row.get("nights"):
                        updates["nights"] = row["nights"]
                    update_row_fields(worksheet, ref_to_rownum[ref], updates, headers)
                    log.info(f"  ✓ Modified    {ref}  {row['guest_name']}")
                    updated += 1
                else:
                    # Original not in sheet — skip (nothing to update)
                    log.warning(f"  ! Modification for unknown ref {ref} — skipping")
                    skipped += 1

            # ── New booking ───────────────────────────────────────────────────
            else:
                if ref in existing_refs:
                    skipped += 1
                    continue
                row["repeat_guest"], row["visit_count"] = detect_repeat_guest(
                    row, existing_records
                )
                append_new_row(worksheet, row)
                existing_records.append(row)
                existing_refs.add(ref)
                ref_to_rownum[ref] = len(existing_records) + 1
                added += 1
                log.info(f"  ✓ Added       {ref}  {row['guest_name']}")

            # Mark as processed only on success
            processed_ids.add(msg_meta["id"])

        except Exception as exc:
            errors += 1
            log.error(
                f"  ✗ Error on message {msg_meta['id']}: {exc}\n"
                + traceback.format_exc()
            )

    _save_processed_ids(processed_ids)
    log.info(f"Done — {added} added, {updated} updated, {skipped} skipped, {errors} errors")


if __name__ == "__main__":
    run()
