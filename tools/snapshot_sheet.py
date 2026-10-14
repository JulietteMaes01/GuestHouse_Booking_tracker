"""
Save the Google Sheet as it is right now to tests/fixtures/sheet.json.

The snapshot holds guest personal data: it is gitignored and stays on this Mac.
Both gspread views are kept, because the scripts use both:
  records — worksheet.get_all_records()  (numbers already converted)
  values  — worksheet.get_all_values()   (raw strings)

    python tools/snapshot_sheet.py
"""
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from auth import get_worksheet  # noqa: E402

FIXTURE = os.path.join(REPO_ROOT, "tests", "fixtures", "sheet.json")


def main():
    worksheet = get_worksheet()
    snapshot = {
        "records": worksheet.get_all_records(),
        "values": worksheet.get_all_values(),
    }
    os.makedirs(os.path.dirname(FIXTURE), exist_ok=True)
    with open(FIXTURE, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, ensure_ascii=False, indent=1)
    print(f"Saved {len(snapshot['records'])} rows → {FIXTURE}")


if __name__ == "__main__":
    main()
