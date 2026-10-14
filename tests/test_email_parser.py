"""Reading elloha emails into Sheet rows."""
from datetime import datetime

import email_parser

RECEIVED = int(datetime(2026, 3, 11, 9, 30).timestamp() * 1000)   # Gmail internalDate (ms)

BOOKING_BODY = """Nouvelle réservation
Laurasie de la Cour
Tibert de la Cour
Date d'Arrivée : 12/08/2026
Date de Départ : 15/08/2026
Montant total 1 226,25 €
* Nom : Jean Exemple
* Téléphone : +352 621 123 456
* E-mail : abc123@guest.booking.com
Options : Table d'hôtes
"""


def test_new_booking_from_booking_com():
    row = email_parser.parse_email("Nouvelle réservation | U2603113069", BOOKING_BODY, RECEIVED,
                                   from_header="BOOKING <no-reply@elloha.com>")
    assert row == {
        "booking_source": "Booking.com", "booking_date": "11/03/2026", "email_type": "Booking",
        "status": "Confirmed", "reference": "U2603113069",
        "room1": "Laurasie de la Cour", "room2": "Tibert de la Cour", "room3": "", "room4": "",
        "arrival_date": "12/08/2026", "departure_date": "15/08/2026", "amount": 1226.25,
        "guest_name": "Jean Exemple", "phone": "+352 621 123 456",
        "email": "abc123@guest.booking.com", "nationality": "Luxembourg", "nights": 3,
        "cancellation_date": "", "modification_date": "", "notes": "",
        "repeat_guest": False, "visit_count": 1, "table_dhotes": True, "breakfast": True,
    }


def test_booking_source_comes_from_sender_name():
    def source(from_header, ref="U2603113069"):
        return email_parser.parse_email(f"Réservation | {ref}", BOOKING_BODY, RECEIVED,
                                        from_header=from_header)["booking_source"]
    assert source("EXPEDIA <no-reply@elloha.com>") == "Expedia"
    assert source("Ferme de la Cour <no-reply@elloha.com>") == "Website"
    assert source("no-reply@elloha.com", ref="P2507272499") == "Website"


def test_cancellation_only_carries_what_changes():
    row = email_parser.parse_email("Annulation de réservation | N°U2601252458",
                                   "* Nom du Client: Marie Exemple\n", RECEIVED)
    assert row == {"email_type": "Cancellation", "reference": "U2601252458", "status": "Cancelled",
                   "cancellation_date": "11/03/2026", "guest_name": "Marie Exemple"}


def test_modification_carries_new_dates_and_amount():
    body = "Date d'Arrivée : 13/08/2026\nDate de Départ : 15/08/2026\nMontant de la Réservation : 300.00 €\n"
    row = email_parser.parse_email("Modification | U2603113069", body, RECEIVED)
    assert row["email_type"] == "Modification"
    assert (row["arrival_date"], row["departure_date"], row["amount"], row["nights"]) == \
        ("13/08/2026", "15/08/2026", 300.0, 2)


def test_unrelated_email_is_ignored():
    assert email_parser.parse_email("Votre facture elloha", BOOKING_BODY, RECEIVED) is None


# ── Whole run, with fake Gmail and a fake Sheet ───────────────────────────────

import base64

import pytest

from config import COLUMNS
from fake_sheet import FakeWorksheet


class FakeGmail:
    """Just enough of the Gmail API: list messages, get one message."""

    def __init__(self, emails):
        self.emails = emails   # {id: (subject, from, body)}

    def users(self):
        return self

    def messages(self):
        return self

    def list(self, userId, q, maxResults):
        ids = [i for i, (subject, _, body) in self.emails.items()
               if all(word in subject + body for word in q.split()[1:])]
        return _Result({"messages": [{"id": i} for i in ids]})

    def get(self, userId, id, format):
        subject, sender, body = self.emails[id]
        return _Result({
            "internalDate": str(RECEIVED),
            "payload": {
                "mimeType": "text/plain",
                "headers": [{"name": "Subject", "value": subject}, {"name": "From", "value": sender}],
                "body": {"data": base64.urlsafe_b64encode(body.encode()).decode()},
            },
        })


class _Result:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


@pytest.fixture
def run_parser(monkeypatch, tmp_path):
    def run(emails, existing_rows):
        worksheet = FakeWorksheet.from_rows(COLUMNS, existing_rows)
        monkeypatch.setattr(email_parser, "get_gmail_service", lambda: FakeGmail(emails))
        monkeypatch.setattr(email_parser, "get_worksheet", lambda: worksheet)
        monkeypatch.setattr(email_parser, "PROCESSED_IDS_FILE", str(tmp_path / "processed.json"))
        email_parser.run()
        return worksheet
    return run


def updates_by_cell(worksheet):
    return {u["range"]: u["values"][0][0] for w in worksheet.writes if w[0] == "batch_update" for u in w[1]}


def test_run_adds_cancels_and_modifies(run_parser):
    existing = [
        {"reference": "U2600000001", "status": "Confirmed", "guest_name": "Ancien Client",
         "email": "jean@example.com"},
        {"reference": "U2600000002", "status": "Confirmed", "guest_name": "Autre Client"},
    ]
    emails = {
        # The cancellation is listed first: it must still be applied after the new booking.
        "m1": ("Annulation | N°U2600000002", "BOOKING <no-reply@elloha.com>", "* Nom : Autre Client\n"),
        "m2": ("Nouvelle réservation | U2603113069", "BOOKING <no-reply@elloha.com>",
               BOOKING_BODY.replace("abc123@guest.booking.com", "jean@example.com")),
        "m3": ("Modification | U2600000001", "BOOKING <no-reply@elloha.com>",
               "Date d'Arrivée : 20/08/2026\nDate de Départ : 22/08/2026\nMontant total 410,00 €\n"),
    }
    worksheet = run_parser(emails, existing)

    [(_, appended)] = [w for w in worksheet.writes if w[0] == "append_row"]
    row = dict(zip(COLUMNS, appended))
    assert row["reference"] == "U2603113069"
    assert (row["repeat_guest"], row["visit_count"]) == (True, 2)   # same email as row 2

    cells = updates_by_cell(worksheet)
    assert cells["D3"] == "Cancelled"                               # status of U2600000002
    assert cells["D2"] == "Modified"                                # status of U2600000001
    assert (cells["J2"], cells["K2"]) == ("20/08/2026", "22/08/2026")
    assert float(cells["L2"]) == 410.0


def test_run_skips_already_processed_emails(run_parser):
    emails = {"m2": ("Nouvelle réservation | U2603113069", "BOOKING <no-reply@elloha.com>", BOOKING_BODY)}
    run_parser(emails, [])
    worksheet = run_parser(emails, [])   # same processed-ids file
    assert worksheet.writes == []


def test_cancellation_without_booking_email_adds_placeholder(run_parser):
    emails = {"m1": ("Annulation | N°U2600000009", "BOOKING <no-reply@elloha.com>", "* Nom : Perdu\n")}
    worksheet = run_parser(emails, [])
    [(_, appended)] = [w for w in worksheet.writes if w[0] == "append_row"]
    row = dict(zip(COLUMNS, appended))
    assert (row["booking_source"], row["status"], row["guest_name"]) == ("Unknown", "Cancelled", "Perdu")
