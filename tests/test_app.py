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
