"""
schedule_generator.py
─────────────────────
Reads the Google Sheet, generates:
  • docs/index.html        — today's room-by-room schedule
  • docs/weekly.html       — this week's summary (revenue, occupancy, …)
Then commits and pushes both files to GitHub so GitHub Pages updates.

Usage:
    python schedule_generator.py           # generate + git push
    python schedule_generator.py --no-git  # generate only (used by GitHub Actions)
"""
import os
import sys
import shutil
import subprocess
import logging
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("Europe/Brussels")

import pandas as pd

from auth import get_worksheet
from config import (ROOMS, GITHUB_REPO_PATH, DOCS_FOLDER, OWNER_NAME,
                    PREPAID_SOURCES, SPLIT_PAYMENT_SOURCES, BREAKFAST_AUTO_SOURCES,
                    SOURCE_ALIASES)

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
log = logging.getLogger(__name__)

# ── Country flag emojis ────────────────────────────────────────────────────────
FLAG = {
    "belgique": "🇧🇪", "belgium": "🇧🇪",
    "france": "🇫🇷",
    "pays-bas": "🇳🇱", "netherlands": "🇳🇱",
    "allemagne": "🇩🇪", "germany": "🇩🇪",
    "luxembourg": "🇱🇺",
    "royaume-uni": "🇬🇧", "united kingdom": "🇬🇧", "uk": "🇬🇧",
    "espagne": "🇪🇸", "spain": "🇪🇸",
    "italie": "🇮🇹", "italy": "🇮🇹",
    "suisse": "🇨🇭", "switzerland": "🇨🇭",
    "autriche": "🇦🇹", "austria": "🇦🇹",
    "portugal": "🇵🇹",
    "irlande": "🇮🇪", "ireland": "🇮🇪",
    "danemark": "🇩🇰", "denmark": "🇩🇰",
    "suède": "🇸🇪", "sweden": "🇸🇪",
    "norvège": "🇳🇴", "norway": "🇳🇴",
    "pologne": "🇵🇱", "poland": "🇵🇱",
    "hongrie": "🇭🇺", "hungary": "🇭🇺",
    "états-unis": "🇺🇸", "united states": "🇺🇸", "usa": "🇺🇸",
}

DAYS_FR   = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MONTHS_FR = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
             "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]

CSS = """
:root {
    --primary:    #4A5D4E;
    --secondary:  #7A8C7E;
    --accent:     #D4A373;
    --text:       #2C2C2C;
    --bg:         #F1EFE7;
    --card-bg:    #fff;
    --shadow:     0 4px 6px rgba(0,0,0,.1);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', Tahoma, Verdana, sans-serif;
       background: var(--bg); color: var(--text); line-height: 1.6; }
header { background: var(--primary); color: #fff; padding: 20px;
         text-align: center; border-radius: 0 0 12px 12px; box-shadow: var(--shadow); }
header img  { max-height: 70px; margin-bottom: 8px; display: block; margin-inline: auto; }
header h1   { font-size: 1.6rem; }
header .sub { font-style: italic; font-size: .95rem; opacity: .85; margin-top: 4px; }
.container  { max-width: 900px; margin: 24px auto; padding: 0 16px; }
.section-title { color: var(--primary); font-size: .8rem; font-weight: 700;
                 text-transform: uppercase; letter-spacing: 1.5px;
                 margin: 28px 0 12px; border-bottom: 2px solid var(--accent); padding-bottom: 4px; }
.card { background: var(--card-bg); border-radius: 10px; padding: 16px;
        margin-bottom: 14px; box-shadow: var(--shadow); border-left: 5px solid #ccc; }
.card.arrival   { border-left-color: #D4A373; }
.card.departure { border-left-color: #8B6355; }
.card.staying   { border-left-color: #4A5D4E; }
.card.turnover  { border-left-color: #7A8C7E; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 20px;
         font-size: .75rem; font-weight: 700; margin-bottom: 8px; }
.badge.arrival   { background: #FAF0E6; color: #A0622A; }
.badge.departure { background: #F5EDEA; color: #6B4033; }
.badge.staying   { background: #EBF0EC; color: #2C3D30; }
.badge.turnover  { background: #EEF2EF; color: #4A5D4E; }
.guest-name  { font-size: 1.15rem; font-weight: 700; margin-bottom: 6px; }
.repeat-tag  { background: #F5EDD8; color: #8B6220; font-size: .72rem;
               padding: 2px 8px; border-radius: 12px; margin-left: 8px; vertical-align: middle; }
.info-grid   { display: grid; grid-template-columns: auto 1fr; gap: 2px 12px;
               font-size: .88rem; margin-top: 6px; }
.info-label  { color: var(--secondary); font-weight: 600; white-space: nowrap; }
.info-value  { color: var(--text); }
.notes-box   { background: #F5F0E8; border-radius: 6px; padding: 8px 12px;
               margin-top: 10px; font-style: italic; font-size: .85rem; color: #4A5D4E; }
.action-box  { background: #FDF3E8; border-radius: 6px; padding: 8px 12px;
               margin-top: 10px; font-weight: 700; font-size: .85rem; color: #7A4A1E; }
.empty-msg   { text-align: center; padding: 48px; color: var(--secondary);
               font-style: italic; font-size: 1.1rem; }
/* Weekly stats */
.stat-grid   { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
               gap: 14px; margin-bottom: 20px; }
.stat-card   { background: var(--card-bg); border-radius: 10px; padding: 16px;
               box-shadow: var(--shadow); text-align: center; }
.stat-value  { font-size: 1.8rem; font-weight: 700; color: var(--primary); }
.stat-label  { font-size: .8rem; color: var(--secondary); margin-top: 4px; }
table        { width: 100%; border-collapse: collapse; font-size: .88rem; }
th, td       { padding: 8px 12px; border-bottom: 1px solid #D4C9BC; text-align: left; }
th           { background: var(--primary); color: #fff; }
tr:hover     { background: #F1EFE7; }
.occ-bar     { display: inline-block; height: 8px; background: var(--primary);
               border-radius: 4px; vertical-align: middle; margin-right: 6px; }
footer       { text-align: center; color: #A8B8AC; font-size: .78rem;
               margin: 32px 0 16px; }
nav          { display: flex; justify-content: center; background: var(--card-bg);
               border-bottom: 2px solid var(--accent); margin-bottom: 0;
               overflow-x: auto; -webkit-overflow-scrolling: touch; }
nav a        { color: var(--secondary); text-decoration: none; padding: 12px 16px;
               font-weight: 600; font-size: .85rem; border-bottom: 3px solid transparent;
               margin-bottom: -2px; transition: color .15s; white-space: nowrap; flex-shrink: 0; }
nav a:hover  { color: var(--primary); }
nav a.active { color: var(--primary); border-bottom-color: var(--primary); }
@media (max-width: 520px) {
    header h1   { font-size: 1.2rem; }
    .info-grid  { grid-template-columns: 1fr; }
    nav a       { padding: 10px 11px; font-size: .78rem; }
}
"""

# ── Room identities ────────────────────────────────────────────────────────────
ROOM_IDENTITY = {
    "Laurasie de la Cour": {"emoji": "🐴", "bg": "#F5E0E3", "color": "#7A3040"},  # rose/pink
    "Tibert de la Cour":   {"emoji": "🦌", "bg": "#FAE8DC", "color": "#7A3F2E"},  # warm orange (unchanged)
    "Léon de la Cour":     {"emoji": "🦚", "bg": "#DDE8E5", "color": "#2A4A44"},  # blue-green
    "Odette de la Cour":   {"emoji": "🦢", "bg": "#F5F2EE", "color": "#4A3828"},  # off-white
}

def room_badge_html(rooms_str: str) -> str:
    """Return one coloured pill per room in rooms_str."""
    badges = []
    for room in [r.strip() for r in rooms_str.split(",")]:
        ident = ROOM_IDENTITY.get(room, {"emoji": "🛏", "bg": "#F1EFE7", "color": "#4A5D4E"})
        short = room.replace(" de la Cour", "")
        badges.append(
            f'<span style="display:inline-flex;align-items:center;gap:5px;'
            f'background:{ident["bg"]};color:{ident["color"]};'
            f'padding:5px 14px;border-radius:20px;font-size:.9rem;font-weight:700;'
            f'margin:6px 4px 10px 0;">'
            f'{ident["emoji"]} {short}</span>'
        )
    return "".join(badges)


# ── Data loading ───────────────────────────────────────────────────────────────

def load_data() -> pd.DataFrame:
    log.info("Loading data from Google Sheets …")
    ws   = get_worksheet()
    data = ws.get_all_records()
    df   = pd.DataFrame(data)

    if df.empty:
        return df

    for col in ("arrival_date", "departure_date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="%d/%m/%Y", errors="coerce")

    # Only active bookings
    df = df[~df["status"].str.lower().isin(["cancelled"])]

    # Normalize legacy source labels (e.g. "Manual" → "Email/phone")
    if "booking_source" in df.columns:
        df["booking_source"] = df["booking_source"].replace(SOURCE_ALIASES)

    return df


# ── Formatting helpers ─────────────────────────────────────────────────────────

def fmt_date(d: date) -> str:
    return f"{DAYS_FR[d.weekday()]} {d.day} {MONTHS_FR[d.month]} {d.year}"


def flag_for(nationality: str) -> str:
    return FLAG.get((nationality or "").lower().strip(), "🌍")


def get_rooms_for_booking(row) -> str:
    parts = []
    for col in ("room1", "room2", "room3", "room4"):
        v = str(row.get(col, "") or "").strip()
        if v:
            parts.append(v)
    return " + ".join(parts)


# ── Card HTML ──────────────────────────────────────────────────────────────────

def booking_card(row, booking_type: str) -> str:
    """Generate HTML card for one booking."""
    rooms        = get_rooms_for_booking(row)
    is_meal_only = not rooms
    name         = str(row.get("guest_name", "") or "Hôte")
    phone        = str(row.get("phone", "") or "")
    email        = str(row.get("email", "") or "")
    nat          = str(row.get("nationality", "") or "")
    flag         = flag_for(nat)
    amount       = row.get("amount", "")
    source       = str(row.get("booking_source", "") or "")
    nights       = row.get("nights", "")
    notes        = str(row.get("notes", "") or "")
    repeat       = str(row.get("repeat_guest", "")).lower() in ("true", "1", "yes", "oui")
    visits       = row.get("visit_count", 1)

    arr = row["arrival_date"]
    dep = row["departure_date"]
    arr_str = arr.strftime("%d/%m/%Y") if pd.notna(arr) else "?"
    dep_str = dep.strftime("%d/%m/%Y") if pd.notna(dep) else "?"

    badge_labels = {
        "arrival":   "⬆ Arrivée",
        "departure": "⬇ Départ",
        "staying":   "🏠 En séjour",
        "turnover":  "🔄 Rotation",
    }
    action_texts = {
        "arrival":   "Préparer la chambre pour l'arrivée des hôtes.",
        "departure": "C'est leur dernier jour. Prévoir le nettoyage de la chambre.",
        "turnover":  "Nettoyage et préparation de la chambre entre deux clients.",
    }

    table_dhotes = str(row.get("table_dhotes", "")).lower() in ("true", "1", "yes", "oui")
    # Breakfast: explicit flag OR auto-included for certain sources
    breakfast    = (str(row.get("breakfast", "")).lower() in ("true", "1", "yes", "oui")
                    or source in BREAKFAST_AUTO_SOURCES)
    try:
        guest_count = int(row.get("guest_count", "") or 0)
    except (ValueError, TypeError):
        guest_count = 0

    repeat_tag  = f'<span class="repeat-tag">⭐ Visite {visits}</span>' if repeat else ""
    td_tag      = '<span class="repeat-tag" style="background:#F5EDD8;color:#7A5020;">🍽️ Table d\'hôtes</span>' if table_dhotes else ""
    bf_tag      = '<span class="repeat-tag" style="background:#FFFDE7;color:#F57F17;">🥐 Petit-déjeuner</span>' if breakfast else ""

    if source in PREPAID_SOURCES:
        payment_tag = '<span class="repeat-tag" style="background:#E8F5E9;color:#2E7D32;">✅ Payé</span>'
    elif source in SPLIT_PAYMENT_SOURCES:
        try:
            half = float(str(amount).replace(",", ".")) / 2
            half_str = f" — {half:,.0f} €" if half > 0 else ""
        except (ValueError, TypeError):
            half_str = ""
        payment_tag = f'<span class="repeat-tag" style="background:#FFF8E1;color:#F57F17;">💳 50% restant{half_str}</span>'
    elif source:
        payment_tag = '<span class="repeat-tag" style="background:#FFF3E0;color:#E65100;">💳 À régler</span>'
    else:
        payment_tag = ""

    # Room preparation action only relevant when there is a room
    action_html = ""
    if booking_type in action_texts and not is_meal_only:
        action_html = f'<div class="action-box">⚠ {action_texts[booking_type]}</div>'
    td_action  = '<div class="action-box" style="background:#FDF3E8;color:#7A4A1E;">🍽️ Prévoir le dîner Table d\'hôtes pour ce séjour.</div>' if table_dhotes else ""
    bf_action  = '<div class="action-box" style="background:#FFFDE7;color:#B45309;">🥐 Prévoir le petit-déjeuner pour ce séjour.</div>' if breakfast else ""
    notes_html = f'<div class="notes-box">📝 {notes}</div>' if notes else ""

    # Room badge — or a "🍽️ Repas" badge for meal-only entries
    if is_meal_only:
        rooms_html = ('<span style="display:inline-flex;align-items:center;gap:5px;'
                      'background:#FFF3E0;color:#E65100;'
                      'padding:5px 14px;border-radius:20px;font-size:.9rem;font-weight:700;'
                      'margin:6px 4px 10px 0;">🍽️ Repas</span>')
    else:
        rooms_html = room_badge_html(rooms)

    info_rows = ""
    if phone:
        info_rows += f'<span class="info-label">Tél.</span><span class="info-value">{phone}</span>'
    if email and "@guest.booking.com" not in email:
        info_rows += f'<span class="info-label">Email</span><span class="info-value">{email}</span>'
    if nat:
        info_rows += f'<span class="info-label">Nationalité</span><span class="info-value">{flag} {nat}</span>'
    if str(nights) == "0" or arr_str == dep_str:
        info_rows += f'<span class="info-label">Date</span><span class="info-value">{arr_str}</span>'
    else:
        info_rows += f'<span class="info-label">Séjour</span><span class="info-value">{arr_str} → {dep_str} ({nights} nuit{"s" if str(nights) != "1" else ""})</span>'
    if guest_count:
        info_rows += f'<span class="info-label">Personnes</span><span class="info-value">👥 {guest_count}</span>'
    if source:
        info_rows += f'<span class="info-label">Source</span><span class="info-value">{source}</span>'
    if amount:
        info_rows += f'<span class="info-label">Montant</span><span class="info-value">{amount} €</span>'

    return f"""
<div class="card {booking_type}">
    <span class="badge {booking_type}">{badge_labels[booking_type]}</span>
    <div class="guest-name">{name}{repeat_tag}{td_tag}{bf_tag}{payment_tag}</div>
    {rooms_html}
    <div class="info-grid">{info_rows}</div>
    {action_html}{td_action}{bf_action}{notes_html}
</div>"""


# ── Meal prep summary ──────────────────────────────────────────────────────────

def _covers(row) -> int:
    """Return guest count for a row, defaulting to 2 for room bookings and 1 for meal-only."""
    try:
        n = int(row.get("guest_count", "") or 0)
        if n > 0:
            return n
    except (ValueError, TypeError):
        pass
    is_meal_only = not any(row.get(f"room{i}") for i in range(1, 5))
    return 1 if is_meal_only else 2


def meal_prep_summary(df_active: pd.DataFrame, target_date: date) -> str:
    """
    Return an HTML summary box showing total covers per meal service for the given day.

    - Table d'hôtes tonight:  active guests NOT departing today (they'll be there for dinner)
    - Breakfast/brunch this morning: active guests NOT arriving today for a room
      (they slept here last night) + meal-only guests arriving today with breakfast
    """
    lines = []

    # ── Table d'hôtes tonight ──────────────────────────────────────────────
    td_entries = []
    for _, r in df_active.iterrows():
        if str(r.get("table_dhotes", "")).lower() not in ("true", "1", "yes", "oui"):
            continue
        is_meal_only = not any(r.get(f"room{i}") for i in range(1, 5))
        dep_date = r["departure_date"]
        is_leaving_today = (pd.notna(dep_date) and dep_date.date() == target_date
                            and r["arrival_date"].date() != target_date)
        if not is_leaving_today:
            td_entries.append((str(r.get("guest_name", "") or "?"), _covers(r)))

    if td_entries:
        total  = sum(c for _, c in td_entries)
        detail = " + ".join(f"{n} ({c})" for n, c in td_entries)
        lines.append(
            f'🍽️ Table d\'hôtes ce soir : <strong>{total} couvert{"s" if total > 1 else ""}</strong>'
            f'<span style="color:#7A8C7E;font-size:.85rem;margin-left:8px">{detail}</span>'
        )

    # ── Breakfast / brunch this morning ────────────────────────────────────
    bf_entries = []
    for _, r in df_active.iterrows():
        if str(r.get("breakfast", "")).lower() not in ("true", "1", "yes", "oui"):
            # Also auto-include certain sources if no explicit flag
            if str(r.get("booking_source", "")) not in BREAKFAST_AUTO_SOURCES:
                continue
        is_meal_only = not any(r.get(f"room{i}") for i in range(1, 5))
        arr_date = r["arrival_date"]
        # Room guests arriving today haven't slept here yet → breakfast tomorrow, not today
        is_room_arriving_today = (not is_meal_only and arr_date.date() == target_date)
        if not is_room_arriving_today:
            bf_entries.append((str(r.get("guest_name", "") or "?"), _covers(r)))

    if bf_entries:
        total  = sum(c for _, c in bf_entries)
        detail = " + ".join(f"{n} ({c})" for n, c in bf_entries)
        lines.append(
            f'🥐 Petit-déjeuner ce matin : <strong>{total} couvert{"s" if total > 1 else ""}</strong>'
            f'<span style="color:#7A8C7E;font-size:.85rem;margin-left:8px">{detail}</span>'
        )

    if not lines:
        return ""

    inner = "<br>".join(lines)
    return (
        '<div style="background:#F5F0E8;border-radius:8px;padding:14px 16px;'
        'margin-bottom:20px;border-left:4px solid #D4A373;font-size:.92rem;color:#3D2B1F;">'
        f'{inner}</div>'
    )


# ── Nav helper ────────────────────────────────────────────────────────────────

def _nav_html(active: str) -> str:
    """Return 4-tab nav HTML.  active = filename of current page, e.g. 'index.html'."""
    tabs = [
        ("index.html",    "📅 Aujourd'hui"),
        ("weekly.html",   "📆 Cette semaine"),
        ("upcoming.html", "🗓️ Semaines prochaines"),
        ("analytics.html","📊 Analytiques"),
    ]
    links = ""
    for href, label in tabs:
        cls = ' class="active"' if href == active else ""
        links += f'<a href="{href}"{cls}>{label}</a>'
    return f"<nav>{links}</nav>"


# ── Shared day-section helpers ─────────────────────────────────────────────────

def upcoming_day_section(df: pd.DataFrame, target_date: date,
                         day_offset: int, label: str = "") -> str:
    """Arrivals + departures card-block for one day offset from target_date."""
    d   = target_date + timedelta(days=day_offset)
    arr = df[df["arrival_date"].dt.date == d]
    dep = df[(df["departure_date"].dt.date == d) & (df["arrival_date"].dt.date != d)]
    full_label = f"{label} — {fmt_date(d)}" if label else fmt_date(d)
    if arr.empty and dep.empty:
        return (f'<div class="section-title">{full_label}</div>'
                '<div class="empty-msg" style="padding:16px">Rien de prévu</div>')
    html  = f'<div class="section-title">{full_label}</div>'
    html += "".join(booking_card(row, "arrival")   for _, row in arr.iterrows())
    html += "".join(booking_card(row, "departure") for _, row in dep.iterrows())
    return html


def next_week_section(df: pd.DataFrame, week_start_date: date, week_number: int) -> str:
    """All arrivals for one upcoming calendar week."""
    week_end = week_start_date + timedelta(days=6)
    arr = df[(df["arrival_date"].dt.date >= week_start_date) &
             (df["arrival_date"].dt.date <= week_end)]
    label = (f"Semaine +{week_number} : {DAYS_FR[week_start_date.weekday()]} "
             f"{week_start_date.day}/{week_start_date.month}"
             f" – {DAYS_FR[week_end.weekday()]} {week_end.day}/{week_end.month}")
    if arr.empty:
        return (f'<div class="section-title">📆 {label}</div>'
                '<div class="empty-msg" style="padding:16px">Aucune arrivée</div>')
    html  = f'<div class="section-title">📆 {label}</div>'
    html += "".join(booking_card(row, "arrival") for _, row in arr.iterrows())
    return html


# ── Daily HTML ─────────────────────────────────────────────────────────────────

def generate_daily_html(df: pd.DataFrame, target_date: date, logo_path: str) -> str:
    today_str   = fmt_date(target_date)
    target_dt   = pd.Timestamp(target_date)

    active = df[
        (df["arrival_date"]   <= target_dt) &
        (df["departure_date"] >= target_dt)
    ]

    arrivals   = active[active["arrival_date"].dt.date   == target_date]
    departures = active[
        (active["departure_date"].dt.date == target_date) &
        (active["arrival_date"].dt.date   != target_date)
    ]
    staying    = active[
        (active["arrival_date"].dt.date   != target_date) &
        (active["departure_date"].dt.date != target_date)
    ]

    # Turnovers: rooms that have both a departure and an arrival today
    arriving_rooms = set()
    for _, r in arrivals.iterrows():
        for col in ("room1","room2","room3","room4"):
            if r.get(col):
                arriving_rooms.add(r[col])
    departing_rooms = set()
    for _, r in departures.iterrows():
        for col in ("room1","room2","room3","room4"):
            if r.get(col):
                departing_rooms.add(r[col])
    turnover_rooms = arriving_rooms & departing_rooms

    def section(bookings, btype, title):
        if bookings.empty:
            return ""
        cards = "".join(booking_card(row, btype) for _, row in bookings.iterrows())
        return f'<div class="section-title">{title}</div>{cards}'

    # ── Today ─────────────────────────────────────────────────────────────────
    meal_summary = meal_prep_summary(active, target_date)

    sections = (
        section(arrivals,   "arrival",   f"⬆ Arrivées ({len(arrivals)})") +
        section(departures, "departure", f"⬇ Départs ({len(departures)})") +
        section(staying,    "staying",   f"🏠 En séjour ({len(staying)})")
    )

    # Rotation banner — top of page, highly visible
    rotation_banner = ""
    if turnover_rooms:
        rooms_list = ", ".join(sorted(turnover_rooms))
        rotation_banner = (
            '<div style="background:#FFF3CD;border:2px solid #FFC107;border-radius:10px;'
            'padding:14px 18px;margin-bottom:18px;font-size:1rem;color:#7A4A00;">'
            f'🔄 <strong>Rotation aujourd\'hui :</strong> {rooms_list}'
            '</div>'
        )

    today_body = rotation_banner + meal_summary + (sections if sections else '<div class="empty-msg">🌿 Pas de réservation aujourd\'hui — repos bien mérité !</div>')

    # ── Next 6 days flat ──────────────────────────────────────────────────────
    upcoming_body = ""
    for offset in range(1, 7):
        if offset == 1:
            lbl = "⬆ Demain"
        elif offset == 2:
            lbl = "⬆ Après-demain"
        else:
            lbl = ""
        upcoming_body += upcoming_day_section(df, target_date, offset, lbl)

    body = today_body + upcoming_body

    nav = _nav_html("index.html")

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>La Ferme de la Cour — {today_str}</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <img src="logo.png" alt="La Ferme de la Cour">
  <h1>La Ferme de la Cour</h1>
  <div class="sub">{today_str}</div>
</header>
{nav}
<div class="container">{body}
</div>
<footer>Généré le {datetime.now(_TZ).strftime("%d/%m/%Y à %H:%M")} · {OWNER_NAME}</footer>
</body>
</html>"""


# ── Weekly HTML ────────────────────────────────────────────────────────────────

def generate_weekly_html(df: pd.DataFrame, week_start: date, logo_path: str) -> str:
    week_end = week_start + timedelta(days=6)
    week_days = [week_start + timedelta(days=i) for i in range(7)]

    # Arrivals this week
    arrivals_week = df[
        (df["arrival_date"].dt.date >= week_start) &
        (df["arrival_date"].dt.date <= week_end)
    ]
    departures_week = df[
        (df["departure_date"].dt.date >= week_start) &
        (df["departure_date"].dt.date <= week_end)
    ]

    # Revenue = sum of amounts for bookings arriving this week
    revenue = arrivals_week["amount"].apply(
        lambda x: float(str(x).replace(",", ".")) if x else 0.0
    ).sum()

    # Repeat guests arriving this week
    repeat_arrivals = arrivals_week[
        arrivals_week["repeat_guest"].astype(str).str.lower().isin(["true", "1", "yes", "oui"])
    ]
    # Table d'hôtes this week
    td_week = arrivals_week[
        arrivals_week.get("table_dhotes", pd.Series(dtype=str)).astype(str).str.lower().isin(["true", "1", "yes", "oui"])
    ] if "table_dhotes" in arrivals_week.columns else arrivals_week.iloc[0:0]

    # Breakfast this week — explicit flag OR auto-included for Booking.com / Website
    _bf_flag = (arrivals_week["breakfast"].astype(str).str.lower().isin(["true", "1", "yes", "oui"])
                if "breakfast" in arrivals_week.columns
                else pd.Series(False, index=arrivals_week.index))
    _bf_auto = arrivals_week["booking_source"].isin(BREAKFAST_AUTO_SOURCES)
    bf_week  = arrivals_week[_bf_flag | _bf_auto]

    # Occupancy per day — count rooms occupied, not bookings
    occ_rows = ""
    for d in week_days:
        dt = pd.Timestamp(d)
        day_bookings = df[(df["arrival_date"] <= dt) & (df["departure_date"] >= dt)]
        rooms_occupied = set()
        for _, r in day_bookings.iterrows():
            for col in ("room1", "room2", "room3", "room4"):
                v = str(r.get(col, "") or "").strip()
                if v:
                    rooms_occupied.add(v)
        count  = len(rooms_occupied)
        total  = len(ROOMS)
        pct    = int(count / total * 100) if total else 0
        bar    = f'<span class="occ-bar" style="width:{pct}px"></span>'
        occ_rows += (f"<tr><td>{DAYS_FR[d.weekday()]} {d.day}/{d.month}</td>"
                     f"<td>{bar}{pct}%</td><td>{count}/{total}</td></tr>")

    # Room availability grid — rows=rooms, cols=7 days
    day_headers = "".join(
        f'<th style="text-align:center;font-size:.75rem;padding:6px 8px;">'
        f'{DAYS_FR[d.weekday()][:3]}<br>{d.day}/{d.month}</th>'
        for d in week_days
    )
    grid_rows = ""
    for room in ROOMS:
        ident = ROOM_IDENTITY.get(room, {"emoji": "🛏", "bg": "#F1EFE7", "color": "#4A5D4E"})
        short = room.replace(" de la Cour", "")
        name_cell = (f'<td style="font-weight:600;font-size:.8rem;white-space:nowrap;'
                     f'color:{ident["color"]};padding:6px 10px;">'
                     f'{ident["emoji"]} {short}</td>')
        cells = ""
        for d in week_days:
            dt = pd.Timestamp(d)
            day_bk = df[(df["arrival_date"] <= dt) & (df["departure_date"] >= dt)]
            guest_name = None
            for _, r in day_bk.iterrows():
                booked = [str(r.get(f"room{i}", "") or "").strip() for i in range(1, 5)]
                if room in booked:
                    guest_name = str(r.get("guest_name", "") or "?").split()[0]
                    break
            if guest_name:
                cells += (f'<td style="background:{ident["bg"]};color:{ident["color"]};'
                          f'text-align:center;font-size:.72rem;padding:5px 3px;'
                          f'font-weight:600">{guest_name}</td>')
            else:
                cells += ('<td style="background:#EBF5EC;color:#2E7D32;text-align:center;'
                          'font-size:.85rem;padding:5px 3px;">✓</td>')
        grid_rows += f"<tr>{name_cell}{cells}</tr>"

    room_grid_html = f"""
<div class="section-title">🛏️ Disponibilités des chambres</div>
<div style="overflow-x:auto">
<table style="border-collapse:collapse;width:100%;font-size:.82rem">
  <thead><tr><th style="text-align:left;padding:6px 10px">Chambre</th>{day_headers}</tr></thead>
  <tbody>{grid_rows}</tbody>
</table>
</div>"""

    # Source breakdown for arrivals this week
    source_counts = arrivals_week["booking_source"].value_counts()
    source_rows = "".join(
        f"<tr><td>{src}</td><td>{cnt}</td></tr>"
        for src, cnt in source_counts.items()
    )

    # Repeat guest list
    repeat_html = ""
    if not repeat_arrivals.empty:
        items = "".join(
            f"<li><strong>{r['guest_name']}</strong> "
            f"({r.get('nationality','')}) — {flag_for(r.get('nationality',''))}</li>"
            for _, r in repeat_arrivals.iterrows()
        )
        repeat_html = f"""
<div class="section-title">⭐ Clients Fidèles cette semaine</div>
<ul style="padding-left:20px;font-size:.9rem;line-height:2">{items}</ul>"""

    week_label = (f"Semaine du {DAYS_FR[week_start.weekday()]} {week_start.day} "
                  f"{MONTHS_FR[week_start.month]} au "
                  f"{DAYS_FR[week_end.weekday()]} {week_end.day} "
                  f"{MONTHS_FR[week_end.month]} {week_end.year}")

    nav = _nav_html("weekly.html")

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>La Ferme de la Cour — Semaine</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <img src="logo.png" alt="La Ferme de la Cour">
  <h1>La Ferme de la Cour</h1>
  <div class="sub">{week_label}</div>
</header>
{nav}
<div class="container">
  <div class="stat-grid">
    <div class="stat-card">
      <div class="stat-value">{len(arrivals_week)}</div>
      <div class="stat-label">Arrivées cette semaine</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{len(departures_week)}</div>
      <div class="stat-label">Départs cette semaine</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{revenue:,.0f} €</div>
      <div class="stat-label">Revenus estimés</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{len(repeat_arrivals)}</div>
      <div class="stat-label">Clients Fidèles</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{len(td_week)}</div>
      <div class="stat-label">🍽️ Table d'hôtes</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{len(bf_week)}</div>
      <div class="stat-label">🥐 Petit-déjeuner</div>
    </div>
  </div>

  <div class="section-title">📅 Taux d'Occupation</div>
  <table>
    <thead><tr><th>Jour</th><th>Occupation</th><th>Chambres</th></tr></thead>
    <tbody>{occ_rows}</tbody>
  </table>

  {room_grid_html}

  <div class="section-title">📊 Réservations par Source</div>
  <table>
    <thead><tr><th>Source</th><th>Arrivées</th></tr></thead>
    <tbody>{source_rows if source_rows else "<tr><td colspan='2'>Aucune arrivée cette semaine</td></tr>"}</tbody>
  </table>

  {repeat_html}
</div>
<footer>Généré le {datetime.now(_TZ).strftime("%d/%m/%Y à %H:%M")} · {OWNER_NAME}</footer>
</body>
</html>"""


# ── Upcoming weeks HTML ────────────────────────────────────────────────────────

def generate_upcoming_html(df: pd.DataFrame, today: date, logo_path: str) -> str:
    """Page showing the next 8 calendar weeks (starting from next Monday)."""
    # Start from next Monday (or this coming Monday if today is Sunday)
    days_until_monday = (7 - today.weekday()) % 7 or 7
    first_week_start  = today + timedelta(days=days_until_monday)

    body = ""
    for i in range(8):
        week_start = first_week_start + timedelta(weeks=i)
        body += next_week_section(df, week_start, i + 1)

    nav = _nav_html("upcoming.html")

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>La Ferme de la Cour — Semaines prochaines</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <img src="logo.png" alt="La Ferme de la Cour">
  <h1>La Ferme de la Cour</h1>
  <div class="sub">Semaines prochaines</div>
</header>
{nav}
<div class="container">{body}
</div>
<footer>Généré le {datetime.now(_TZ).strftime("%d/%m/%Y à %H:%M")} · {OWNER_NAME}</footer>
</body>
</html>"""


# ── GitHub push ────────────────────────────────────────────────────────────────

def push_to_github(today_str: str) -> None:
    repo = GITHUB_REPO_PATH
    try:
        subprocess.run(["git", "-C", repo, "add", DOCS_FOLDER], check=True)
        subprocess.run(
            ["git", "-C", repo, "commit", "-m", f"Schedule update — {today_str}"],
            check=True,
        )
        subprocess.run(["git", "-C", repo, "push"], check=True)
        log.info("Pushed to GitHub Pages ✓")
    except subprocess.CalledProcessError as exc:
        log.error(f"Git push failed: {exc}")


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    df     = load_data()
    today  = date.today()

    docs_dir = os.path.join(GITHUB_REPO_PATH, DOCS_FOLDER)
    os.makedirs(docs_dir, exist_ok=True)

    # Copy logo into docs/ so GitHub Pages can serve it
    logo_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
    logo_dst = os.path.join(docs_dir, "logo.png")
    if os.path.exists(logo_src) and not os.path.exists(logo_dst):
        shutil.copy2(logo_src, logo_dst)

    # Daily page
    daily_html = generate_daily_html(df, today, logo_src)
    index_path = os.path.join(docs_dir, "index.html")
    archive_path = os.path.join(docs_dir, f"{today.strftime('%Y-%m-%d')}.html")
    for path in (index_path, archive_path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(daily_html)
    log.info(f"Daily HTML written → {index_path}")

    # Weekly page (week starts on Monday)
    week_start = today - timedelta(days=today.weekday())
    weekly_html = generate_weekly_html(df, week_start, logo_src)
    weekly_path = os.path.join(docs_dir, "weekly.html")
    with open(weekly_path, "w", encoding="utf-8") as fh:
        fh.write(weekly_html)
    log.info(f"Weekly HTML written → {weekly_path}")

    # Upcoming weeks page
    upcoming_html = generate_upcoming_html(df, today, logo_src)
    upcoming_path = os.path.join(docs_dir, "upcoming.html")
    with open(upcoming_path, "w", encoding="utf-8") as fh:
        fh.write(upcoming_html)
    log.info(f"Upcoming HTML written → {upcoming_path}")

    no_git = "--no-git" in sys.argv
    if no_git:
        log.info("--no-git flag set — skipping git push (handled by GitHub Actions)")
    else:
        push_to_github(today.strftime("%Y-%m-%d"))


if __name__ == "__main__":
    run()
