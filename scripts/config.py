"""
Every setting of the booking tracker, in one place.

Change prices, rooms, sources or goals here; the scripts read them from this file.
"""
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

# ── Published pages (GitHub Pages serves this folder) ─────────────────────────
DOCS_DIR      = _os.path.join(_REPO_ROOT, "docs")
TEMPLATES_DIR = _os.path.join(_REPO_ROOT, "templates")
OWNER_NAME    = "Juliette Maes"

# ── Guesthouse ────────────────────────────────────────────────────────────────
ROOMS = [
    "Laurasie de la Cour",
    "Tibert de la Cour",
    "Odette de la Cour",
    "Léon de la Cour",
]

# Cabins (not run by the farm) where Angela delivers dishes in the evening
CABINS = [
    "Bonne aventure",
    "Ombre et lumière",
    "Regards croisés",
    "Tanière des Nutons",
    "Sens dessus dessous",
    "Trappes et Cachettes",
    "Couleurs du monde",
]

MASSAGE_OPTIONS = [
    "Réflexologie 1h (55€)",
    "3 séances réflexologie (120€)",
    "Massage détente pieds 30min (40€)",
    "Massage détente dos/arrière jambes 60min (65€)",
    "Massage détente corps entier 90min (95€)",
    "Massage du dos 30min (30€)",
    "Massage du dos 45min (45€)",
    "Massage des 5 continents 1h15 (80€)",
]

NATIONALITIES = [
    "Belgique", "France", "Pays-Bas", "Allemagne", "Luxembourg",
    "Royaume-Uni", "Espagne", "Italie", "Suisse", "Autriche",
    "Portugal", "Irlande", "Danemark", "Suède", "Norvège",
    "Pologne", "Hongrie", "États-Unis", "Autre",
]

# ── Nationalities ─────────────────────────────────────────────────────────────
# The Sheet stores nationalities in French. Older rows may be in English.
NATIONALITY_EN_TO_FR = {
    "Belgium": "Belgique", "Netherlands": "Pays-Bas", "Germany": "Allemagne",
    "United Kingdom": "Royaume-Uni", "UK": "Royaume-Uni", "Spain": "Espagne",
    "Italy": "Italie", "Switzerland": "Suisse", "Austria": "Autriche",
    "Ireland": "Irlande", "Denmark": "Danemark", "Sweden": "Suède",
    "Norway": "Norvège", "Poland": "Pologne", "Hungary": "Hongrie",
    "United States": "États-Unis", "USA": "États-Unis", "Romania": "Roumanie",
    "China": "Chine", "Japan": "Japon", "Australia": "Australie",
}

# Phone codes and flags of every country are in countries.py.

# ── Booking sources ───────────────────────────────────────────────────────────
# Old Sheet rows say "Manual"; they are read as "Email/phone".
SOURCE_ALIASES = {
    "Manual": "Email/phone",
}

# ── Commissions ────────────────────────────────────────────────────────────────
# Net amount = gross amount × (1 - commission rate)
COMMISSIONS = {
    "Booking.com":          0.15,   # 15% — update when confirmed
    "Website":              0.00,
    "Expedia":              0.15,   # update when confirmed
    "Social Deal":          0.00,   # update when confirmed
    "Umfulana":             0.00,   # update when confirmed
    "Email/phone":          0.00,
}

# Sources where guests pay fully in advance (show ✅ Payé on schedule)
PREPAID_SOURCES = {"Booking.com", "Social Deal", "Expedia"}

# Sources where guests pay 50% in advance, 50% on arrival (show 💳 50% restant)
SPLIT_PAYMENT_SOURCES = {"Umfulana"}

# Sources that always include breakfast automatically
BREAKFAST_AUTO_SOURCES = {"Booking.com", "Website", "Umfulana"}

# Sources Angela can pick in the booking form (the others arrive by email)
FORM_SOURCES = ["Email/phone", "Social Deal", "Umfulana"]

# ── Weekly booking goals (number of confirmed bookings per week) ───────────────
BOOKING_GOALS = {
    2025: 3,
    2026: 5,
}

# ── Sheet column order (must match the Google Sheet header row exactly) ────────
COLUMNS = [
    "booking_source", "booking_date", "email_type", "status", "reference",
    "room1", "room2", "room3", "room4",
    "arrival_date", "departure_date", "amount",
    "guest_name", "phone", "email", "nationality", "nights",
    "cancellation_date", "modification_date", "notes",
    "repeat_guest", "visit_count", "table_dhotes", "breakfast", "guest_count", "massage",
    "cabane", "plats",
]
