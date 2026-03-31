"""
app.py
──────
Simple Flask web form for adding manual (phone/direct) bookings to the
Google Sheet.

Run:
    python app.py

Then open  http://localhost:5051  in any browser on the same device.
To access from another device on the same Wi-Fi, use the printed local URL.
"""
import os
import re
import logging
from datetime import datetime, date

from flask import Flask, render_template, request, redirect, url_for, flash

from auth import get_worksheet
from config import ROOMS, NATIONALITIES, COLUMNS
from email_parser import detect_repeat_guest

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
log = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(__name__,
            template_folder=os.path.join(_REPO_ROOT, "templates"),
            static_folder=_REPO_ROOT)
app.secret_key = os.urandom(24)


def generate_reference(worksheet) -> str:
    """
    Generate a sequential manual reference: M0001, M0002, …
    Scans the sheet for the highest existing M#### reference and increments by 1.
    """
    records = worksheet.get_all_records()
    max_num = 0
    for rec in records:
        ref = str(rec.get("reference") or "")
        m = re.match(r"^M(\d+)$", ref)
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"M{max_num + 1:04d}"


def row_dict_to_list(row: dict) -> list:
    return [row.get(col, "") for col in COLUMNS]


@app.route("/", methods=["GET", "POST"])
def booking_form():
    if request.method == "POST":
        rooms_selected = request.form.getlist("rooms")
        arrival_str    = request.form.get("arrival_date", "").strip()
        departure_str  = request.form.get("departure_date", "").strip()
        guest_name     = request.form.get("guest_name", "").strip()
        phone          = request.form.get("phone", "").strip()
        guest_email    = request.form.get("email", "").strip()
        nationality    = request.form.get("nationality", "").strip()
        amount_str     = request.form.get("amount", "").strip()
        notes          = request.form.get("notes", "").strip()
        table_dhotes   = request.form.get("table_dhotes") == "1"

        # ── Validation ────────────────────────────────────────────────────────
        errors = []
        if not rooms_selected:
            errors.append("Veuillez sélectionner au moins une chambre.")
        if not arrival_str or not departure_str:
            errors.append("Les dates d'arrivée et de départ sont obligatoires.")
        if not guest_name:
            errors.append("Le nom du client est obligatoire.")
        if not phone:
            errors.append("Le numéro de téléphone est obligatoire.")

        arrival_date = departure_date = None
        nights = 0
        if arrival_str and departure_str:
            try:
                arrival_date   = datetime.strptime(arrival_str,   "%Y-%m-%d").date()
                departure_date = datetime.strptime(departure_str, "%Y-%m-%d").date()
                nights = (departure_date - arrival_date).days
                if nights <= 0:
                    errors.append("La date de départ doit être après la date d'arrivée.")
            except ValueError:
                errors.append("Format de date invalide.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "booking_form.html",
                rooms=ROOMS,
                nationalities=NATIONALITIES,
                form_data=request.form,
            )

        # ── Build row ─────────────────────────────────────────────────────────
        amount = 0.0
        if amount_str:
            try:
                amount = float(amount_str.replace(",", "."))
            except ValueError:
                pass

        arrival_fmt   = arrival_date.strftime("%d/%m/%Y")
        departure_fmt = departure_date.strftime("%d/%m/%Y")

        # ── Connect to sheet (needed for reference + repeat-guest check) ────────
        try:
            ws      = get_worksheet()
            records = ws.get_all_records()
        except Exception as exc:
            log.error(f"Failed to connect to Google Sheet: {exc}")
            flash(f"Erreur de connexion au Google Sheet : {exc}", "error")
            return render_template(
                "booking_form.html",
                rooms=ROOMS,
                nationalities=NATIONALITIES,
                form_data=request.form,
            )

        row = {
            "booking_source":    "Manual",
            "booking_date":      date.today().strftime("%d/%m/%Y"),
            "email_type":        "Booking",
            "status":            "Confirmed",
            "reference":         generate_reference(ws),
            "room1":             rooms_selected[0] if len(rooms_selected) > 0 else "",
            "room2":             rooms_selected[1] if len(rooms_selected) > 1 else "",
            "room3":             rooms_selected[2] if len(rooms_selected) > 2 else "",
            "room4":             rooms_selected[3] if len(rooms_selected) > 3 else "",
            "arrival_date":      arrival_fmt,
            "departure_date":    departure_fmt,
            "amount":            amount,
            "guest_name":        guest_name,
            "phone":             phone,
            "email":             guest_email,
            "nationality":       nationality,
            "nights":            nights,
            "cancellation_date": "",
            "modification_date": "",
            "notes":             notes,
            "repeat_guest":      False,
            "visit_count":       1,
            "table_dhotes":      table_dhotes,
        }

        # ── Repeat-guest detection ────────────────────────────────────────────
        try:
            row["repeat_guest"], row["visit_count"] = detect_repeat_guest(row, records)

            ws.append_row(row_dict_to_list(row), value_input_option="RAW")
            log.info(f"Manual booking saved: {row['reference']} — {guest_name}")

            flash(
                f"✓ Réservation enregistrée pour {guest_name} "
                f"({arrival_fmt} → {departure_fmt})"
                + (" — Client fidèle ! 🌟" if row["repeat_guest"] else ""),
                "success",
            )
            return redirect(url_for("booking_form"))

        except Exception as exc:
            log.error(f"Failed to save booking: {exc}")
            flash(f"Erreur lors de l'enregistrement : {exc}", "error")

    return render_template(
        "booking_form.html",
        rooms=ROOMS,
        nationalities=NATIONALITIES,
        form_data={},
    )


if __name__ == "__main__":
    import socket

    # Print local network URL so it can be opened from another device
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = "127.0.0.1"

    print("\n" + "═" * 50)
    print("  La Ferme de la Cour — Formulaire de Réservation")
    print("═" * 50)
    print(f"  Ouvrir dans le navigateur :")
    print(f"  → Sur cet appareil  : http://localhost:5051")
    print(f"  → Sur le réseau Wi-Fi : http://{local_ip}:5051")
    print("═" * 50 + "\n")

    app.run(host="0.0.0.0", port=5051, debug=False)
