"""
Turning page data into the HTML files GitHub Pages publishes (docs/).
Page layouts live in templates/; this module only fills and saves them.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date

from jinja2 import Environment, FileSystemLoader, select_autoescape

import clock
import config
from guests import flag_for

log = logging.getLogger(__name__)

DAYS_FR   = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MONTHS_FR = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
             "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]


def weekday(day: date) -> str:
    return DAYS_FR[day.weekday()]                                  # "Mercredi"


def day_month(day: date) -> str:
    return f"{weekday(day)} {day.day} {MONTHS_FR[day.month]}"      # "Mercredi 14 Octobre"


def long_date(day: date) -> str:
    return f"{day_month(day)} {day.year}"                          # "Mercredi 14 Octobre 2026"


def short_date(day: date) -> str:
    return f"{weekday(day)} {day.day}/{day.month}"                 # "Mercredi 14/10"


def sheet_date(day: date | None) -> str:
    return day.strftime("%d/%m/%Y") if day else "?"                # "14/10/2026"


_templates = Environment(
    loader=FileSystemLoader(config.TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)
_templates.globals.update(flag_for=flag_for, owner=config.OWNER_NAME)
_templates.filters.update(weekday=weekday, day_month=day_month, long_date=long_date,
                          short_date=short_date, sheet_date=sheet_date)

NAV_TABS = [
    ("index.html",     "📅 Aujourd'hui"),
    ("weekly.html",    "📆 Cette semaine"),
    ("upcoming.html",  "🗓️ Semaines prochaines"),
    ("analytics.html", "📊 Analytiques"),
]


def render(page: str, **context) -> str:
    """Fill templates/<page> with context. `page` is also the active nav tab."""
    return _templates.get_template(page).render(
        page=page, nav_tabs=NAV_TABS, generated_at=clock.now(), **context)


def write(page: str, html: str, unless_only_changed: str = "") -> None:
    """
    Save the page into docs/. With unless_only_changed (a regex), the existing
    file is kept when that is the only difference, so git sees no change.
    """
    os.makedirs(config.DOCS_DIR, exist_ok=True)
    path = os.path.join(config.DOCS_DIR, page)
    if unless_only_changed and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            current = fh.read()
        if re.sub(unless_only_changed, "", current) == re.sub(unless_only_changed, "", html):
            log.info(f"Unchanged → {path}")
            return
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    log.info(f"Written → {path}")
