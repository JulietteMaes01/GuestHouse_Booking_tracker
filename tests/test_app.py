"""Booking form (app.py) behaviour, with the Google Sheet replaced by a fake."""
import pytest

import app as form_app
from config import COLUMNS
from fake_sheet import FakeWorksheet

EXISTING = {
    "booking_source": "Booking.com", "status": "Confirmed", "reference": "U2604160349",
    "room1": "Léon de la Cour", "arrival_date": "10/11/2026", "departure_date": "12/11/2026",
    "amount": 250, "guest_name": "Anne Exemple", "phone": "+32470000000",
    "email": "anne@example.com", "nights": 2, "notes": "[TD: 10/11/2026] Allergie noix",
    "table_dhotes": "True", "massage": "Massage du dos 30min (30€)", "guest_count": 2,
}


@pytest.fixture
def sheet(monkeypatch):
    worksheet = FakeWorksheet.from_rows(COLUMNS, [EXISTING])
    monkeypatch.setattr(form_app, "get_worksheet", lambda: worksheet)
    return worksheet


@pytest.fixture
def client():
    return form_app.app.test_client()


def written_cells(worksheet):
    """{column name: value} for every cell written, whichever gspread call was used."""
    cells = {}
    for write in worksheet.writes:
        if write[0] == "update_cell":
            _, _row, col, value = write
            cells[COLUMNS[col - 1]] = value
        elif write[0] == "batch_update":
            for update in write[1]:
                col_letter = "".join(ch for ch in update["range"] if ch.isalpha())
                col = 0
                for ch in col_letter:
                    col = col * 26 + ord(ch) - ord("A") + 1
                cells[COLUMNS[col - 1]] = update["values"][0][0]
    return cells


# ── Extras tab ────────────────────────────────────────────────────────────────

def test_extras_amount_only_keeps_table_dhotes_and_massage(sheet, client):
    client.post("/update-booking", data={"identifier": "U2604160349", "amount": "300"})

    cells = written_cells(sheet)
    assert float(cells["amount"]) == 300
    assert "table_dhotes" not in cells
    assert "massage" not in cells


def test_extras_note_keeps_table_dhotes_dates(sheet, client):
    client.post("/update-booking", data={"identifier": "U2604160349", "notes_extra": "Arrivée tardive"})

    cells = written_cells(sheet)
    assert cells["notes"] == "[TD: 10/11/2026] Allergie noix | Arrivée tardive"


def test_extras_new_table_dhotes_date_replaces_old_one(sheet, client):
    client.post("/update-booking", data={
        "identifier": "U2604160349", "table_dhotes": "1", "td_date": "2026-11-11"})

    cells = written_cells(sheet)
    assert str(cells["table_dhotes"]) == "True"
    assert cells["notes"] == "[TD: 11/11/2026] Allergie noix"


def test_extras_adds_massage(sheet, client):
    client.post("/update-booking", data={
        "identifier": "U2604160349", "massage_type": "Réflexologie 1h (55€)", "massage_duo": "1"})

    assert written_cells(sheet)["massage"] == "Réflexologie 1h (55€) · Duo"


# ── Room tab ──────────────────────────────────────────────────────────────────

def test_conflict_page_still_lists_massages(sheet, client):
    response = client.post("/", data={
        "form_type": "room", "rooms": "Léon de la Cour",
        "arrival_date": "2026-11-11", "departure_date": "2026-11-13",
        "guest_name": "Test", "phone": "0470000000"})

    page = response.get_data(as_text=True)
    assert "Conflit de réservation" in page
    assert "Réflexologie 1h (55€)" in page
    assert not [w for w in sheet.writes if w[0] == "append_row"]


# ── Exact rows written (pinned before the app.py restructure) ────────────────

from freezegun import freeze_time


def appended_row(worksheet):
    [(_, values)] = [w for w in worksheet.writes if w[0] == "append_row"]
    return dict(zip(COLUMNS, values))


@freeze_time("2026-10-14 10:00:00")
def test_room_booking_row(sheet, client):
    client.post("/", data={
        "form_type": "room", "booking_source": "Social Deal",
        "rooms": ["Odette de la Cour", "Tibert de la Cour"],
        "arrival_date": "2026-12-01", "departure_date": "2026-12-04",
        "guest_name": "Paul Test", "phone": "+32 470 00 00 00", "email": "anne@example.com",
        "nationality": "Belgique", "amount": "420,50", "notes": "Chien",
        "table_dhotes": "1", "td_dates": ["01/12/2026", "03/12/2026"], "breakfast": "1",
        "guest_count": "3", "massage_type": "Massage du dos 45min (45€)", "massage_duo": "1"})

    assert appended_row(sheet) == {
        "booking_source": "Social Deal", "booking_date": "14/10/2026", "email_type": "Booking",
        "status": "Confirmed", "reference": "M0001",
        "room1": "Odette de la Cour", "room2": "Tibert de la Cour", "room3": "", "room4": "",
        "arrival_date": "01/12/2026", "departure_date": "04/12/2026", "amount": 420.5,
        "guest_name": "Paul Test", "phone": "+32 470 00 00 00", "email": "anne@example.com",
        "nationality": "Belgique", "nights": 3, "cancellation_date": "", "modification_date": "",
        "notes": "[TD: 01/12/2026, 03/12/2026] Chien", "repeat_guest": True, "visit_count": 2,
        "table_dhotes": True, "breakfast": True, "guest_count": 3,
        "massage": "Massage du dos 45min (45€) · Duo", "cabane": "", "plats": "",
    }


@freeze_time("2026-10-14 10:00:00")
def test_meal_booking_row(sheet, client):
    client.post("/", data={
        "form_type": "meal", "booking_source": "Umfulana",   # ignored: meals are Email/phone
        "brunch": "1", "diet_vegan": "1", "diet_gluten_free": "1", "diet_other": "noix",
        "arrival_date": "2026-11-20", "guest_count": "6",
        "guest_name": "Groupe Test", "phone": "0470000000", "notes": "Anniversaire"})

    row = appended_row(sheet)
    assert (row["booking_source"], row["arrival_date"], row["departure_date"], row["nights"]) == \
        ("Email/phone", "20/11/2026", "20/11/2026", 0)
    assert (row["breakfast"], row["table_dhotes"], row["guest_count"]) == (True, False, 6)
    assert row["notes"] == "[☕ Brunch | 🌱 Végétalien | 🌾 Sans gluten | ⚠️ noix] Anniversaire"
    assert row["room1"] == ""


def test_missing_fields_are_listed_and_nothing_is_saved(sheet, client):
    page = client.post("/", data={"form_type": "room"}).get_data(as_text=True)
    for message in ("au moins une chambre", "date d&#39;arrivée est obligatoire",
                    "date de départ est obligatoire", "nom du client", "téléphone"):
        assert message in page
    assert sheet.writes == []


def test_departure_before_arrival_is_refused(sheet, client):
    page = client.post("/", data={
        "form_type": "room", "rooms": "Léon de la Cour", "arrival_date": "2026-12-04",
        "departure_date": "2026-12-01", "guest_name": "X", "phone": "1"}).get_data(as_text=True)
    assert "La date de départ doit être après la date d&#39;arrivée." in page
    assert sheet.writes == []


def test_update_email_by_reference(sheet, client):
    client.post("/update-email", data={"identifier": "u2604160349", "new_email": "vrai@example.com"})
    assert written_cells(sheet) == {"email": "vrai@example.com"}


def test_update_email_by_booking_com_address(monkeypatch, client):
    rows = [{"reference": "U1", "email": "abc@guest.booking.com"},
            {"reference": "U2", "email": "abc@guest.booking.com"}]
    worksheet = FakeWorksheet.from_rows(COLUMNS, rows)
    monkeypatch.setattr(form_app, "get_worksheet", lambda: worksheet)
    client.post("/update-email", data={"identifier": "abc@guest.booking.com", "new_email": "vrai@example.com"})
    rows_written = sorted(
        [w[1] for w in worksheet.writes if w[0] == "update_cell"]
        + [int("".join(c for c in u["range"] if c.isdigit())) for w in worksheet.writes
           if w[0] == "batch_update" for u in w[1]])
    assert rows_written == [2, 3]


def test_extras_by_partial_name_must_be_unique(monkeypatch, client):
    rows = [{"reference": "U1", "guest_name": "Anne Dupont"}, {"reference": "U2", "guest_name": "Marc Dupont"}]
    worksheet = FakeWorksheet.from_rows(COLUMNS, rows)
    monkeypatch.setattr(form_app, "get_worksheet", lambda: worksheet)
    page = client.post("/update-booking", data={"identifier": "dupont", "amount": "1"},
                       follow_redirects=True).get_data(as_text=True)
    assert "Plusieurs réservations trouvées (U1, U2)" in page
    assert worksheet.writes == []


@freeze_time("2026-10-14 10:00:00")
def test_extras_marks_modification_date(sheet, client):
    client.post("/update-booking", data={"identifier": "Anne", "guest_count": "4"})
    cells = written_cells(sheet)
    assert (int(cells["guest_count"]), cells["modification_date"]) == (4, "14/10/2026")


def test_form_serves_the_logo(client):
    response = client.get("/logo.png")
    assert response.status_code == 200
    assert response.mimetype == "image/png"


def test_browser_opens_once_the_form_answers(monkeypatch):
    opened = []
    monkeypatch.setattr(form_app.socket, "create_connection", lambda *a, **k: type("C", (), {"close": lambda self: None})())
    monkeypatch.setattr(form_app.webbrowser, "open", opened.append)
    form_app._open_browser_when_ready()
    assert opened == ["http://localhost:5051"]


# ── Cabin tab ─────────────────────────────────────────────────────────────────

@freeze_time("2026-10-14 10:00:00")
def test_cabin_delivery_row(sheet, client):
    client.post("/", data={
        "form_type": "cabin", "cabane": "Tanière des Nutons", "arrival_date": "2026-10-20",
        "guest_count": "4", "plats": "2 lasagnes\r\n2 tiramisus", "amount": "68", "notes": "Sans noix"})

    row = appended_row(sheet)
    assert (row["cabane"], row["plats"]) == ("Tanière des Nutons", "2 lasagnes\n2 tiramisus")
    assert (row["arrival_date"], row["departure_date"], row["nights"]) == ("20/10/2026", "20/10/2026", 0)
    assert (row["guest_count"], row["amount"], row["notes"]) == (4, 68.0, "Sans noix")
    assert (row["room1"], row["guest_name"], row["phone"]) == ("", "", "")
    assert (row["table_dhotes"], row["breakfast"], row["booking_source"]) == (False, False, "Email/phone")


def test_cabin_delivery_needs_cabin_dishes_date_and_people(sheet, client):
    page = client.post("/", data={"form_type": "cabin", "cabane": "Pas une cabane"}).get_data(as_text=True)
    for message in ("choisir la cabane", "plats à livrer", "nombre de personnes", "date de livraison"):
        assert message in page
    assert "nom du client est obligatoire" not in page and "téléphone est obligatoire" not in page
    assert sheet.writes == []


def test_form_lists_the_cabins(client):
    page = client.get("/?tab=cabin").get_data(as_text=True)
    assert "Couleurs du monde" in page and 'id="panel-cabin"' in page
