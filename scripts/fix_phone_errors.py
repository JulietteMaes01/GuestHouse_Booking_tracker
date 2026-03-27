"""
fix_phone_errors.py
───────────────────
One-time script.  Finds every row in the Google Sheet whose 'phone' cell
shows #ERROR! (caused by phone numbers starting with '+' being written as
formulas), re-fetches the original elloha email for that booking, and
overwrites the cell with the correct phone number stored as plain text.

Run once:
    python fix_phone_errors.py
"""
import logging
import gspread.utils

from auth import get_gmail_service, get_worksheet
from email_parser import get_full_message, get_email_text, _first_group

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
log = logging.getLogger(__name__)


def run():
    log.info("Connecting …")
    service   = get_gmail_service()
    worksheet = get_worksheet()

    all_values = worksheet.get_all_values()
    if not all_values:
        log.error("Sheet is empty.")
        return

    headers = all_values[0]
    if "phone" not in headers or "reference" not in headers:
        log.error("Could not find 'phone' or 'reference' columns in the sheet.")
        return

    phone_col_idx = headers.index("phone") + 1      # 1-indexed for gspread
    ref_col_idx   = headers.index("reference")      # 0-indexed for list access
    name_col_idx  = headers.index("guest_name") if "guest_name" in headers else -1

    error_rows = []
    for sheet_row_num, vals in enumerate(all_values[1:], start=2):
        while len(vals) < len(headers):
            vals.append("")
        phone = vals[phone_col_idx - 1]
        ref   = vals[ref_col_idx]
        name  = vals[name_col_idx] if name_col_idx >= 0 else ""
        if phone == "#ERROR!" and ref:
            error_rows.append((sheet_row_num, ref, name))

    if not error_rows:
        log.info("No #ERROR! phone cells found — nothing to do.")
        return

    log.info(f"Found {len(error_rows)} row(s) with #ERROR! in phone:")
    for _, ref, name in error_rows:
        log.info(f"  {ref}  {name}")

    fixed = not_found = 0

    for sheet_row_num, ref, name in error_rows:
        log.info(f"\nLooking up {ref} ({name}) …")

        # Search Gmail for the booking email with this reference
        result = service.users().messages().list(
            userId="me",
            q=f"from:no-reply@elloha.com {ref}",
            maxResults=5,
        ).execute()

        msgs = result.get("messages", [])
        if not msgs:
            log.warning(f"  No Gmail message found for reference {ref}")
            not_found += 1
            continue

        # Try each candidate message until we find a phone number
        phone_found = ""
        for msg_stub in msgs:
            msg  = get_full_message(service, msg_stub["id"])
            body = get_email_text(msg["payload"])
            phone_found = _first_group(
                r"\*?\s*T[eé]l[eé]phone\s*:\s*(.+?)(?:\n|$)", body
            )
            if phone_found:
                break

        if not phone_found:
            log.warning(f"  Phone number not found in email body for {ref}")
            not_found += 1
            continue

        # Write the corrected phone using RAW to prevent formula interpretation
        cell_a1 = gspread.utils.rowcol_to_a1(sheet_row_num, phone_col_idx)
        worksheet.update(cell_a1, [[phone_found]], value_input_option="RAW")
        log.info(f"  ✓ Fixed → {phone_found}")
        fixed += 1

    log.info(f"\nDone — {fixed} fixed, {not_found} not found")


if __name__ == "__main__":
    run()
