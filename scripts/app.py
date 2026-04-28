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
from config import ROOMS, NATIONALITIES, COLUMNS, MASSAGE_OPTIONS

MANUAL_SOURCES = ["Email/phone", "Social Deal", "Umfulana"]

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


def _normalize_phone(phone) -> str:
    """Strip all non-digit characters."""
    return re.sub(r"\D", "", str(phone or ""))


def detect_repeat_guest(new_row: dict, existing_records: list) -> tuple:
    """Return (is_repeat, visit_count) by matching on email or normalised phone."""
    new_email = str(new_row.get("email") or "").lower()
    new_phone = _normalize_phone(new_row.get("phone") or "")
    use_email = (bool(new_email)
                 and "@guest.booking.com" not in new_email
                 and "@m.expediapartnercentral.com" not in new_email)

    matches   = 0
    seen_refs = set()

    for rec in existing_records:
        ref = str(rec.get("reference") or "")
        if ref in seen_refs:
            continue
        seen_refs.add(ref)
        existing_email = str(rec.get("email") or "").lower()
        existing_phone = _normalize_phone(rec.get("phone") or "")
        if use_email and existing_email and existing_email == new_email:
            matches += 1
        elif (new_phone and existing_phone
              and existing_phone == new_phone
              and len(set(new_phone)) > 1
              and len(set(existing_phone)) > 1):
            matches += 1

    return matches > 0, matches + 1


@app.route("/", methods=["GET", "POST"])
def booking_form():
    active_tab = request.args.get("tab", "room")

    if request.method == "POST":
        form_type      = request.form.get("form_type", "room")
        active_tab     = form_type  # stay on the same tab if there are errors
        rooms_selected = request.form.getlist("rooms")
        arrival_str    = request.form.get("arrival_date", "").strip()
        departure_str  = request.form.get("departure_date", "").strip()
        guest_name     = request.form.get("guest_name", "").strip()
        phone          = request.form.get("phone", "").strip()
        guest_email    = request.form.get("email", "").strip()
        nationality    = request.form.get("nationality", "").strip()
        amount_str     = request.form.get("amount", "").strip()
        notes          = request.form.get("notes", "").strip()
        table_dhotes      = request.form.get("table_dhotes") == "1"
        brunch            = request.form.get("brunch") == "1"
        breakfast         = request.form.get("breakfast") == "1" or brunch
        guest_count_str   = request.form.get("guest_count", "").strip()
        try:
            guest_count = max(1, int(guest_count_str)) if guest_count_str else ""
        except ValueError:
            guest_count = ""

        massage_type = request.form.get("massage_type", "").strip()
        massage_duo  = request.form.get("massage_duo") == "1"
        massage      = (massage_type + (" · Duo" if massage_duo else "")) if massage_type else ""

        # Meal form always uses Email/phone (no source selector in that tab)
        if form_type == "meal":
            booking_source = "Email/phone"
        else:
            booking_source = request.form.get("booking_source", "Email/phone").strip()
            if booking_source not in MANUAL_SOURCES:
                booking_source = "Email/phone"

        # ── Dietary / service notes (meal form only) ──────────────────────────
        if form_type == "meal":
            diet_parts = []
            if brunch:
                diet_parts.append("☕ Brunch")
            if request.form.get("diet_vegan")       == "1": diet_parts.append("🌱 Végétalien")
            if request.form.get("diet_vegetarian")  == "1": diet_parts.append("🥦 Végétarien")
            if request.form.get("diet_gluten_free") == "1": diet_parts.append("🌾 Sans gluten")
            if request.form.get("diet_dairy_free")  == "1": diet_parts.append("🥛 Sans lactose")
            diet_other = request.form.get("diet_other", "").strip()
            if diet_other:
                diet_parts.append(f"⚠️ {diet_other}")
            if diet_parts:
                prefix = "[" + " | ".join(diet_parts) + "]"
                notes  = f"{prefix} {notes}".strip()

        # ── Validation ────────────────────────────────────────────────────────
        errors = []
        if form_type == "room":
            if not rooms_selected:
                errors.append("Veuillez sélectionner au moins une chambre.")
        else:  # meal
            if not (breakfast or table_dhotes):
                errors.append("Veuillez sélectionner au moins un service repas.")
            if not guest_count_str:
                errors.append("Le nombre de personnes est obligatoire pour un repas.")
        if not arrival_str:
            errors.append("La date d'arrivée est obligatoire.")
        if form_type == "room" and not departure_str:
            errors.append("La date de départ est obligatoire.")
        if not guest_name:
            errors.append("Le nom du client est obligatoire.")
        if not phone:
            errors.append("Le numéro de téléphone est obligatoire.")

        # Meal: no departure → same day as arrival
        if form_type == "meal" and not departure_str:
            departure_str = arrival_str

        arrival_date = departure_date = None
        nights = 0
        if arrival_str and departure_str:
            try:
                arrival_date   = datetime.strptime(arrival_str,   "%Y-%m-%d").date()
                departure_date = datetime.strptime(departure_str, "%Y-%m-%d").date()
                nights = (departure_date - arrival_date).days
                if nights < 0:
                    errors.append("La date de départ doit être après la date d'arrivée.")
                elif nights == 0 and form_type == "room":
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
                manual_sources=MANUAL_SOURCES,
                massage_options=MASSAGE_OPTIONS,
                active_tab=active_tab,
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

        # ── Connect to sheet ──────────────────────────────────────────────────
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
                manual_sources=MANUAL_SOURCES,
                massage_options=MASSAGE_OPTIONS,
                active_tab=active_tab,
                form_data=request.form,
            )

        row = {
            "booking_source":    booking_source,
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
            "breakfast":         breakfast,
            "guest_count":       guest_count,
            "massage":           massage,
        }

        # ── Double-booking check (room bookings only) ────────────────────────
        if form_type == "room" and rooms_selected and arrival_date and departure_date:
            conflicts = []
            for rec in records:
                if str(rec.get("status", "")).lower() == "cancelled":
                    continue
                try:
                    rec_arr = datetime.strptime(rec["arrival_date"],   "%d/%m/%Y").date()
                    rec_dep = datetime.strptime(rec["departure_date"], "%d/%m/%Y").date()
                except (ValueError, KeyError):
                    continue
                # Overlap: [arr, dep) intervals intersect when arr < other_dep AND dep > other_arr
                if rec_arr < departure_date and rec_dep > arrival_date:
                    booked_rooms = [str(rec.get(f"room{i}", "") or "") for i in range(1, 5)]
                    for room in rooms_selected:
                        if room in booked_rooms:
                            conflicts.append(
                                f"{room} (déjà occupée par {rec.get('guest_name', '?')} "
                                f"{rec['arrival_date']}→{rec['departure_date']})"
                            )
            if conflicts:
                for c in conflicts:
                    flash(f"⛔ Conflit de réservation : {c}", "error")
                return render_template(
                    "booking_form.html",
                    rooms=ROOMS,
                    nationalities=NATIONALITIES,
                    manual_sources=MANUAL_SOURCES,
                    active_tab=active_tab,
                    form_data=request.form,
                )

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
            return redirect(url_for("booking_form") + f"?tab={form_type}")

        except Exception as exc:
            log.error(f"Failed to save booking: {exc}")
            flash(f"Erreur lors de l'enregistrement : {exc}", "error")

    return render_template(
        "booking_form.html",
        rooms=ROOMS,
        nationalities=NATIONALITIES,
        manual_sources=MANUAL_SOURCES,
        massage_options=MASSAGE_OPTIONS,
        active_tab=active_tab,
        form_data={},
    )


@app.route("/update-email", methods=["POST"])
def update_email():
    identifier = request.form.get("identifier", "").strip()
    new_email  = request.form.get("new_email",  "").strip()

    if not identifier or not new_email:
        flash("Identifiant et nouvelle adresse email obligatoires.", "error")
        return redirect(url_for("booking_form") + "?tab=email")

    # Decide search mode: if identifier looks like a booking reference (letter + digits), search
    # by reference column; otherwise treat it as a (Booking.com) email address to search by.
    search_by_ref = bool(re.match(r'^[A-Za-z]\d', identifier))

    try:
        ws         = get_worksheet()
        all_values = ws.get_all_values()
        if not all_values:
            flash("Tableau vide — impossible de mettre à jour.", "error")
            return redirect(url_for("booking_form") + "?tab=email")

        headers   = all_values[0]
        ref_col   = headers.index("reference") if "reference" in headers else None
        email_col = headers.index("email")     if "email"     in headers else None

        if ref_col is None or email_col is None:
            flash("Colonnes 'reference' ou 'email' introuvables dans le tableau.", "error")
            return redirect(url_for("booking_form") + "?tab=email")

        updated = 0
        for row_idx, row in enumerate(all_values[1:], start=2):
            if search_by_ref:
                cell_val = row[ref_col].strip().upper() if len(row) > ref_col else ""
                match    = (cell_val == identifier.upper())
            else:
                cell_val = row[email_col].strip().lower() if len(row) > email_col else ""
                match    = (cell_val == identifier.lower())

            if match:
                ws.update_cell(row_idx, email_col + 1, new_email)  # gspread is 1-indexed
                log.info(f"Email updated ({identifier}) → {new_email}")
                updated += 1
                if search_by_ref:
                    break  # reference is unique — stop after first match

        if updated:
            flash(
                f"✓ Email mis à jour ({updated} ligne{'s' if updated > 1 else ''}) : {new_email}",
                "success",
            )
        else:
            flash(f"Identifiant « {identifier} » introuvable dans le tableau.", "error")

    except Exception as exc:
        log.error(f"Failed to update email for {identifier}: {exc}")
        flash(f"Erreur lors de la mise à jour : {exc}", "error")

    return redirect(url_for("booking_form") + "?tab=email")


@app.route("/update-booking", methods=["POST"])
def update_booking():
    identifier      = request.form.get("identifier", "").strip()
    table_dhotes    = request.form.get("table_dhotes") == "1"
    massage_type    = request.form.get("massage_type", "").strip()
    massage_duo     = request.form.get("massage_duo") == "1"
    massage         = (massage_type + (" · Duo" if massage_duo else "")) if massage_type else ""
    guest_count_str = request.form.get("guest_count", "").strip()
    notes_extra     = request.form.get("notes_extra", "").strip()

    if not identifier:
        flash("Référence, email ou nom obligatoire.", "error")
        return redirect(url_for("booking_form") + "?tab=extras")

    # Determine search mode
    if re.match(r'^[A-Za-z]\d', identifier):
        search_mode = "reference"
    elif "@" in identifier:
        search_mode = "email"
    else:
        search_mode = "name"

    try:
        ws         = get_worksheet()
        all_values = ws.get_all_values()
        if not all_values:
            flash("Tableau vide — impossible de mettre à jour.", "error")
            return redirect(url_for("booking_form") + "?tab=extras")

        headers     = all_values[0]
        ref_col     = headers.index("reference")         if "reference"         in headers else None
        name_col    = headers.index("guest_name")        if "guest_name"        in headers else None
        email_col   = headers.index("email")             if "email"             in headers else None
        td_col      = headers.index("table_dhotes")      if "table_dhotes"      in headers else None
        massage_col = headers.index("massage")           if "massage"           in headers else None
        gc_col      = headers.index("guest_count")       if "guest_count"       in headers else None
        notes_col   = headers.index("notes")             if "notes"             in headers else None
        mod_col     = headers.index("modification_date") if "modification_date" in headers else None

        # Find matching rows
        matches = []
        for row_idx, row in enumerate(all_values[1:], start=2):
            if search_mode == "reference":
                val = row[ref_col].strip().upper() if ref_col is not None and len(row) > ref_col else ""
                if val == identifier.upper():
                    matches.append((row_idx, row))
                    break  # reference is unique
            elif search_mode == "email":
                val = row[email_col].strip().lower() if email_col is not None and len(row) > email_col else ""
                if val == identifier.lower():
                    matches.append((row_idx, row))
            else:  # name — partial, case-insensitive
                val = row[name_col].strip().lower() if name_col is not None and len(row) > name_col else ""
                if identifier.lower() in val:
                    matches.append((row_idx, row))

        if not matches:
            flash(
                f"Aucune réservation trouvée pour « {identifier} ». "
                "Vérifiez le Google Sheet ou essayez avec la référence exacte.",
                "error",
            )
            return redirect(url_for("booking_form") + "?tab=extras")

        if len(matches) > 1:
            refs = ", ".join(
                row[ref_col].strip() for _, row in matches
                if ref_col is not None and len(row) > ref_col
            )
            flash(
                f"Plusieurs réservations trouvées ({refs}). "
                "Utilisez la référence exacte pour éviter toute erreur.",
                "error",
            )
            return redirect(url_for("booking_form") + "?tab=extras")

        row_idx, matched_row = matches[0]
        ref_display = matched_row[ref_col].strip() if ref_col is not None and len(matched_row) > ref_col else identifier

        if td_col is not None:
            ws.update_cell(row_idx, td_col + 1, str(table_dhotes))
        if massage_col is not None:
            ws.update_cell(row_idx, massage_col + 1, massage)
        if gc_col is not None and guest_count_str:
            try:
                ws.update_cell(row_idx, gc_col + 1, max(1, int(guest_count_str)))
            except ValueError:
                pass
        if notes_col is not None and notes_extra:
            existing  = matched_row[notes_col].strip() if len(matched_row) > notes_col else ""
            new_notes = f"{existing} | {notes_extra}".strip(" |") if existing else notes_extra
            ws.update_cell(row_idx, notes_col + 1, new_notes)
        if mod_col is not None:
            ws.update_cell(row_idx, mod_col + 1, date.today().strftime("%d/%m/%Y"))
        log.info(f"Extras updated for {ref_display} — td={table_dhotes}, massage={massage!r}")
        flash(f"✓ Réservation {ref_display} mise à jour.", "success")

    except Exception as exc:
        log.error(f"Failed to update booking '{identifier}': {exc}")
        flash(f"Erreur lors de la mise à jour : {exc}", "error")

    return redirect(url_for("booking_form") + "?tab=extras")


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
