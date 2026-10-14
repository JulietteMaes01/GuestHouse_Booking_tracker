"""Returning guests and nationalities."""
import guests


def test_phone_country_code_gives_nationality():
    assert guests.phone_to_nationality("+32 470 12 34 56") == "Belgique"
    assert guests.phone_to_nationality("00352621123456") == "Luxembourg"
    assert guests.phone_to_nationality("0470123456") == "Belgique"


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


def test_every_way_a_phone_number_is_written():
    assert guests.phone_to_nationality("+33 6 12 34 56 78") == "France"
    assert guests.phone_to_nationality("0049 151 2345 6789") == "Allemagne"
    assert guests.phone_to_nationality("[supprimé]") == "Belgique"        # code without +
    assert guests.phone_to_nationality("[supprimé]") == "Belgique"  # extra 0 after the code
    assert guests.phone_to_nationality("+0470 12 34 56") == "Belgique"     # website adds + to local numbers
    assert guests.phone_to_nationality("[supprimé]") == "Belgique"          # Sheet dropped the leading 0
    assert guests.phone_to_nationality("+1 212 555 0100") == "États-Unis"
    assert guests.phone_to_nationality("+1 514 555 0100") == "Canada"
    assert guests.phone_to_nationality("+7 701 123 4567") == "Kazakhstan"
    assert guests.phone_to_nationality("+7 916 123 4567") == "Russie"
    assert guests.phone_to_nationality("+596 696 12 34 56") == "Martinique"
    assert guests.phone_to_nationality("+81 90 1234 5678") == "Japon"


def test_placeholder_phones_give_no_nationality():
    for placeholder in ("", "000", "0000000", "+11111111111"):
        assert guests.phone_to_nationality(placeholder) == ""


def test_every_country_has_its_flag():
    assert guests.flag_for("Canada") == "🇨🇦"
    assert guests.flag_for("Japon") == "🇯🇵"
    assert guests.flag_for("Royaume-Uni") == "🇬🇧"
