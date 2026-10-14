"""
app.py
──────
The booking form Angela uses for bookings made by phone, email or in person.
Everything is saved straight into the Google Sheet.

    python app.py        then open http://localhost:5051

Tabs:
  room    a stay in one or more rooms
  meal    table d'hôtes or breakfast/brunch without a room
  extras  add table d'hôtes, a massage, an amount or a note to an existing booking
  email   replace a Booking.com hidden address with the guest's real email
"""
from __future__ import annotations

import logging
import os
import re
import socket
import sys
import threading
import time
import webbrowser
from datetime import date, datetime

from flask import Flask, flash, redirect, render_template, request, send_from_directory, url_for

import sheet
from auth import get_worksheet
from bookings import TABLE_DHOTES_DATES_TAG
from config import DOCS_DIR, FORM_SOURCES, MASSAGE_OPTIONS, NATIONALITIES, ROOMS, TEMPLATES_DIR
from guests import detect_repeat_guest

PORT = 5051
FORM_DATE = "%Y-%m-%d"     # what <input type="date"> sends
SHEET_DATE = "%d/%m/%Y"
LOOKS_LIKE_REFERENCE = re.compile(r"^[A-Za-z]\d")   # U2603113069, M0012, …

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__, template_folder=TEMPLATES_DIR)
app.secret_key = os.urandom(24)


@app.route("/logo.png")
def logo():
    """The farm logo shown at the top of the form (same file as on the website)."""
    return send_from_directory(DOCS_DIR, "logo.png")


# ── New booking (room and meal tabs) ──────────────────────────────────────────

@app.route("/", methods=["GET", "POST"])
def booking_form():
    if request.method == "GET":
        return _render_form(request.args.get("tab", "room"), {})

    form, tab = request.form, request.form.get("form_type", "room")
    errors = validation_errors(form, tab)
    if errors:
        return _render_form_with(errors, tab, form)

    try:
        worksheet = get_worksheet()
        _, existing = sheet.read_rows(worksheet)
    except Exception as exc:
        log.error(f"Failed to connect to Google Sheet: {exc}")
        return _render_form_with([f"Erreur de connexion au Google Sheet : {exc}"], tab, form)

    row = new_booking_row(form, tab, existing)
    conflicts = room_conflicts(row, existing) if tab == "room" else []
    if conflicts:
        return _render_form_with([f"⛔ Conflit de réservation : {c}" for c in conflicts], tab, form)

    try:
        sheet.append_row(worksheet, row)
    except Exception as exc:
        log.error(f"Failed to save booking: {exc}")
        return _render_form_with([f"Erreur lors de l'enregistrement : {exc}"], tab, form)

    log.info(f"Manual booking saved: {row['reference']} — {row['guest_name']}")
    flash(f"✓ Réservation enregistrée pour {row['guest_name']} "
          f"({row['arrival_date']} → {row['departure_date']})"
          + (" — Client fidèle ! 🌟" if row["repeat_guest"] else ""), "success")
    return _back_to(tab)


def validation_errors(form, tab: str) -> list[str]:
    """French messages for everything missing or wrong, in the order of the form."""
    errors = []
    if tab == "room" and not form.getlist("rooms"):
        errors.append("Veuillez sélectionner au moins une chambre.")
    if tab == "meal":
        if not (_ticked(form, "breakfast") or _ticked(form, "brunch") or _ticked(form, "table_dhotes")):
            errors.append("Veuillez sélectionner au moins un service repas.")
        if not form.get("guest_count", "").strip():
            errors.append("Le nombre de personnes est obligatoire pour un repas.")
    if not form.get("arrival_date", "").strip():
        errors.append("La date d'arrivée est obligatoire.")
    if tab == "room" and not form.get("departure_date", "").strip():
        errors.append("La date de départ est obligatoire.")
    if not form.get("guest_name", "").strip():
        errors.append("Le nom du client est obligatoire.")
    if not form.get("phone", "").strip():
        errors.append("Le numéro de téléphone est obligatoire.")

    if form.get("arrival_date", "").strip() and _departure_text(form, tab):
        try:
            arrival, departure = stay_dates(form, tab)
        except ValueError:
            errors.append("Format de date invalide.")
        else:
            nights = (departure - arrival).days
            if nights < 0 or (nights == 0 and tab == "room"):
                errors.append("La date de départ doit être après la date d'arrivée.")
    return errors


def stay_dates(form, tab: str) -> tuple[date, date]:
    """Arrival and departure; a meal without departure ends the day it starts."""
    arrival = datetime.strptime(form["arrival_date"].strip(), FORM_DATE).date()
    departure = datetime.strptime(_departure_text(form, tab), FORM_DATE).date()
    return arrival, departure


def new_booking_row(form, tab: str, existing: list[dict]) -> dict:
    """The Sheet row for a valid form."""
    arrival, departure = stay_dates(form, tab)
    nights = (departure - arrival).days
    rooms = form.getlist("rooms") if tab == "room" else []
    guest_count = form.get("guest_count", "").strip()
    row = {
        "booking_source":    booking_source(form, tab),
        "booking_date":      date.today().strftime(SHEET_DATE),
        "email_type":        "Booking",
        "status":            "Confirmed",
        "reference":         next_reference(existing),
        "room1":             rooms[0] if len(rooms) > 0 else "",
        "room2":             rooms[1] if len(rooms) > 1 else "",
        "room3":             rooms[2] if len(rooms) > 2 else "",
        "room4":             rooms[3] if len(rooms) > 3 else "",
        "arrival_date":      arrival.strftime(SHEET_DATE),
        "departure_date":    departure.strftime(SHEET_DATE),
        "amount":            _number(form.get("amount", "")) or 0.0,
        "guest_name":        form.get("guest_name", "").strip(),
        "phone":             form.get("phone", "").strip(),
        "email":             form.get("email", "").strip(),
        "nationality":       form.get("nationality", "").strip(),
        "nights":            nights,
        "cancellation_date": "",
        "modification_date": "",
        "notes":             notes_with_tags(form, tab, nights),
        "table_dhotes":      _ticked(form, "table_dhotes"),
        "breakfast":         _ticked(form, "breakfast") or _ticked(form, "brunch"),
        "guest_count":       max(1, int(guest_count)) if guest_count.isdigit() else "",
        "massage":           massage_choice(form),
    }
    row["repeat_guest"], row["visit_count"] = detect_repeat_guest(row, existing)
    return row


def booking_source(form, tab: str) -> str:
    """Meals are always Email/phone; rooms use the chosen source."""
    source = form.get("booking_source", "").strip()
    return source if tab == "room" and source in FORM_SOURCES else "Email/phone"


def notes_with_tags(form, tab: str, nights: int) -> str:
    """
    Notes, prefixed with the tags the schedule reads:
      meal: [☕ Brunch | 🌱 Végétalien | …]   room: [TD: 12/08/2026, 13/08/2026]
    """
    notes = form.get("notes", "").strip()
    if tab == "meal":
        tags = [label for field, label in (
            ("brunch", "☕ Brunch"), ("diet_vegan", "🌱 Végétalien"),
            ("diet_vegetarian", "🥦 Végétarien"), ("diet_gluten_free", "🌾 Sans gluten"),
            ("diet_dairy_free", "🥛 Sans lactose"),
        ) if _ticked(form, field)]
        other = form.get("diet_other", "").strip()
        if other:
            tags.append(f"⚠️ {other}")
        if tags:
            notes = f"[{' | '.join(tags)}] {notes}".strip()
    dinner_nights = form.getlist("td_dates")
    if tab == "room" and _ticked(form, "table_dhotes") and dinner_nights and nights > 1:
        notes = f"[TD: {', '.join(dinner_nights)}] {notes}".strip()
    return notes


def room_conflicts(row: dict, existing: list[dict]) -> list[str]:
    """Rooms of `row` already taken by another booking on overlapping nights."""
    arrival = datetime.strptime(row["arrival_date"], SHEET_DATE).date()
    departure = datetime.strptime(row["departure_date"], SHEET_DATE).date()
    wanted = [row[f"room{i}"] for i in range(1, 5) if row[f"room{i}"]]
    conflicts = []
    for other in existing:
        if str(other.get("status", "")).lower() == "cancelled":
            continue
        try:
            other_arrival = datetime.strptime(other["arrival_date"], SHEET_DATE).date()
            other_departure = datetime.strptime(other["departure_date"], SHEET_DATE).date()
        except (ValueError, KeyError):
            continue
        if other_arrival < departure and other_departure > arrival:
            taken = [str(other.get(f"room{i}", "") or "") for i in range(1, 5)]
            conflicts += [
                f"{room} (déjà occupée par {other.get('guest_name', '?')} "
                f"{other['arrival_date']}→{other['departure_date']})"
                for room in wanted if room in taken
            ]
    return conflicts


def next_reference(existing: list[dict]) -> str:
    """Manual bookings are numbered M0001, M0002, …"""
    numbers = [int(m.group(1)) for row in existing
               if (m := re.match(r"^M(\d+)$", str(row.get("reference") or "")))]
    return f"M{max(numbers, default=0) + 1:04d}"


# ── Extras tab ────────────────────────────────────────────────────────────────

@app.route("/update-booking", methods=["POST"])
def update_booking():
    identifier = request.form.get("identifier", "").strip()
    if not identifier:
        flash("Référence, email ou nom obligatoire.", "error")
        return _back_to("extras")

    try:
        worksheet = get_worksheet()
        headers, rows = sheet.read_rows(worksheet)
        matches = find_bookings(rows, identifier, allow_name=True)
        if not matches:
            flash(f"Aucune réservation trouvée pour « {identifier} ». "
                  "Vérifiez le Google Sheet ou essayez avec la référence exacte.", "error")
        elif len(matches) > 1:
            refs = ", ".join(str(row.get("reference", "")).strip() for _, row in matches)
            flash(f"Plusieurs réservations trouvées ({refs}). "
                  "Utilisez la référence exacte pour éviter toute erreur.", "error")
        else:
            [(sheet_row, booking)] = matches
            updates = extras_updates(request.form, booking)
            sheet.update_cells(worksheet, sheet_row, updates, headers)
            ref = str(booking.get("reference", "")).strip() or identifier
            log.info(f"Extras updated for {ref} — {updates}")
            flash(f"✓ Réservation {ref} mise à jour.", "success")
    except Exception as exc:
        log.error(f"Failed to update booking '{identifier}': {exc}")
        flash(f"Erreur lors de la mise à jour : {exc}", "error")

    return _back_to("extras")


def extras_updates(form, booking: dict) -> dict:
    """
    Cells to change. Only adds: an unticked table d'hôtes or an empty massage
    leaves the booking as it is (removing them is done in the Sheet).
    """
    updates = {}
    if _ticked(form, "table_dhotes"):
        updates["table_dhotes"] = "True"
    massage = massage_choice(form)
    if massage:
        updates["massage"] = massage
    amount = _number(form.get("amount", ""))
    if amount is not None:
        updates["amount"] = amount
    guest_count = form.get("guest_count", "").strip()
    if guest_count.isdigit():
        updates["guest_count"] = max(1, int(guest_count))

    dinner_date = form.get("td_date", "").strip()
    extra_note = form.get("notes_extra", "").strip()
    if dinner_date or extra_note:
        notes = str(booking.get("notes", "")).strip()
        if _ticked(form, "table_dhotes") and dinner_date:
            # A new table d'hôtes date replaces the existing [TD: …] tag
            try:
                night = datetime.strptime(dinner_date, FORM_DATE).strftime(SHEET_DATE)
                notes = f"[TD: {night}] {TABLE_DHOTES_DATES_TAG.sub('', notes).strip()}".strip()
            except ValueError:
                pass
        if extra_note:
            notes = f"{notes} | {extra_note}" if notes else extra_note
        updates["notes"] = notes

    updates["modification_date"] = date.today().strftime(SHEET_DATE)
    return updates


# ── Email tab ─────────────────────────────────────────────────────────────────

@app.route("/update-email", methods=["POST"])
def update_email():
    identifier = request.form.get("identifier", "").strip()
    new_email = request.form.get("new_email", "").strip()
    if not identifier or not new_email:
        flash("Identifiant et nouvelle adresse email obligatoires.", "error")
        return _back_to("email")

    try:
        worksheet = get_worksheet()
        headers, rows = sheet.read_rows(worksheet)
        matches = find_bookings(rows, identifier, allow_name=False)
        for sheet_row, _ in matches:
            sheet.update_cells(worksheet, sheet_row, {"email": new_email}, headers)
            log.info(f"Email updated ({identifier}) → {new_email}")
        if matches:
            flash(f"✓ Email mis à jour ({len(matches)} ligne{'s' if len(matches) > 1 else ''}) : "
                  f"{new_email}", "success")
        else:
            flash(f"Identifiant « {identifier} » introuvable dans le tableau.", "error")
    except Exception as exc:
        log.error(f"Failed to update email for {identifier}: {exc}")
        flash(f"Erreur lors de la mise à jour : {exc}", "error")

    return _back_to("email")


# ── Shared helpers ────────────────────────────────────────────────────────────

def find_bookings(rows: list[dict], identifier: str, allow_name: bool) -> list[tuple[int, dict]]:
    """
    (Sheet row number, row) of the bookings matching `identifier`:
      a reference  → that booking only
      an email     → every booking with that address
      a name       → every booking whose name contains it (only if allow_name)
    """
    def column(row, name):
        return str(row.get(name, "")).strip().lower()

    wanted = identifier.lower()
    numbered = [(i + sheet.FIRST_DATA_ROW, row) for i, row in enumerate(rows)]
    if LOOKS_LIKE_REFERENCE.match(identifier):
        return [match for match in numbered if column(match[1], "reference") == wanted][:1]
    if "@" in identifier or not allow_name:
        return [match for match in numbered if column(match[1], "email") == wanted]
    return [match for match in numbered if wanted in column(match[1], "guest_name")]


def massage_choice(form) -> str:
    """'Réflexologie 1h (55€) · Duo', or '' when no massage is chosen."""
    massage = form.get("massage_type", "").strip()
    if massage and _ticked(form, "massage_duo"):
        massage += " · Duo"
    return massage


def _ticked(form, checkbox: str) -> bool:
    return form.get(checkbox) == "1"


def _departure_text(form, tab: str) -> str:
    departure = form.get("departure_date", "").strip()
    return departure or (form.get("arrival_date", "").strip() if tab == "meal" else "")


def _number(text: str) -> float | None:
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        return None


def _render_form(active_tab: str, form_data) -> str:
    """The form on the given tab, refilled with form_data."""
    return render_template(
        "booking_form.html",
        rooms=ROOMS,
        nationalities=NATIONALITIES,
        form_sources=FORM_SOURCES,
        massage_options=MASSAGE_OPTIONS,
        active_tab=active_tab,
        form_data=form_data,
    )


def _render_form_with(errors: list[str], tab: str, form) -> str:
    for error in errors:
        flash(error, "error")
    return _render_form(tab, form)


def _back_to(tab: str):
    return redirect(url_for("booking_form") + f"?tab={tab}")


def _open_browser_when_ready() -> None:
    """Open the form in the browser as soon as the server answers (at most 30 s)."""
    for _ in range(60):
        try:
            socket.create_connection(("127.0.0.1", PORT), timeout=0.5).close()
            webbrowser.open(f"http://localhost:{PORT}")
            return
        except OSError:
            time.sleep(0.5)


def _local_network_address() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


if __name__ == "__main__":
    print("\n" + "═" * 50)
    print("  La Ferme de la Cour — Formulaire de Réservation")
    print("═" * 50)
    print("  Ouvrir dans le navigateur :")
    print(f"  → Sur cet appareil  : http://localhost:{PORT}")
    print(f"  → Sur le réseau Wi-Fi : http://{_local_network_address()}:{PORT}")
    print("═" * 50 + "\n")

    if "--open" in sys.argv:    # start_form.bat asks for this
        threading.Thread(target=_open_browser_when_ready, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, debug=False)
