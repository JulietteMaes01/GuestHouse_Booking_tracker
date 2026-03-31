"""
fix_table_dhotes.py
───────────────────
One-time backfill script: scans ALL past elloha booking emails and sets
table_dhotes = True on any sheet row whose email body contains "Table d'hôtes".

Safe to run multiple times — only touches the table_dhotes column.

Prerequisites:
  1. Add a "table_dhotes" column to the Google Sheet header row (after visit_count).
  2. Run:  python fix_table_dhotes.py

Usage:
    python fix_table_dhotes.py
"""

import re
import sys
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
log = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auth import get_gmail_service, get_worksheet
from email_parser import get_email_text
from config import ELLOHA_SENDER, COLUMNS

# ── helpers ───────────────────────────────────────────────────────────────────

def _extract_reference(subject: str) -> str | None:
    m = re.search(r"\|\s*N?°?([A-Z]\d{8,12})", subject)
    return m.group(1) if m else None

def _is_table_dhotes(body: str) -> bool:
    return "table d" in body.lower() and "hôtes" in body.lower()

# ── main ──────────────────────────────────────────────────────────────────────

def run():
    log.info("Connecting to Gmail and Google Sheets …")
    service   = get_gmail_service()
    worksheet = get_worksheet()

    # ── Load sheet ────────────────────────────────────────────────────────────
    records = worksheet.get_all_records()
    headers = worksheet.row_values(1)

    if "table_dhotes" not in headers:
        log.error(
            "Column 'table_dhotes' not found in the sheet header row.\n"
            "Please add it manually (after 'visit_count'), then re-run this script."
        )
        sys.exit(1)

    col_idx       = headers.index("table_dhotes") + 1   # 1-based for gspread
    ref_col_idx   = headers.index("reference")          # 0-based for records
    ref_to_row    = {
        str(r.get("reference", "")).strip(): i + 2      # +2 = header + 1-based
        for i, r in enumerate(records)
        if str(r.get("reference", "")).strip()
    }

    log.info(f"Sheet loaded — {len(ref_to_row)} references found")

    # ── Fetch all elloha booking emails (ignoring processed_emails.json) ──────
    query   = f"from:{ELLOHA_SENDER} subject:réservation"
    results = service.users().messages().list(
        userId="me", q=query, maxResults=500
    ).execute()
    messages = results.get("messages", [])
    log.info(f"Found {len(messages)} elloha booking email(s)")

    updates      = []   # list of (sheet_row, col_idx, True)
    found_refs   = set()

    for msg_meta in messages:
        msg_id  = msg_meta["id"]
        msg     = service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()

        subject = ""
        for hdr in msg.get("payload", {}).get("headers", []):
            if hdr["name"].lower() == "subject":
                subject = hdr["value"]
                break

        reference = _extract_reference(subject)
        if not reference:
            continue

        body = get_email_text(msg.get("payload", {}))
        if not _is_table_dhotes(body):
            continue

        # This email mentions Table d'hôtes
        row_num = ref_to_row.get(reference)
        if not row_num:
            log.warning(f"  Reference {reference} not found in sheet — skipping")
            continue

        if reference in found_refs:
            continue   # already queued

        found_refs.add(reference)
        log.info(f"  🍽️  {reference}  (row {row_num}) → table_dhotes = True")
        updates.append({
            "range": f"{_col_letter(col_idx)}{row_num}",
            "values": [["True"]],
        })

    # ── Write to sheet ────────────────────────────────────────────────────────
    if not updates:
        log.info("No Table d'hôtes bookings found — nothing to update.")
        return

    log.info(f"Writing {len(updates)} update(s) to sheet …")
    worksheet.batch_update(updates, value_input_option="RAW")
    log.info(f"Done! {len(updates)} row(s) updated.")


def _col_letter(n: int) -> str:
    """Convert 1-based column number to A1-notation letter(s)."""
    result = ""
    while n:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


if __name__ == "__main__":
    run()
