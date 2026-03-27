import os as _os

_SCRIPTS_DIR = _os.path.dirname(_os.path.abspath(__file__))          # …/GuestHouse_Booking_tracker/scripts/
_REPO_ROOT   = _os.path.dirname(_SCRIPTS_DIR)                        # …/GuestHouse_Booking_tracker/
_CREDS_DIR   = _os.path.join(_os.path.dirname(_REPO_ROOT), "creds")  # …/La Ferme de la Cour/creds/

# ── Google Sheets ─────────────────────────────────────────────────────────────
SPREADSHEET_ID = "1nrVpFlQ6Bh2H5RCC8FWz9I9JECDWBx7F4T2YJIXS5Ro"
WORKSHEET_GID  = 1484078102

# ── Google OAuth ──────────────────────────────────────────────────────────────
CREDENTIALS_FILE = _os.path.join(_CREDS_DIR, "credentials.json")
TOKEN_FILE       = _os.path.join(_CREDS_DIR, "token.pickle")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]

# ── Gmail ─────────────────────────────────────────────────────────────────────
ELLOHA_SENDER = "no-reply@elloha.com"

# ── GitHub / GitHub Pages ─────────────────────────────────────────────────────
GITHUB_REPO_PATH = _REPO_ROOT
DOCS_FOLDER      = "docs"

# ── Guesthouse ────────────────────────────────────────────────────────────────
ROOMS = [
    "Laurasie de la Cour",
    "Tibert de la Cour",
    "Odette de la Cour",
    "Léon de la Cour",
]

NATIONALITIES = [
    "Belgique", "France", "Pays-Bas", "Allemagne", "Luxembourg",
    "Royaume-Uni", "Espagne", "Italie", "Suisse", "Autre",
]

OWNER_NAME = "Juliette Maes"

# ── Sheet column order (must match the Google Sheet header row exactly) ────────
COLUMNS = [
    "booking_source", "booking_date", "email_type", "status", "reference",
    "room1", "room2", "room3", "room4",
    "arrival_date", "departure_date", "amount",
    "guest_name", "phone", "email", "nationality", "nights",
    "cancellation_date", "modification_date", "notes",
    "repeat_guest", "visit_count",
]
