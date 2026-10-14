"""Returning guests and nationalities."""
import guests


def test_phone_country_code_gives_nationality():
    assert guests.phone_to_nationality("+32 470 12 34 56") == "Belgique"
    assert guests.phone_to_nationality("00352621123456") == "Luxembourg"
    assert guests.phone_to_nationality("0470123456") == ""


def test_returning_guest_matched_by_email_or_phone():
    earlier = [
        {"reference": "U1", "email": "anne@example.com", "phone": "+32 470 00 00 01"},
        {"reference": "U2", "email": "", "phone": "32470000001"},
    ]
    assert guests.detect_repeat_guest({"email": "ANNE@example.com"}, earlier) == (True, 2)
    assert guests.detect_repeat_guest({"phone": "+32 470 000 001"}, earlier) == (True, 3)
    assert guests.detect_repeat_guest({"email": "new@example.com"}, earlier) == (False, 1)


def test_proxy_emails_and_dummy_phones_never_match():
    earlier = [{"reference": "U1", "email": "x@guest.booking.com", "phone": "0000000"}]
    new = {"email": "x@guest.booking.com", "phone": "0000000"}
    assert guests.detect_repeat_guest(new, earlier) == (False, 1)


def test_english_nationality_gets_french_flag():
    assert guests.flag_for("Belgium") == "🇧🇪"
    assert guests.flag_for("Belgique") == "🇧🇪"
    assert guests.flag_for("Mars") == "🌍"
