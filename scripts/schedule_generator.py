"""
schedule_generator.py
─────────────────────
Reads the Google Sheet, generates:
  • docs/index.html        — today's room-by-room schedule
  • docs/weekly.html       — this week's summary (revenue, occupancy, …)
Then commits and pushes both files to GitHub so GitHub Pages updates.

Usage:
    python schedule_generator.py
"""
import os
import shutil
import subprocess
import logging
from datetime import datetime, timedelta, date

import pandas as pd

from auth import get_worksheet
from config import ROOMS, GITHUB_REPO_PATH, DOCS_FOLDER, OWNER_NAME

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
}

DAYS_FR   = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MONTHS_FR = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
             "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]

CSS = """
:root {
    --primary:    #5D4037;
    --secondary:  #8D6E63;
    --accent:     #A1887F;
    --text:       #3E2723;
    --bg:         #EFEBE9;
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
.card.arrival   { border-left-color: #1565C0; }
.card.departure { border-left-color: #E65100; }
.card.staying   { border-left-color: #2E7D32; }
.card.turnover  { border-left-color: #AD1457; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 20px;
         font-size: .75rem; font-weight: 700; margin-bottom: 8px; }
.badge.arrival   { background: #E3F2FD; color: #1565C0; }
.badge.departure { background: #FFF3E0; color: #E65100; }
.badge.staying   { background: #E8F5E9; color: #2E7D32; }
.badge.turnover  { background: #FCE4EC; color: #AD1457; }
.guest-name  { font-size: 1.15rem; font-weight: 700; margin-bottom: 6px; }
.repeat-tag  { background: #FFF9C4; color: #F57F17; font-size: .72rem;
               padding: 2px 8px; border-radius: 12px; margin-left: 8px; vertical-align: middle; }
.info-grid   { display: grid; grid-template-columns: auto 1fr; gap: 2px 12px;
               font-size: .88rem; margin-top: 6px; }
.info-label  { color: var(--secondary); font-weight: 600; white-space: nowrap; }
.info-value  { color: var(--text); }
.notes-box   { background: #FFF8E7; border-radius: 6px; padding: 8px 12px;
               margin-top: 10px; font-style: italic; font-size: .85rem; color: #5D4037; }
.action-box  { background: #FFEBEE; border-radius: 6px; padding: 8px 12px;
               margin-top: 10px; font-weight: 700; font-size: .85rem; color: #C62828; }
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
th, td       { padding: 8px 12px; border-bottom: 1px solid #D7CCC8; text-align: left; }
th           { background: var(--primary); color: #fff; }
tr:hover     { background: #FFF8E7; }
.occ-bar     { display: inline-block; height: 8px; background: var(--primary);
               border-radius: 4px; vertical-align: middle; margin-right: 6px; }
footer       { text-align: center; color: #BCAAA4; font-size: .78rem;
               margin: 32px 0 16px; }
nav          { text-align: center; margin: 16px 0; }
nav a        { color: var(--primary); text-decoration: none; margin: 0 10px;
               font-weight: 600; font-size: .9rem; }
nav a:hover  { text-decoration: underline; }
@media (max-width: 520px) {
    header h1   { font-size: 1.2rem; }
    .info-grid  { grid-template-columns: 1fr; }
}
"""


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
    return " + ".join(parts) if parts else "Chambre inconnue"


# ── Card HTML ──────────────────────────────────────────────────────────────────

def booking_card(row, booking_type: str) -> str:
    """Generate HTML card for one booking."""
    rooms      = get_rooms_for_booking(row)
    name       = str(row.get("guest_name", "") or "Invité")
    phone      = str(row.get("phone", "") or "")
    email      = str(row.get("email", "") or "")
    nat        = str(row.get("nationality", "") or "")
    flag       = flag_for(nat)
    amount     = row.get("amount", "")
    source     = str(row.get("booking_source", "") or "")
    nights     = row.get("nights", "")
    notes      = str(row.get("notes", "") or "")
    repeat     = str(row.get("repeat_guest", "")).lower() in ("true", "1", "yes", "oui")
    visits     = row.get("visit_count", 1)

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
        "arrival":   "Préparer la chambre pour l'arrivée des invités.",
        "departure": "C'est leur dernier jour. Prévoir le nettoyage de la chambre.",
        "turnover":  "Nettoyage et préparation de la chambre entre deux clients.",
    }

    repeat_tag  = f'<span class="repeat-tag">⭐ Visite {visits}</span>' if repeat else ""
    action_html = (f'<div class="action-box">⚠ {action_texts[booking_type]}</div>'
                   if booking_type in action_texts else "")
    notes_html  = f'<div class="notes-box">📝 {notes}</div>' if notes else ""

    info_rows = ""
    if phone:
        info_rows += f'<span class="info-label">Tél.</span><span class="info-value">{phone}</span>'
    if email and "@guest.booking.com" not in email:
        info_rows += f'<span class="info-label">Email</span><span class="info-value">{email}</span>'
    if nat:
        info_rows += f'<span class="info-label">Nationalité</span><span class="info-value">{flag} {nat}</span>'
    info_rows += f'<span class="info-label">Séjour</span><span class="info-value">{arr_str} → {dep_str} ({nights} nuit{"s" if str(nights) != "1" else ""})</span>'
    info_rows += f'<span class="info-label">Chambre</span><span class="info-value">{rooms}</span>'
    if source:
        info_rows += f'<span class="info-label">Source</span><span class="info-value">{source}</span>'
    if amount:
        info_rows += f'<span class="info-label">Montant</span><span class="info-value">{amount} €</span>'

    return f"""
<div class="card {booking_type}">
    <span class="badge {booking_type}">{badge_labels[booking_type]}</span>
    <div class="guest-name">{name}{repeat_tag}</div>
    <div class="info-grid">{info_rows}</div>
    {action_html}{notes_html}
</div>"""


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

    sections = (
        section(arrivals,   "arrival",   f"⬆ Arrivées ({len(arrivals)})") +
        section(departures, "departure", f"⬇ Départs ({len(departures)})") +
        section(staying,    "staying",   f"🏠 En séjour ({len(staying)})")
    )

    if turnover_rooms:
        rooms_list = ", ".join(sorted(turnover_rooms))
        sections += f'<div class="notes-box" style="margin-top:16px">🔄 Rotation de chambre aujourd\'hui : <strong>{rooms_list}</strong></div>'

    body = sections if sections else '<div class="empty-msg">🌿 Pas de réservation aujourd\'hui — repos bien mérité !</div>'

    nav = '<nav><a href="index.html">Aujourd\'hui</a> | <a href="weekly.html">Cette semaine</a></nav>'

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
<div class="container">{body}</div>
<footer>Généré le {datetime.now().strftime("%d/%m/%Y à %H:%M")} · {OWNER_NAME}</footer>
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

    # Occupancy per day
    occ_rows = ""
    for d in week_days:
        dt = pd.Timestamp(d)
        count = len(df[
            (df["arrival_date"]   <= dt) &
            (df["departure_date"] >= dt)
        ])
        total  = len(ROOMS)
        pct    = int(count / total * 100) if total else 0
        bar    = f'<span class="occ-bar" style="width:{pct}px"></span>'
        occ_rows += (f"<tr><td>{DAYS_FR[d.weekday()]} {d.day}/{d.month}</td>"
                     f"<td>{bar}{pct}%</td><td>{count}/{total}</td></tr>")

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

    nav = '<nav><a href="index.html">Aujourd\'hui</a> | <a href="weekly.html">Cette semaine</a></nav>'

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
  </div>

  <div class="section-title">📅 Taux d'Occupation</div>
  <table>
    <thead><tr><th>Jour</th><th>Occupation</th><th>Chambres</th></tr></thead>
    <tbody>{occ_rows}</tbody>
  </table>

  <div class="section-title">📊 Réservations par Source</div>
  <table>
    <thead><tr><th>Source</th><th>Arrivées</th></tr></thead>
    <tbody>{source_rows if source_rows else "<tr><td colspan='2'>Aucune arrivée cette semaine</td></tr>"}</tbody>
  </table>

  {repeat_html}
</div>
<footer>Généré le {datetime.now().strftime("%d/%m/%Y à %H:%M")} · {OWNER_NAME}</footer>
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

    push_to_github(today.strftime("%Y-%m-%d"))


if __name__ == "__main__":
    run()
