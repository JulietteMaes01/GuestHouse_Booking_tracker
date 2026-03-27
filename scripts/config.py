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
    "Royaume-Uni", "Espagne", "Italie", "Suisse", "Autriche",
    "Portugal", "Irlande", "Danemark", "Suède", "Norvège",
    "Pologne", "Hongrie", "Autre",
]

# ── Phone country code → nationality (French) ─────────────────────────────────
# Codes are tried longest-first to avoid e.g. 32 matching before 352.
PHONE_CODE_TO_NATIONALITY = {
    # 3-digit codes (must be checked before 2-digit)
    "352": "Luxembourg",
    "353": "Irlande",
    "354": "Islande",
    "358": "Finlande",
    "370": "Lituanie",
    "371": "Lettonie",
    "372": "Estonie",
    "380": "Ukraine",
    "385": "Croatie",
    "386": "Slovénie",
    "420": "Tchéquie",
    "421": "Slovaquie",
    # 2-digit codes
    "31":  "Pays-Bas",
    "32":  "Belgique",
    "33":  "France",
    "34":  "Espagne",
    "36":  "Hongrie",
    "39":  "Italie",
    "41":  "Suisse",
    "43":  "Autriche",
    "44":  "Royaume-Uni",
    "45":  "Danemark",
    "46":  "Suède",
    "47":  "Norvège",
    "48":  "Pologne",
    "49":  "Allemagne",
    "351": "Portugal",
}

# ── Normalize English → French (for fixing existing sheet data) ────────────────
NATIONALITY_EN_TO_FR = {
    "Belgium":        "Belgique",
    "France":         "France",
    "Netherlands":    "Pays-Bas",
    "Germany":        "Allemagne",
    "Luxembourg":     "Luxembourg",
    "United Kingdom": "Royaume-Uni",
    "UK":             "Royaume-Uni",
    "Spain":          "Espagne",
    "Italy":          "Italie",
    "Switzerland":    "Suisse",
    "Austria":        "Autriche",
    "Portugal":       "Portugal",
    "Ireland":        "Irlande",
    "Denmark":        "Danemark",
    "Sweden":         "Suède",
    "Norway":         "Norvège",
    "Poland":         "Pologne",
    "Hungary":        "Hongrie",
}

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
