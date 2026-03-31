"""
analytics.py  –  La Ferme de la Cour
Generates docs/analytics.html with charts from the Google Sheet.
Run: python analytics.py
"""

import os, sys, io, base64, warnings
from collections import Counter, defaultdict
from datetime import datetime, date, timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import warnings
warnings.filterwarnings("ignore")

# ── local imports ────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auth import get_worksheet
from config import DOCS_FOLDER, GITHUB_REPO_PATH, ROOMS, COMMISSIONS, BOOKING_GOALS

# ── colour themes ─────────────────────────────────────────────────────────────
# Change THEME to switch the full palette. "P01" or "P03".
THEME = "P01"

_THEMES = {
    "P01": {  # L'Ardenne Authentique
        "brown":      "#4A5D4E",   # Vert Épicéa
        "secondary":  "#7A8C7E",
        "accent":     "#D4A373",   # Terre de Sienne
        "light":      "#C9D5CB",
        "gold":       "#A8B8AC",
        "bg":         "#F1EFE7",   # Laine Grège
        "text":       "#2C2C2C",   # Ardoise Fumée
        "shadow_rgb": "74,93,78",
        "rooms":      ["#4A5D4E", "#D4A373", "#C9D5CB", "#E8E2D8"],
        "sources":    {"Booking.com": "#4A5D4E", "Website": "#D4A373", "Manual": "#7A8C7E", "Unknown": "#C9D5CB"},
        "goal_hit":   "#4A5D4E",
        "goal_miss":  "#D4A373",
    },
    "P03": {  # La Table d'Hôtes
        "brown":      "#8D5B4C",   # Vieux Bordeaux
        "secondary":  "#A67C6E",
        "accent":     "#E6C199",   # Paille Dorée
        "light":      "#E8D5C0",
        "gold":       "#C4A882",
        "bg":         "#FFF8F0",   # Fleur de Lait
        "text":       "#3E3E3E",   # Bistre
        "shadow_rgb": "141,91,76",
        "rooms":      ["#8D5B4C", "#E6C199", "#E8D5C0", "#F5E8D5"],
        "sources":    {"Booking.com": "#8D5B4C", "Website": "#E6C199", "Manual": "#A67C6E", "Unknown": "#E8D5C0"},
        "goal_hit":   "#8D5B4C",
        "goal_miss":  "#E6C199",
    },
}

_t            = _THEMES[THEME]
BROWN         = _t["brown"]
SECONDARY     = _t["secondary"]
LIGHT         = _t["light"]
ACCENT        = _t["accent"]
GOLD          = _t["gold"]
BG            = _t["bg"]
TEXT_COLOR    = _t["text"]
SHADOW_RGB    = _t["shadow_rgb"]
ROOMS_COLORS  = _t["rooms"]
SOURCE_COLORS = _t["sources"]
GOAL_HIT      = _t["goal_hit"]
GOAL_MISS     = _t["goal_miss"]

plt.rcParams.update({
    "font.family": "sans-serif",
    "axes.facecolor": BG,
    "figure.facecolor": BG,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.edgecolor": LIGHT,
    "axes.labelcolor": BROWN,
    "xtick.color": ACCENT,
    "ytick.color": ACCENT,
    "text.color": BROWN,
    "axes.titleweight": "bold",
    "axes.titlesize": 13,
})

NATIONALITY_FR = {
    "Belgium": "Belgique", "Belgique": "Belgique",
    "Netherlands": "Pays-Bas", "France": "France",
    "Luxembourg": "Luxembourg", "Germany": "Allemagne",
    "United Kingdom": "Royaume-Uni", "UK": "Royaume-Uni",
    "Switzerland": "Suisse", "Italy": "Italie",
    "Spain": "Espagne", "United States": "États-Unis",
    "Austria": "Autriche", "Poland": "Pologne",
    "Denmark": "Danemark", "Sweden": "Suède",
    "Norway": "Norvège", "Portugal": "Portugal",
    "Hungary": "Hongrie", "Romania": "Roumanie",
    "China": "Chine", "Japan": "Japon",
    "Canada": "Canada", "Australia": "Australie",
}

# ── helpers ──────────────────────────────────────────────────────────────────
def _fig_to_b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)
    return base64.b64encode(buf.read()).decode()

def _parse_date(s):
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(s).strip(), fmt).date()
        except Exception:
            pass
    return None

def _week_key(d):          # "2025-W23"
    return f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"

def _norm_nat(n):
    n = str(n).strip()
    return NATIONALITY_FR.get(n, n) if n not in ("", "nan", "Unknown", "None") else None

# ── load data ────────────────────────────────────────────────────────────────
def load_data(include_cancelled=False):
    ws = get_worksheet()
    records = ws.get_all_records()
    rows = []
    for r in records:
        status = str(r.get("status", "")).strip()
        if not include_cancelled:
            if status in ("Cancelled", "", "Unknown") or not str(r.get("reference","")).strip():
                continue
        else:
            if status in ("", "Unknown") or not str(r.get("reference","")).strip():
                continue
        arrival   = _parse_date(r.get("arrival_date", ""))
        departure = _parse_date(r.get("departure_date", ""))
        booking_d = _parse_date(r.get("booking_date", ""))
        if not arrival:
            continue
        rooms_booked = [str(r.get(f"room{i}", "")).strip() for i in range(1, 5)
                        if str(r.get(f"room{i}", "")).strip()]
        try:
            amount = float(str(r.get("amount", 0)).replace(",", ".") or 0)
        except Exception:
            amount = 0.0
        try:
            nights = float(str(r.get("nights", 0)) or 0)
        except Exception:
            nights = (departure - arrival).days if departure else 0
        source = str(r.get("booking_source", "")).strip() or "Unknown"
        commission = COMMISSIONS.get(source, 0.0)
        net_amount = round(amount * (1 - commission), 2)
        rows.append({
            "source":     source,
            "arrival":    arrival,
            "departure":  departure,
            "booking_d":  booking_d,
            "rooms":      rooms_booked,
            "amount":     amount,        # gross (what guest paid)
            "net_amount": net_amount,    # after commission
            "commission": commission,
            "nights":     nights,
            "nationality": _norm_nat(r.get("nationality", "")),
            "repeat":       str(r.get("repeat_guest", "")).lower() in ("true", "1", "yes"),
            "table_dhotes": str(r.get("table_dhotes", "")).lower() in ("true", "1", "yes", "oui"),
            "status":       status,
            "reference":    str(r.get("reference", "")),
        })
    return rows

# ── individual charts ─────────────────────────────────────────────────────────

def chart_room_popularity(rows):
    counts = Counter(rm for r in rows for rm in r["rooms"])
    short  = {room: room.split(" ")[0] for room in ROOMS}
    vals   = [counts.get(room, 0) for room in ROOMS]
    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar([short[r] for r in ROOMS], vals, color=ROOMS_COLORS, width=0.55, zorder=3)
    ax.bar_label(bars, padding=4, fontsize=11, color=BROWN, fontweight="bold")
    ax.set_title("Chambres les plus réservées")
    ax.set_ylabel("Réservations")
    ax.grid(axis="y", color=LIGHT, zorder=0)
    ax.set_ylim(0, max(vals) * 1.18)
    return _fig_to_b64(fig)

def chart_day_of_week(rows):
    DAY_FR = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    counts = Counter(r["arrival"].weekday() for r in rows)
    vals   = [counts.get(i, 0) for i in range(7)]
    colors = [BROWN if v == max(vals) else ACCENT for v in vals]
    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(DAY_FR, vals, color=colors, width=0.6, zorder=3)
    ax.bar_label(bars, padding=4, fontsize=11, fontweight="bold")
    ax.set_title("Jour d'arrivée préféré")
    ax.set_ylabel("Arrivées")
    ax.grid(axis="y", color=LIGHT, zorder=0)
    ax.set_ylim(0, max(vals) * 1.18)
    return _fig_to_b64(fig)

def chart_monthly(rows):
    MONTH_FR = ["Jan","Fév","Mar","Avr","Mai","Jun","Jul","Aoû","Sep","Oct","Nov","Déc"]
    counts = Counter((r["arrival"].year, r["arrival"].month) for r in rows)
    years  = sorted({r["arrival"].year for r in rows})
    x      = np.arange(12)
    w      = 0.35 if len(years) > 1 else 0.5
    palette = [BROWN, ACCENT]
    fig, ax = plt.subplots(figsize=(11, 4.5))
    for i, yr in enumerate(years):
        vals = [counts.get((yr, m+1), 0) for m in range(12)]
        offset = (i - (len(years)-1)/2) * w
        bars = ax.bar(x + offset, vals, w, label=str(yr), color=palette[i % len(palette)], zorder=3)
        ax.bar_label(bars, padding=3, fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(MONTH_FR)
    ax.set_title("Réservations par mois")
    ax.set_ylabel("Réservations")
    ax.legend(frameon=False)
    ax.grid(axis="y", color=LIGHT, zorder=0)
    return _fig_to_b64(fig)

def chart_nationality(rows):
    counts = Counter(r["nationality"] for r in rows if r["nationality"])
    top = counts.most_common(8)
    labels, vals = zip(*top) if top else ([], [])
    fig, ax = plt.subplots(figsize=(7, 4.5))
    colors = [BROWN if i == 0 else ACCENT if i == 1 else GOLD if i < 4 else LIGHT
              for i in range(len(vals))]
    bars = ax.barh(list(reversed(labels)), list(reversed(vals)),
                   color=list(reversed(colors)), zorder=3)
    ax.bar_label(bars, padding=4, fontsize=11, fontweight="bold")
    ax.set_title("Nationalités")
    ax.set_xlabel("Réservations")
    ax.grid(axis="x", color=LIGHT, zorder=0)
    ax.set_xlim(0, max(vals) * 1.2)
    return _fig_to_b64(fig)

def chart_source(rows):
    counts = Counter(r["source"] for r in rows)
    labels = list(counts.keys())
    vals   = list(counts.values())
    colors = [SOURCE_COLORS.get(l, LIGHT) for l in labels]
    fig, ax = plt.subplots(figsize=(5.5, 5))
    wedges, texts, autotexts = ax.pie(
        vals, labels=None, colors=colors, autopct="%1.0f%%",
        startangle=140, wedgeprops=dict(linewidth=2, edgecolor="white"),
        pctdistance=0.78)
    for at in autotexts:
        at.set_color("white"); at.set_fontweight("bold"); at.set_fontsize(12)
    legend = [mpatches.Patch(color=c, label=f"{l}  ({v})")
              for l, v, c in zip(labels, vals, colors)]
    ax.legend(handles=legend, loc="lower center", bbox_to_anchor=(0.5, -0.12),
              ncol=len(labels), frameon=False, fontsize=11)
    ax.set_title("Canal de réservation")
    return _fig_to_b64(fig)

def chart_revenue_month(rows):
    MONTH_FR = ["Jan","Fév","Mar","Avr","Mai","Jun","Jul","Aoû","Sep","Oct","Nov","Déc"]
    revenue = defaultdict(float)
    for r in rows:
        revenue[(r["arrival"].year, r["arrival"].month)] += r["net_amount"]
    years  = sorted({r["arrival"].year for r in rows})
    x      = np.arange(12)
    w      = 0.35 if len(years) > 1 else 0.5
    palette = [BROWN, ACCENT]
    fig, ax = plt.subplots(figsize=(11, 4.5))
    for i, yr in enumerate(years):
        vals = [revenue.get((yr, m+1), 0) for m in range(12)]
        offset = (i - (len(years)-1)/2) * w
        bars = ax.bar(x + offset, vals, w, label=str(yr), color=palette[i % len(palette)], zorder=3)
        ax.bar_label(bars, padding=3, fontsize=8,
                     labels=[f"{v/1000:.1f}k" if v >= 1000 else (f"{v:.0f}" if v else "") for v in vals])
    ax.set_xticks(x)
    ax.set_xticklabels(MONTH_FR)
    ax.set_title("Revenus nets par mois (€ après commission)")
    ax.set_ylabel("€")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f} €"))
    ax.legend(frameon=False)
    ax.grid(axis="y", color=LIGHT, zorder=0)
    return _fig_to_b64(fig)

def chart_lead_time(rows):
    leads = [(r["arrival"] - r["booking_d"]).days
             for r in rows if r["booking_d"] and r["arrival"] >= r["booking_d"]]
    if not leads:
        return None
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(leads, bins=20, color=BROWN, edgecolor="white", zorder=3)
    ax.axvline(np.median(leads), color=ACCENT, linestyle="--", linewidth=2,
               label=f"Médiane : {int(np.median(leads))} j")
    ax.set_title("Délai de réservation (jours avant arrivée)")
    ax.set_xlabel("Jours")
    ax.set_ylabel("Réservations")
    ax.legend(frameon=False)
    ax.grid(axis="y", color=LIGHT, zorder=0)
    return _fig_to_b64(fig)

def chart_repeat_guests(rows):
    total   = len(rows)
    repeats = sum(1 for r in rows if r["repeat"])
    first   = total - repeats
    vals    = [first, repeats]
    labels  = [f"Première visite\n({first})", f"Client fidèle\n({repeats})"]
    colors  = [LIGHT, BROWN]
    fig, ax = plt.subplots(figsize=(5, 4.5))
    wedges, texts, autotexts = ax.pie(
        vals, labels=None, colors=colors, autopct="%1.0f%%",
        startangle=90, wedgeprops=dict(linewidth=2, edgecolor="white"),
        pctdistance=0.72)
    for at in autotexts:
        at.set_color("white"); at.set_fontweight("bold"); at.set_fontsize(13)
    legend = [mpatches.Patch(color=c, label=l) for l, c in zip(labels, colors)]
    ax.legend(handles=legend, loc="lower center", bbox_to_anchor=(0.5, -0.1),
              ncol=2, frameon=False, fontsize=11)
    ax.set_title("Fidélité des clients")
    return _fig_to_b64(fig)

def chart_nights_distribution(rows):
    nights = [int(r["nights"]) for r in rows if r["nights"] and 0 < r["nights"] <= 14]
    counts = Counter(nights)
    xs = list(range(1, max(counts)+1))
    vals = [counts.get(x, 0) for x in xs]
    fig, ax = plt.subplots(figsize=(7, 4))
    colors = [BROWN if v == max(vals) else ACCENT for v in vals]
    bars = ax.bar(xs, vals, color=colors, width=0.6, zorder=3)
    ax.bar_label(bars, padding=4, fontsize=11, fontweight="bold")
    ax.set_title("Durée des séjours")
    ax.set_xlabel("Nuits")
    ax.set_ylabel("Réservations")
    ax.set_xticks(xs)
    ax.grid(axis="y", color=LIGHT, zorder=0)
    ax.set_ylim(0, max(vals) * 1.18)
    return _fig_to_b64(fig)

def chart_yoy_weekly(rows):
    """Cumulative bookings per week, year vs year."""
    years = sorted({r["arrival"].year for r in rows})
    if len(years) < 2:
        return None
    palette = [BROWN, ACCENT]
    fig, ax = plt.subplots(figsize=(11, 4.5))
    for i, yr in enumerate(years):
        yr_rows = [r for r in rows if r["arrival"].year == yr]
        weekly  = Counter(r["arrival"].isocalendar()[1] for r in yr_rows)
        xs = sorted(weekly.keys())
        cumul = np.cumsum([weekly[w] for w in xs])
        ax.plot(xs, cumul, marker="o", markersize=4, color=palette[i % len(palette)],
                linewidth=2.2, label=str(yr))
    ax.set_title("Réservations cumulées par semaine (année vs année)")
    ax.set_xlabel("Semaine de l'année")
    ax.set_ylabel("Réservations cumulées")
    ax.legend(frameon=False)
    ax.grid(color=LIGHT, zorder=0)
    return _fig_to_b64(fig)

def chart_source_trend(rows):
    """Bookings per quarter per source."""
    quarters = defaultdict(lambda: Counter())
    for r in rows:
        q = f"{r['arrival'].year} Q{((r['arrival'].month-1)//3)+1}"
        quarters[q][r["source"]] += 1
    qs = sorted(quarters.keys())
    sources = ["Booking.com", "Website", "Manual"]
    colors  = [SOURCE_COLORS[s] for s in sources]
    x = np.arange(len(qs))
    w = 0.25
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for i, src in enumerate(sources):
        vals = [quarters[q].get(src, 0) for q in qs]
        offset = (i - 1) * w
        bars = ax.bar(x + offset, vals, w, label=src, color=colors[i], zorder=3)
        ax.bar_label(bars, padding=2, fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(qs, rotation=30, ha="right")
    ax.set_title("Canal de réservation par trimestre")
    ax.set_ylabel("Réservations")
    ax.legend(frameon=False)
    ax.grid(axis="y", color=LIGHT, zorder=0)
    return _fig_to_b64(fig)

def chart_lead_time_by_month(rows):
    """Median booking lead time per arrival month — only past arrivals, all years combined."""
    MONTH_FR = ["Jan","Fév","Mar","Avr","Mai","Jun","Jul","Aoû","Sep","Oct","Nov","Déc"]
    today = date.today()
    monthly_leads = defaultdict(list)
    for r in rows:
        # Only count months that have fully passed so data is complete
        if r["arrival"] >= today:
            continue
        if r["booking_d"] and r["arrival"] >= r["booking_d"]:
            monthly_leads[r["arrival"].month].append((r["arrival"] - r["booking_d"]).days)
    if not monthly_leads:
        return None
    # Sort months starting from January
    months = list(range(1, 13))
    medians = [np.median(monthly_leads[m]) if monthly_leads[m] else None for m in months]
    ns      = [len(monthly_leads[m]) for m in months]
    # Filter out months with no data
    valid = [(MONTH_FR[m-1], med, n) for m, med, n in zip(months, medians, ns) if med is not None]
    labels, vals, counts = zip(*valid)
    fig, ax = plt.subplots(figsize=(11, 4.5))
    colors = [BROWN if v == max(vals) else ACCENT for v in vals]
    bars = ax.bar(labels, vals, color=colors, width=0.6, zorder=3)
    # Label each bar with median days + sample size
    for bar, v, n in zip(bars, vals, counts):
        ax.text(bar.get_x() + bar.get_width()/2, v + 1.5,
                f"{v:.0f}j", ha="center", va="bottom", fontsize=10,
                fontweight="bold", color=BROWN)
        ax.text(bar.get_x() + bar.get_width()/2, -3,
                f"n={n}", ha="center", va="top", fontsize=8, color=ACCENT)
    ax.set_title("Délai médian de réservation par mois d'arrivée")
    ax.set_ylabel("Jours à l'avance (médiane)")
    ax.grid(axis="y", color=LIGHT, zorder=0)
    ax.set_ylim(-6, max(vals) * 1.25)
    return _fig_to_b64(fig)


def chart_booking_day_of_week(rows):
    """Day-of-week bookings are made, split by season (2×2 grid)."""
    DAY_FR = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    SEASONS = {
        "Printemps (Mar-Mai)": [3, 4, 5],
        "Ete (Jun-Aou)":       [6, 7, 8],
        "Automne (Sep-Nov)":   [9, 10, 11],
        "Hiver (Dec-Fev)":     [12, 1, 2],
    }
    fig, axes = plt.subplots(2, 2, figsize=(12, 7))
    fig.suptitle("Jour de réservation par saison", fontsize=14, fontweight="bold", color=BROWN, y=1.01)
    axes_flat = axes.flatten()
    for ax, (season_label, months) in zip(axes_flat, SEASONS.items()):
        season_rows = [r for r in rows if r["booking_d"] and r["arrival"].month in months]
        counts = Counter(r["booking_d"].weekday() for r in season_rows)
        vals   = [counts.get(i, 0) for i in range(7)]
        if max(vals) == 0:
            ax.text(0.5, 0.5, "Pas de données", ha="center", va="center",
                    transform=ax.transAxes, color=ACCENT)
            ax.set_title(season_label, fontsize=11)
            continue
        colors = [BROWN if v == max(vals) else ACCENT if v >= sorted(vals)[-2] else GOLD
                  for v in vals]
        bars = ax.bar(DAY_FR, vals, color=colors, width=0.6, zorder=3)
        ax.bar_label(bars, padding=3, fontsize=9, fontweight="bold")
        ax.set_title(f"{season_label}  (n={sum(vals)})", fontsize=11)
        ax.set_ylim(0, max(vals) * 1.25)
        ax.grid(axis="y", color=LIGHT, zorder=0)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    fig.tight_layout()
    return _fig_to_b64(fig)


def chart_cancellation_rate(all_rows):
    """Cancellation rate (%) by booking source — uses all rows including cancelled."""
    total_by_src  = Counter(r["source"] for r in all_rows)
    cancel_by_src = Counter(r["source"] for r in all_rows if r["status"] == "Cancelled")
    sources = [s for s in ["Booking.com", "Website", "Manual"] if total_by_src.get(s, 0) > 0]
    rates   = [cancel_by_src.get(s, 0) / total_by_src[s] * 100 for s in sources]
    colors  = [SOURCE_COLORS.get(s, LIGHT) for s in sources]
    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(sources, rates, color=colors, width=0.5, zorder=3)
    ax.bar_label(bars, padding=4, fontsize=12, fontweight="bold",
                 labels=[f"{v:.0f}%" for v in rates])
    totals_lbl = [f"(sur {total_by_src[s]})" for s in sources]
    for bar, lbl in zip(bars, totals_lbl):
        ax.text(bar.get_x() + bar.get_width()/2, -2.5, lbl,
                ha="center", va="top", fontsize=8, color=ACCENT)
    ax.set_title("Taux d'annulation par canal")
    ax.set_ylabel("%")
    ax.grid(axis="y", color=LIGHT, zorder=0)
    ax.set_ylim(-5, max(rates) * 1.3 if rates else 20)
    return _fig_to_b64(fig)


def chart_revenue_per_night(rows):
    """Net revenue per night per booking source — true channel value."""
    src_rpn = defaultdict(list)
    for r in rows:
        if r["net_amount"] > 0 and r["nights"] > 0:
            src_rpn[r["source"]].append(r["net_amount"] / r["nights"])
    sources = [s for s in ["Booking.com", "Website", "Manual"] if src_rpn.get(s)]
    if not sources:
        return None
    means  = [np.mean(src_rpn[s]) for s in sources]
    colors = [SOURCE_COLORS.get(s, LIGHT) for s in sources]
    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(sources, means, color=colors, width=0.5, zorder=3)
    ax.bar_label(bars, padding=4, fontsize=12, fontweight="bold",
                 labels=[f"{v:.0f} €" for v in means])
    ax.set_title("Revenu net moyen par nuit (par canal)")
    ax.set_ylabel("€ / nuit")
    ax.grid(axis="y", color=LIGHT, zorder=0)
    ax.set_ylim(0, max(means) * 1.25)
    return _fig_to_b64(fig)


def chart_weekly_goal(rows):
    """Bookings per week vs the annual goal — green = hit, orange = missed."""
    from datetime import timedelta
    import calendar

    # Group bookings by ISO week key  "YYYY-Www"
    weekly = defaultdict(int)
    for r in rows:
        iso = r["arrival"].isocalendar()
        weekly[f"{iso[0]}-W{iso[1]:02d}"] += 1

    if not weekly:
        return None

    # Sort weeks and split by year
    all_weeks = sorted(weekly.keys())
    years = sorted({w.split("-")[0] for w in all_weeks})

    fig, axes = plt.subplots(len(years), 1,
                             figsize=(13, 4 * len(years)),
                             squeeze=False)
    fig.suptitle("Réservations par semaine vs objectif",
                 fontsize=14, fontweight="bold", color=BROWN, y=1.01)

    for ax, yr in zip(axes.flatten(), years):
        yr_int  = int(yr)
        goal    = BOOKING_GOALS.get(yr_int, 0)
        yr_weeks = sorted(w for w in all_weeks if w.startswith(yr))
        xs   = [int(w.split("-W")[1]) for w in yr_weeks]
        vals = [weekly[w] for w in yr_weeks]
        colors = [GOAL_HIT if v >= goal else GOAL_MISS for v in vals]
        bars = ax.bar(xs, vals, color=colors, width=0.7, zorder=3)
        ax.bar_label(bars, padding=2, fontsize=8, fontweight="bold")
        if goal:
            ax.axhline(goal, color=BROWN, linestyle="--", linewidth=1.5,
                       label=f"Objectif {yr}: {goal}/semaine")
            ax.legend(frameon=False, fontsize=10)
        ax.set_title(str(yr), fontsize=12, fontweight="bold", color=BROWN)
        ax.set_xlabel("Semaine de l'année")
        ax.set_ylabel("Réservations")
        ax.set_ylim(0, max(vals + [goal]) * 1.3)
        ax.grid(axis="y", color=LIGHT, zorder=0)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        # Count hit/miss
        hit  = sum(1 for v in vals if v >= goal)
        miss = len(vals) - hit
        ax.text(0.99, 0.95, f"✓ {hit} sem. atteintes  ✗ {miss} manquées",
                transform=ax.transAxes, ha="right", va="top",
                fontsize=9, color=BROWN)

    fig.tight_layout()
    return _fig_to_b64(fig)


def chart_table_dhotes(rows):
    """How many bookings include Table d'hôtes, by month."""
    MONTH_FR = ["Jan","Fév","Mar","Avr","Mai","Jun","Jul","Aoû","Sep","Oct","Nov","Déc"]
    td_by_month    = Counter(r["arrival"].month for r in rows if r["table_dhotes"])
    total_by_month = Counter(r["arrival"].month for r in rows)
    months = [m for m in range(1, 13) if total_by_month.get(m, 0) > 0]
    if not months or not any(td_by_month.values()):
        return None
    x   = np.arange(len(months))
    w   = 0.38
    tot = [total_by_month[m] for m in months]
    tdt = [td_by_month.get(m, 0) for m in months]
    fig, ax = plt.subplots(figsize=(11, 4))
    bars1 = ax.bar(x - w/2, tot, w, label="Total réservations", color=LIGHT,   zorder=3)
    bars2 = ax.bar(x + w/2, tdt, w, label="Dont Table d'hôtes", color=BROWN,  zorder=3)
    ax.bar_label(bars2, padding=3, fontsize=9, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([MONTH_FR[m-1] for m in months])
    ax.set_title("Réservations avec Table d'hôtes par mois")
    ax.set_ylabel("Réservations")
    ax.legend(frameon=False)
    ax.grid(axis="y", color=LIGHT, zorder=0)
    return _fig_to_b64(fig)


def chart_avg_revenue_per_room(rows):
    room_rev   = defaultdict(list)
    for r in rows:
        if r["net_amount"] > 0 and len(r["rooms"]) > 0:
            per_room = r["net_amount"] / len(r["rooms"])
            for rm in r["rooms"]:
                room_rev[rm].append(per_room)
    short = {room: room.split(" ")[0] for room in ROOMS}
    means = [np.mean(room_rev[rm]) if room_rev[rm] else 0 for rm in ROOMS]
    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar([short[r] for r in ROOMS], means,
                  color=ROOMS_COLORS, width=0.55, zorder=3)
    ax.bar_label(bars, padding=4, fontsize=11, fontweight="bold",
                 labels=[f"{v:.0f} €" for v in means])
    ax.set_title("Revenu moyen par chambre (€ net)")
    ax.set_ylabel("€")
    ax.grid(axis="y", color=LIGHT, zorder=0)
    ax.set_ylim(0, max(means) * 1.2)
    return _fig_to_b64(fig)

# ── KPI cards ─────────────────────────────────────────────────────────────────
def compute_kpis(rows):
    total     = len(rows)
    confirmed = sum(1 for r in rows if r["status"] == "Confirmed")
    revenue   = sum(r["net_amount"] for r in rows)
    avg_stay  = np.mean([r["nights"] for r in rows if r["nights"] > 0])
    repeat_rt = sum(1 for r in rows if r["repeat"]) / total * 100 if total else 0
    room_counts = Counter(rm for r in rows for rm in r["rooms"])
    max_count   = room_counts.most_common(1)[0][1]
    top_room    = " & ".join(rm.split()[0] for rm, cnt in room_counts.items() if cnt == max_count)
    leads     = [(r["arrival"] - r["booking_d"]).days
                 for r in rows if r["booking_d"] and r["arrival"] >= r["booking_d"]]
    med_lead  = int(np.median(leads)) if leads else 0
    # Current week goal
    this_year  = date.today().year
    this_week  = date.today().isocalendar()[1]
    goal       = BOOKING_GOALS.get(this_year, 0)
    week_count = sum(1 for r in rows
                     if r["arrival"].isocalendar()[0] == this_year
                     and r["arrival"].isocalendar()[1] == this_week)
    week_kpi   = f"{week_count}/{goal}" if goal else str(week_count)
    week_icon  = "✅" if goal and week_count >= goal else "🎯"
    td_count   = sum(1 for r in rows if r["table_dhotes"])
    return [
        ("🏠", f"{total}", "Réservations totales"),
        ("💶", f"{revenue:,.0f} €", "Revenus nets (après commissions)"),
        ("🌙", f"{avg_stay:.1f} nuits", "Séjour moyen"),
        ("⭐", f"{repeat_rt:.0f}%", "Clients fidèles"),
        ("🏆", top_room, "Chambre star"),
        ("📅", f"{med_lead} jours", "Délai médian de réservation"),
        (week_icon, week_kpi, f"Cette semaine (objectif {this_year})"),
        ("🍽️", f"{td_count}", "Réservations Table d'hôtes"),
    ]

# ── HTML builder ──────────────────────────────────────────────────────────────
def build_html(kpis, charts):
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    def card(b64, title, note=""):
        note_html = f'<p class="note">{note}</p>' if note else ""
        return f"""
        <div class="chart-card">
            <h3>{title}</h3>
            <img src="data:image/png;base64,{b64}" alt="{title}">
            {note_html}
        </div>"""

    kpi_html = "".join(f"""
        <div class="kpi">
            <span class="kpi-icon">{icon}</span>
            <span class="kpi-val">{val}</span>
            <span class="kpi-lbl">{lbl}</span>
        </div>""" for icon, val, lbl in kpis)

    charts_html = ""
    for b64, title, note, wide in charts:
        cls = "chart-card wide" if wide else "chart-card"
        note_html = f'<p class="note">{note}</p>' if note else ""
        charts_html += f"""
        <div class="{cls}">
            <h3>{title}</h3>
            <img src="data:image/png;base64,{b64}" alt="{title}">
            {note_html}
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>La Ferme de la Cour — Analytiques</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Arial, sans-serif; background: {BG}; color: {TEXT_COLOR}; }}
  header {{ background: {BROWN}; color: white; padding: 28px 32px 20px; }}
  header h1 {{ font-size: 1.7rem; font-weight: bold; }}
  header p  {{ font-size: 0.9rem; opacity: 0.8; margin-top: 4px; }}
  .kpis {{ display: flex; flex-wrap: wrap; gap: 16px; padding: 28px 32px 8px; }}
  .kpi  {{ background: white; border-radius: 12px; padding: 18px 22px;
           flex: 1 1 140px; box-shadow: 0 2px 8px rgba({SHADOW_RGB},.1);
           display: flex; flex-direction: column; align-items: center; text-align: center; }}
  .kpi-icon {{ font-size: 1.7rem; margin-bottom: 6px; }}
  .kpi-val  {{ font-size: 1.4rem; font-weight: bold; color: {BROWN}; }}
  .kpi-lbl  {{ font-size: 0.78rem; color: {SECONDARY}; margin-top: 3px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(460px, 1fr));
           gap: 20px; padding: 24px 32px 40px; }}
  .chart-card {{ background: white; border-radius: 14px; padding: 20px 22px;
                 box-shadow: 0 2px 8px rgba({SHADOW_RGB},.1); }}
  .chart-card.wide {{ grid-column: 1 / -1; }}
  .chart-card h3 {{ font-size: 0.95rem; color: {SECONDARY}; margin-bottom: 12px;
                    text-transform: uppercase; letter-spacing: .06em; }}
  .chart-card img {{ width: 100%; height: auto; border-radius: 6px; }}
  .note {{ font-size: 0.8rem; color: #9E9E9E; margin-top: 10px; font-style: italic; }}
  footer {{ text-align: center; padding: 20px; font-size: 0.8rem; color: {GOLD}; }}
  @media (max-width: 600px) {{ .grid {{ grid-template-columns: 1fr; padding: 16px; }} }}
</style>
</head>
<body>
<header>
  <h1>🏡 La Ferme de la Cour — Analytiques</h1>
  <p>Mis à jour le {now}</p>
</header>
<section class="kpis">{kpi_html}</section>
<section class="grid">{charts_html}</section>
<footer>La Ferme de la Cour · Généré automatiquement</footer>
</body>
</html>"""

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print("Chargement des données…")
    rows      = load_data(include_cancelled=False)
    all_rows  = load_data(include_cancelled=True)
    print(f"  {len(rows)} réservations actives, {len(all_rows)} au total (avec annulations)")

    print("Génération des graphiques…")
    kpis = compute_kpis(rows)

    charts = []  # (b64, title, note, wide)

    c = chart_room_popularity(rows)
    charts.append((c, "Chambres les plus réservées", "", False))

    c = chart_source(rows)
    charts.append((c, "Canal de réservation", "", False))

    c = chart_monthly(rows)
    charts.append((c, "Réservations par mois", "Réservations confirmées et modifiées uniquement", True))

    c = chart_revenue_month(rows)
    charts.append((c, "Revenus nets par mois", "Booking.com : -15% commission. Mettre à jour dans config.py quand le taux exact est confirmé.", True))

    c = chart_yoy_weekly(rows)
    if c:
        charts.append((c, "Rythme de croissance (cumulé par semaine)", "Comparaison année vs année", True))

    c = chart_source_trend(rows)
    charts.append((c, "Canal de réservation par trimestre", "", True))

    c = chart_day_of_week(rows)
    charts.append((c, "Jour d'arrivée préféré", "", False))

    c = chart_nights_distribution(rows)
    charts.append((c, "Durée des séjours", "", False))

    c = chart_nationality(rows)
    charts.append((c, "Nationalités (top 8)", "", False))

    c = chart_avg_revenue_per_room(rows)
    charts.append((c, "Revenu moyen par chambre (net)", "Après commission Booking.com. Divisé si plusieurs chambres réservées ensemble.", False))

    c = chart_lead_time(rows)
    if c:
        charts.append((c, "Délai de réservation", "Jours entre date de réservation et arrivée", False))

    c = chart_repeat_guests(rows)
    charts.append((c, "Fidélité des clients", "", False))

    # ── Marketing insights ────────────────────────────────────────────────────
    c = chart_booking_day_of_week(rows)
    charts.append((c, "Quel jour réserve-t-on le plus ? (par saison)",
                   "Jour où la réservation est faite (pas le jour d'arrivée) — basé sur la saison d'arrivée", True))

    c = chart_lead_time_by_month(rows)
    if c:
        charts.append((c, "Combien de jours à l'avance réserve-t-on selon le mois ?",
                       "Utile pour planifier vos campagnes publicitaires", True))

    c = chart_cancellation_rate(all_rows)
    charts.append((c, "Taux d'annulation par canal", "", False))

    c = chart_revenue_per_night(rows)
    if c:
        charts.append((c, "Revenu net moyen par nuit (par canal)",
                       "Après commission Booking.com — valeur réelle de chaque canal", False))

    # ── Goals & Table d'hôtes ─────────────────────────────────────────────────
    c = chart_weekly_goal(rows)
    if c:
        charts.append((c, "Objectif hebdomadaire de réservations",
                       "Vert = objectif atteint · Orange = objectif manqué", True))

    c = chart_table_dhotes(rows)
    if c:
        charts.append((c, "Réservations avec Table d'hôtes",
                       "Nombre de séjours incluant le dîner à la table d'hôtes", True))

    html = build_html(kpis, charts)

    out = os.path.join(GITHUB_REPO_PATH, DOCS_FOLDER, "analytics.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  ✓ Sauvegardé : {out}")
    print("Terminé!")

if __name__ == "__main__":
    main()
