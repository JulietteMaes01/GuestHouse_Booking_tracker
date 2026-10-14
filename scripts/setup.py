"""
setup.py
────────
Log in to Google: the first time, or again when the login has expired
(after deleting creds/token.pickle).

    python setup.py

A browser window opens: sign in with lafermedelacour2016@gmail.com and click
Allow. The script then checks that the Sheet and Gmail can be read.
"""
import os
import sys

from config import CREDENTIALS_FILE


def main():
    if not os.path.exists(CREDENTIALS_FILE):
        sys.exit(f"""
[!] credentials.json not found. Expected here:
    {CREDENTIALS_FILE}

Get it from https://console.cloud.google.com/ → APIs & Services → Credentials
→ + Create Credentials → OAuth client ID → type "Desktop app" → Download JSON.
Rename it to credentials.json, put it in the folder above, and run this again.
(Gmail API and Google Sheets API must be enabled in the same project.)
""")

    print("Logging in to Google — sign in with lafermedelacour2016@gmail.com and click 'Allow' …")
    from auth import get_gmail_service, get_worksheet

    rows = get_worksheet().get_all_values()
    print(f"  ✓ Google Sheet readable — {len(rows) - 1} booking rows")

    profile = get_gmail_service().users().getProfile(userId="me").execute()
    print(f"  ✓ Gmail readable — logged in as {profile.get('emailAddress')}")

    print("\nAll set. The booking form starts with:  python app.py")


if __name__ == "__main__":
    main()
