"""
analytics.py
────────────
Builds docs/analytics.html: key numbers and charts about all bookings.

    python analytics.py

GitHub Actions runs it after schedule_generator.py. The page is only rewritten
when its content changed, so the repo doesn't grow on every run.
"""
from __future__ import annotations

import base64
import io
import logging
import warnings
from collections import Counter, defaultdict
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

import clock
import pages
from auth import get_worksheet
from bookings import Booking, load_bookings
from config import BOOKING_GOALS, ROOMS
from guests import nationality_in_french

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
log = logging.getLogger(__name__)

# ── Colours (L'Ardenne Authentique palette) ───────────────────────────────────
BROWN         = "#4A5D4E"   # Vert Épicéa — main colour
SECONDARY     = "#7A8C7E"
ACCENT        = "#D4A373"   # Terre de Sienne
LIGHT         = "#C9D5CB"
GOLD          = "#A8B8AC"
BG            = "#F1EFE7"   # Laine Grège
TEXT_COLOR    = "#2C2C2C"   # Ardoise Fumée
ROOMS_COLORS  = ["#4A5D4E", "#D4A373", "#C9D5CB", "#E8E2D8"]
SOURCE_COLORS = {"Booking.com": "#4A5D4E", "Website": "#D4A373", "Email/phone": "#7A8C7E",
                 "Social Deal": "#A8B8AC", "Expedia": "#C9D5CB", "Umfulana": "#8B6355",
                 "Unknown": "#E8E2D8"}
GOAL_HIT      = BROWN
GOAL_MISS     = ACCENT
PAGE_COLORS   = {"brown": BROWN, "secondary": SECONDARY, "gold": GOLD, "bg": BG,
                 "text": TEXT_COLOR, "shadow_rgb": "74,93,78"}

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


def main():
    bookings = [b for b in load_bookings(get_worksheet()) if counts_in_stats(b)]
    active = [b for b in bookings if not b.is_cancelled]
    log.info(f"{len(active)} active bookings, {len(bookings)} including cancellations")

    html = pages.render(
        "analytics.html",
        kpis=key_numbers(active),
        charts=dashboard_charts(active, bookings),
        colors=PAGE_COLORS,
    )
    pages.write("analytics.html", html)


def counts_in_stats(booking: Booking) -> bool:
    """Real bookings only: placeholders without status, reference or arrival are skipped."""
    return (booking.status not in ("", "Unknown")
            and bool(booking.reference) and booking.arrival is not None)


def stats_nationality(booking: Booking) -> str | None:
    if booking.nationality.strip() in ("", "Unknown"):
        return None
    return nationality_in_french(booking.nationality)


def dashboard_charts(rows: list[Booking], rows_with_cancelled: list[Booking]) -> list[dict]:
    """Every chart of the page, top to bottom. Charts without enough data are left out."""
    charts = [
        (chart_room_popularity(rows), "Chambres les plus réservées", "", False),
        (chart_source(rows), "Canal de réservation", "", False),
        (chart_monthly(rows), "Réservations par mois",
         "Réservations confirmées et modifiées uniquement", True),
        (chart_monthly_revenue_detail(rows), "Revenus nets — 5 derniers mois",
         "Mois en cours mis en évidence. Revenus nets après commissions.", True),
        (chart_revenue_month(rows), "Revenus nets par mois",
         "Booking.com : -15% commission. Mettre à jour dans config.py quand le taux exact est confirmé.", True),
        (chart_yoy_weekly(rows), "Rythme de croissance (cumulé par semaine)",
         "Comparaison année vs année", True),
        (chart_source_trend(rows), "Canal de réservation par trimestre", "", True),
        (chart_day_of_week(rows), "Jour d'arrivée préféré", "", False),
        (chart_nights_distribution(rows), "Durée des séjours", "", False),
        (chart_nationality(rows), "Nationalités (top 8)", "", False),
        (chart_avg_revenue_per_room(rows), "Revenu moyen par chambre (net)",
         "Après commission Booking.com. Divisé si plusieurs chambres réservées ensemble.", False),
        (chart_lead_time(rows), "Délai de réservation",
         "Jours entre date de réservation et arrivée", False),
        (chart_repeat_guests(rows), "Fidélité des clients", "", False),
        # Marketing insights
        (chart_booking_day_of_week(rows), "Quel jour réserve-t-on le plus ? (par saison)",
         "Jour où la réservation est faite (pas le jour d'arrivée) — basé sur la saison d'arrivée", True),
        (chart_lead_time_by_month(rows), "Combien de jours à l'avance réserve-t-on selon le mois ?",
         "Utile pour planifier vos campagnes publicitaires", True),
        (chart_cancellation_rate(rows_with_cancelled), "Taux d'annulation par canal", "", False),
        (chart_revenue_per_night(rows), "Revenu net moyen par nuit (par canal)",
         "Après commission Booking.com — valeur réelle de chaque canal", False),
        # Goals & meals
        (chart_weekly_goal(rows), "Objectif hebdomadaire de réservations",
         "Vert = objectif atteint · Orange = objectif manqué", True),
        (chart_table_dhotes(rows), "🍽️🥐 Repas par mois",
         "Table d'hôtes (dîner) et petit-déjeuner inclus — Booking.com et Website auto-inclus", True),
    ]
    return [{"png": png, "title": title, "note": note, "wide": wide}
            for png, title, note, wide in charts if png]


def key_numbers(rows: list[Booking]) -> list[tuple[str, str, str]]:
    """(icon, value, label) of the cards at the top of the page."""
    today = clock.today()
    goal = BOOKING_GOALS.get(today.year, 0)
    booked_this_week = sum(1 for r in rows if r.booked_on
                           and r.booked_on.isocalendar()[:2] == today.isocalendar()[:2])
    platform_bookings = [r for r in rows if r.source != "Email/phone"]
    room_counts = Counter(room for r in rows for room in r.rooms)
    top_count = room_counts.most_common(1)[0][1]
    leads = [(r.arrival - r.booked_on).days for r in rows if r.booked_on and r.arrival >= r.booked_on]
    covers = [r.guest_count for r in rows if r.guest_count > 0]

    return [
        ("🏠", f"{len(platform_bookings)}", "Réservations plateformes (hors email/tél)"),
        ("💶", f"{sum(r.net_amount for r in rows if (r.arrival.year, r.arrival.month) == (today.year, today.month)):,.0f} €",
         f"Ce mois ({pages.MONTHS_FR[today.month]})"),
        ("💶", f"{sum(r.net_amount for r in rows):,.0f} €", "Revenus nets (après commissions)"),
        ("🌙", f"{np.mean([r.nights for r in rows if r.nights > 0]):.1f} nuits", "Séjour moyen"),
        ("⭐", f"{sum(1 for r in rows if r.is_repeat_guest) / len(rows) * 100 if rows else 0:.0f}%", "Clients fidèles"),
        ("🏆", " & ".join(room.split()[0] for room, n in room_counts.items() if n == top_count), "Chambre star"),
        ("📅", f"{int(np.median(leads)) if leads else 0} jours", "Délai médian de réservation"),
        ("✅" if goal and booked_this_week >= goal else "🎯",
         f"{booked_this_week}/{goal}" if goal else str(booked_this_week),
         f"Cette semaine (objectif {today.year})"),
        ("🍽️", f"{sum(1 for r in rows if r.has_table_dhotes)}", "Table d'hôtes"),
        ("🥐", f"{sum(1 for r in rows if r.breakfast_booked)}", "Petit-déjeuner (réservé explicitement)"),
        ("👥", f"{np.mean(covers):.1f}" if covers else "—", "Couverts en moyenne"),
        ("💆", f"{sum(1 for r in rows if r.massage)}", "Massages réservés"),
    ]


# ── Charts (each returns a base64 PNG, or None when there is too little data) ─

def _fig_to_b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)
    return base64.b64encode(buf.read()).decode()


def _sources_by_volume(rows):
    """Booking sources present in rows, most bookings first."""
    return [s for s, _ in Counter(r.source for r in rows).most_common()]


def chart_room_popularity(rows):
    counts = Counter(rm for r in rows for rm in r.rooms)
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
    counts = Counter(r.arrival.weekday() for r in rows)
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
    counts = Counter((r.arrival.year, r.arrival.month) for r in rows)
    years  = sorted({r.arrival.year for r in rows})
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
    counts = Counter(n for n in map(stats_nationality, rows) if n)
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
    counts = Counter(r.source for r in rows)
    labels = list(counts.keys())
    vals   = list(counts.values())
    colors = [SOURCE_COLORS.get(l, LIGHT) for l in labels]
    fig, ax = plt.subplots(figsize=(8, 7))
    wedges, texts, autotexts = ax.pie(
        vals, labels=None, colors=colors, autopct="%1.0f%%",
        startangle=140, wedgeprops=dict(linewidth=2, edgecolor="white"),
        pctdistance=0.78)
    for at in autotexts:
        at.set_color("white"); at.set_fontweight("bold"); at.set_fontsize(14)
    legend = [mpatches.Patch(color=c, label=f"{l}  ({v})")
              for l, v, c in zip(labels, vals, colors)]
    ax.legend(handles=legend, loc="lower center", bbox_to_anchor=(0.5, -0.10),
              ncol=len(labels), frameon=False, fontsize=13)
    ax.set_title("Canal de réservation", fontsize=15)
    return _fig_to_b64(fig)

def chart_revenue_month(rows):
    MONTH_FR = ["Jan","Fév","Mar","Avr","Mai","Jun","Jul","Aoû","Sep","Oct","Nov","Déc"]
    revenue = defaultdict(float)
    for r in rows:
        revenue[(r.arrival.year, r.arrival.month)] += r.net_amount
    years  = sorted({r.arrival.year for r in rows})
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
    leads = [(r.arrival - r.booked_on).days
             for r in rows if r.booked_on and r.arrival >= r.booked_on]
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
    repeats = sum(1 for r in rows if r.is_repeat_guest)
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
    nights = [int(r.nights) for r in rows if r.nights and 0 < r.nights <= 14]
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
    years = sorted({r.arrival.year for r in rows})
    if len(years) < 2:
        return None
    palette = [BROWN, ACCENT]
    fig, ax = plt.subplots(figsize=(11, 4.5))
    for i, yr in enumerate(years):
        yr_rows = [r for r in rows if r.arrival.year == yr]
        weekly  = Counter(r.arrival.isocalendar()[1] for r in yr_rows)
        xs = sorted(weekly.keys())
        cumul = np.cumsum([weekly[w] for w in xs])
        ax.plot(xs, cumul, marker="o", markersize=4, color=palette[i % len(palette)],
                linewidth=2.2, label=str(yr))
    # Vertical line for current week
    current_week = clock.today().isocalendar()[1]
    ax.axvline(current_week, color=TEXT_COLOR, linestyle="--", linewidth=1.5,
               alpha=0.6, zorder=5, label=f"Semaine actuelle (S{current_week})")
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
        q = f"{r.arrival.year} Q{((r.arrival.month-1)//3)+1}"
        quarters[q][r.source] += 1
    qs = sorted(quarters.keys())
    sources = _sources_by_volume(rows)
    colors  = [SOURCE_COLORS.get(s, LIGHT) for s in sources]
    x = np.arange(len(qs))
    n = len(sources)
    w = min(0.8 / n, 0.3)
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for i, src in enumerate(sources):
        vals = [quarters[q].get(src, 0) for q in qs]
        offset = (i - (n - 1) / 2) * w
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
    today = clock.today()
    monthly_leads = defaultdict(list)
    for r in rows:
        # Only count months that have fully passed so data is complete
        if r.arrival >= today:
            continue
        if r.booked_on and r.arrival >= r.booked_on:
            monthly_leads[r.arrival.month].append((r.arrival - r.booked_on).days)
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
        season_rows = [r for r in rows if r.booked_on and r.arrival.month in months]
        counts = Counter(r.booked_on.weekday() for r in season_rows)
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
    total_by_src  = Counter(r.source for r in all_rows)
    cancel_by_src = Counter(r.source for r in all_rows if r.is_cancelled)
    sources = _sources_by_volume(all_rows)
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
        if r.net_amount > 0 and r.nights > 0:
            src_rpn[r.source].append(r.net_amount / r.nights)
    sources = [s for s in _sources_by_volume(rows) if src_rpn.get(s)]
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
    """Bookings RECEIVED per week (by booking_date) vs the annual goal — primary = hit, accent = missed."""

    today = clock.today()

    # Group bookings by the ISO week of the booking_date (when the reservation was made)
    weekly = defaultdict(int)
    for r in rows:
        if not r.booked_on:
            continue
        iso = r.booked_on.isocalendar()
        weekly[f"{iso[0]}-W{iso[1]:02d}"] += 1

    if not weekly:
        return None

    years = sorted({w.split("-")[0] for w in weekly})

    fig, axes = plt.subplots(len(years), 1,
                             figsize=(13, 4 * len(years)),
                             squeeze=False)
    fig.suptitle("Réservations reçues par semaine vs objectif",
                 fontsize=14, fontweight="bold", color=BROWN, y=1.01)

    for ax, yr in zip(axes.flatten(), years):
        yr_int = int(yr)
        goal   = BOOKING_GOALS.get(yr_int, 0)

        # For current year: show weeks 1 → current week only.
        # For past years: show the full year (all 52/53 weeks).
        if yr_int == today.year:
            max_week    = today.isocalendar()[1]
            current_week = max_week
        else:
            max_week    = date(yr_int, 12, 28).isocalendar()[1]  # dec-28 is always in last ISO week
            current_week = None

        xs   = list(range(1, max_week + 1))
        vals = [weekly.get(f"{yr}-W{w:02d}", 0) for w in xs]

        colors = [GOAL_HIT if v >= goal else GOAL_MISS for v in vals]

        # Current week: keep hit/miss colour but add a thick border
        if current_week:
            ci = current_week - 1  # xs is 1-indexed, list is 0-indexed
            colors[ci] = GOAL_HIT if vals[ci] >= goal else GOAL_MISS

        bars = ax.bar(xs, vals, color=colors, width=0.7, zorder=3)

        # Outline the current week bar
        if current_week:
            bars[current_week - 1].set_edgecolor(BROWN)
            bars[current_week - 1].set_linewidth(2.5)

        # Bar labels — skip zeros to keep chart readable
        ax.bar_label(bars, padding=2, fontsize=8, fontweight="bold",
                     labels=[str(v) if v > 0 else "" for v in vals])

        # Goal line
        if goal:
            ax.axhline(goal, color=BROWN, linestyle="--", linewidth=1.5,
                       label=f"Objectif: {goal} rés./sem.")
            ax.legend(frameon=False, fontsize=10)

        ymax = max(vals + [goal or 0, 1]) * 1.35
        ax.set_ylim(0, ymax)

        # "Sem. XX" annotation above the current week bar
        if current_week:
            ax.text(current_week, ymax * 0.97,
                    f"▼ S{current_week}",
                    ha="center", va="top", fontsize=8,
                    fontweight="bold", color=BROWN)

        # Hit/miss count in the subplot title
        hit  = sum(1 for v in vals if v >= goal)
        miss = sum(1 for v in vals if v <  goal and v > 0)  # only non-zero weeks
        ax.set_title(
            f"{yr}   ✓ {hit} sem. atteintes   ✗ {miss} manquées",
            fontsize=11, fontweight="bold", color=BROWN
        )
        ax.set_xlabel("Semaine de l'année (date de réservation)")
        ax.set_ylabel("Réservations reçues")
        ax.grid(axis="y", color=LIGHT, zorder=0)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    fig.tight_layout()
    return _fig_to_b64(fig)


def chart_monthly_revenue_detail(rows):
    """Net revenue for the current month and the 4 previous months — clearly labelled bar chart."""
    MONTH_FR = ["Jan","Fév","Mar","Avr","Mai","Jun","Jul","Aoû","Sep","Oct","Nov","Déc"]
    today = clock.today()

    # Build list of (year, month) for last 5 months ending with current month
    months = []
    for delta in range(4, -1, -1):
        m = today.month - delta
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        months.append((y, m))

    rev = defaultdict(float)
    for r in rows:
        key = (r.arrival.year, r.arrival.month)
        rev[key] += r.net_amount

    # Need at least 2 months with data to be meaningful
    data_months = [(y, m) for y, m in months if rev.get((y, m), 0) > 0]
    if len(data_months) < 2:
        return None

    labels = []
    vals   = []
    colors = []
    for y, m in months:
        short_y = str(y)[2:]
        is_current = (y == today.year and m == today.month)
        labels.append(f"{MONTH_FR[m-1]} {short_y}" + (" ●" if is_current else ""))
        vals.append(rev.get((y, m), 0))
        colors.append(BROWN if is_current else LIGHT)

    fig, ax = plt.subplots(figsize=(10, 4))
    bars = ax.bar(labels, vals, color=colors, width=0.55, zorder=3)
    # Label every bar with the euro amount
    ax.bar_label(bars, padding=5, fontsize=11, fontweight="bold",
                 labels=[f"{v:,.0f} €" if v else "" for v in vals])
    ax.set_title("Revenus nets — 5 derniers mois")
    ax.set_ylabel("€ net")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f} €"))
    ax.grid(axis="y", color=LIGHT, zorder=0)
    ax.set_ylim(0, max(vals) * 1.22 if max(vals) else 1)
    fig.tight_layout()
    return _fig_to_b64(fig)


def chart_table_dhotes(rows):
    """How many bookings include Table d'hôtes or Breakfast, by month."""
    MONTH_FR = ["Jan","Fév","Mar","Avr","Mai","Jun","Jul","Aoû","Sep","Oct","Nov","Déc"]
    td_by_month    = Counter(r.arrival.month for r in rows if r.has_table_dhotes)
    bf_by_month    = Counter(r.arrival.month for r in rows if r.has_breakfast)
    total_by_month = Counter(r.arrival.month for r in rows)
    months = [m for m in range(1, 13) if total_by_month.get(m, 0) > 0]
    has_td = any(td_by_month.values())
    has_bf = any(bf_by_month.values())
    if not months or (not has_td and not has_bf):
        return None
    x   = np.arange(len(months))
    w   = 0.26
    tot = [total_by_month[m] for m in months]
    tdt = [td_by_month.get(m, 0) for m in months]
    bft = [bf_by_month.get(m, 0)  for m in months]
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.bar(x - w,     tot, w, label="Total réservations", color=LIGHT,    zorder=3)
    bars2 = ax.bar(x,         tdt, w, label="🍽️ Table d'hôtes",  color=BROWN,    zorder=3)
    bars3 = ax.bar(x + w,     bft, w, label="🥐 Petit-déjeuner",  color=ACCENT,   zorder=3)
    ax.bar_label(bars2, padding=3, fontsize=9, fontweight="bold")
    ax.bar_label(bars3, padding=3, fontsize=9, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([MONTH_FR[m-1] for m in months])
    ax.set_title("🍽️🥐 Repas par mois")
    ax.set_ylabel("Réservations")
    ax.legend(frameon=False)
    ax.grid(axis="y", color=LIGHT, zorder=0)
    return _fig_to_b64(fig)


def chart_avg_revenue_per_room(rows):
    room_rev   = defaultdict(list)
    for r in rows:
        if r.net_amount > 0 and len(r.rooms) > 0:
            per_room = r.net_amount / len(r.rooms)
            for rm in r.rooms:
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


if __name__ == "__main__":
    main()
