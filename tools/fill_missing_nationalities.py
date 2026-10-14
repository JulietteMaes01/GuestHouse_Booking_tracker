"""
One-off: fill empty nationality cells in the Sheet from the guests' phone numbers.
Only empty (or 'Unknown') cells are touched.

    python tools/fill_missing_nationalities.py           # show what would change
    python tools/fill_missing_nationalities.py --write   # write it to the Sheet
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import sheet  # noqa: E402
from auth import get_worksheet  # noqa: E402
from guests import phone_to_nationality  # noqa: E402


def main():
    worksheet = get_worksheet()
    headers, rows = sheet.read_rows(worksheet)
    changes = [
        (i + sheet.FIRST_DATA_ROW, row, phone_to_nationality(row.get("phone")))
        for i, row in enumerate(rows)
        if str(row.get("nationality", "")).strip() in ("", "Unknown")
    ]
    changes = [(sheet_row, row, nationality) for sheet_row, row, nationality in changes if nationality]

    for sheet_row, row, nationality in changes:
        print(f"  row {sheet_row:4d}  {row.get('reference', ''):13s} {row.get('guest_name', '')[:28]:28s} → {nationality}")
    print(f"{len(changes)} empty nationality cell(s) can be filled.")

    if "--write" in sys.argv:
        for sheet_row, _, nationality in changes:
            sheet.update_cells(worksheet, sheet_row, {"nationality": nationality}, headers)
        print("✓ Written to the Sheet.")
    elif changes:
        print("Nothing written. Run again with --write to save.")


if __name__ == "__main__":
    main()
