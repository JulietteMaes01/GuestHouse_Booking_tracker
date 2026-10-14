"""
The farm's clock: today's date and time in Belgium.

GitHub Actions runs in UTC, so date.today() there is yesterday between
midnight and 2am Belgian time. Page generators use these instead.
(The booking form doesn't: it runs on a laptop that is already in Belgium.)
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

FARM_TIMEZONE = ZoneInfo("Europe/Brussels")


def now() -> datetime:
    return datetime.now(FARM_TIMEZONE)


def today() -> date:
    return now().date()
