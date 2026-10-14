"""
Who is the guest? Returning-guest detection and nationality.
"""
from __future__ import annotations

import re

from config import NATIONALITY_EN_TO_FR, NATIONALITY_FLAGS, PHONE_CODE_TO_NATIONALITY

# Booking platforms hide the real address behind these; they can't identify a guest.
PROXY_EMAIL_DOMAINS = ("@guest.booking.com", "@m.expediapartnercentral.com")


def digits_only(phone) -> str:
    """'+32 470 12 34 56' → '32470123456'. Accepts text or numbers."""
    return re.sub(r"\D", "", str(phone or ""))


def detect_repeat_guest(new_row: dict, existing_rows: list[dict]) -> tuple[bool, int]:
    """
    Return (is_repeat, visit_count) by matching earlier bookings on email or phone.
    Proxy emails and placeholder phones like '0000000' never count as a match.
    """
    new_email = str(new_row.get("email") or "").lower()
    new_phone = digits_only(new_row.get("phone"))
    can_match_email = bool(new_email) and not any(d in new_email for d in PROXY_EMAIL_DOMAINS)
    can_match_phone = len(set(new_phone)) > 1

    earlier_visits = 0
    seen_refs = set()
    for row in existing_rows:
        ref = str(row.get("reference") or "")
        if ref in seen_refs:
            continue
        seen_refs.add(ref)

        email = str(row.get("email") or "").lower()
        phone = digits_only(row.get("phone"))
        if can_match_email and email == new_email:
            earlier_visits += 1
        elif can_match_phone and phone == new_phone:
            earlier_visits += 1

    return earlier_visits > 0, earlier_visits + 1


def phone_to_nationality(phone) -> str:
    """Guess the nationality (in French) from the phone's country code, or ''."""
    digits = digits_only(phone)
    if digits.startswith("00"):
        digits = digits[2:]
    for length in (3, 2):
        nationality = PHONE_CODE_TO_NATIONALITY.get(digits[:length])
        if nationality:
            return nationality
    return ""


def nationality_in_french(nationality: str) -> str:
    """'Belgium' → 'Belgique'; French names are returned as they are."""
    nationality = str(nationality or "").strip()
    return NATIONALITY_EN_TO_FR.get(nationality, nationality)


def flag_for(nationality: str) -> str:
    return NATIONALITY_FLAGS.get(nationality_in_french(nationality), "🌍")
