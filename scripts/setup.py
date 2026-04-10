"""
setup.py
────────
One-time setup wizard.  Run this first before anything else.

    python setup.py

It will:
  1. Check that credentials.json is present (and explain how to get it if not)
  2. Run the Google OAuth flow (opens a browser window once)
  3. Verify access to the Google Sheet
  4. Verify access to Gmail
  5. Verify that the GitHub repo / docs folder is reachable
  6. Print a summary
"""
import os
import sys

# ── Step 1: credentials.json ──────────────────────────────────────────────────
print("\n" + "═" * 60)
print("  La Ferme de la Cour — Setup")
print("═" * 60)

from config import CREDENTIALS_FILE
_CREDS_DIR = os.path.dirname(CREDENTIALS_FILE)

if not os.path.exists(CREDENTIALS_FILE):
    print(f"""
[!] 'credentials.json' not found.

Expected location:
    {CREDENTIALS_FILE}

To create it:
  1. Go to  https://console.cloud.google.com/
  2. Create a new project (e.g. "LaFermeDeLaCour")
  3. Enable these two APIs:
       • Gmail API
       • Google Sheets API
     (Search for each in the top search bar → click Enable)
  4. Go to  APIs & Services → Credentials
  5. Click  + Create Credentials → OAuth client ID
  6. Application type: Desktop app   ← IMPORTANT: must be "Desktop app", not "Web"
  7. Click Create, then  ↓ Download JSON
  8. Rename the downloaded file to  credentials.json
  9. Create this folder if it does not exist and move the file there:
       {_CREDS_DIR}
 10. Re-run this script.
""")
    sys.exit(1)

print(f"\n  ✓  credentials.json found  ({CREDENTIALS_FILE})")

# ── Step 2: OAuth flow ────────────────────────────────────────────────────────
print("\n  [2/4] Authenticating with Google …")
print("        A browser window will open — sign in with lafermedelacour2016@gmail.com")
print("        and click 'Allow'.\n")

try:
    from auth import get_credentials
    creds = get_credentials()
    print("  ✓  Authentication successful")
except Exception as exc:
    print(f"  ✗  Authentication failed: {exc}")
    sys.exit(1)

# ── Step 3: Google Sheet ──────────────────────────────────────────────────────
print("\n  [3/4] Testing Google Sheets access …")
try:
    from auth import get_worksheet
    ws      = get_worksheet()
    records = ws.get_all_records()
    print(f"  ✓  Sheet accessible — {len(records)} booking rows found")
except Exception as exc:
    print(f"  ✗  Could not access sheet: {exc}")
    print("       Make sure the Google account has access to the spreadsheet.")
    sys.exit(1)

# ── Step 4: Gmail ─────────────────────────────────────────────────────────────
print("\n  [4/4] Testing Gmail access …")
try:
    from auth import get_gmail_service
    svc    = get_gmail_service()
    result = svc.users().getProfile(userId="me").execute()
    print(f"  ✓  Gmail accessible — logged in as {result.get('emailAddress')}")
except Exception as exc:
    print(f"  ✗  Could not access Gmail: {exc}")
    sys.exit(1)

# ── Step 5: GitHub repo check ─────────────────────────────────────────────────
import subprocess
from config import GITHUB_REPO_PATH, DOCS_FOLDER

print("\n  [Optional] Checking GitHub repo …")
try:
    result = subprocess.run(
        ["git", "-C", GITHUB_REPO_PATH, "remote", "-v"],
        capture_output=True, text=True
    )
    if result.returncode == 0 and result.stdout.strip():
        print(f"  ✓  Git remote found:\n     {result.stdout.strip().splitlines()[0]}")
    else:
        print("  !  No git remote found. Make sure this folder is your cloned GitHub repo.")
        print("     If not, update GITHUB_REPO_PATH in config.py to point to the repo.")
except Exception as exc:
    print(f"  !  Could not check git: {exc}")

# ── Done ──────────────────────────────────────────────────────────────────────
print(f"""
{'═' * 60}
  Setup complete!  You can now run:

  • python email_parser.py        — parse new elloha emails
  • python schedule_generator.py  — generate & push HTML schedule
  • python app.py                 — start the manual booking form
  • python run.py                 — parse emails + generate schedule

  For the booking form (for your mother-in-law):
  • Open a browser and go to  http://localhost:5000
  • Or double-click  start_form.command  to launch it automatically
{'═' * 60}
""")
