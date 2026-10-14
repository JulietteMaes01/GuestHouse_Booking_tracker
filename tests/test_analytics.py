"""Analytics charts: which sources and meals they count."""
from datetime import date

import pytest

import analytics
from config import COLUMNS
from fake_sheet import FakeWorksheet


def booking(source, status="Confirmed", amount=200.0, nights=2, breakfast=False):
    return {
        "source": source, "status": status, "amount": amount, "net_amount": amount,
        "nights": nights, "arrival": date(2026, 5, 1), "breakfast": breakfast,
    }


@pytest.fixture
def chart_axes(monkeypatch):
    """Make chart functions return their matplotlib axes instead of a PNG."""
    monkeypatch.setattr(analytics, "_fig_to_b64", lambda fig: fig.axes[0])


def bar_labels(ax):
    return [label.get_text() for label in ax.get_xticklabels()]


ROWS = [booking("Booking.com"), booking("Booking.com"), booking("Email/phone"),
        booking("Expedia"), booking("Umfulana", status="Cancelled")]


def test_cancellation_rate_shows_every_source(chart_axes):
    ax = analytics.chart_cancellation_rate(ROWS)
    assert bar_labels(ax) == ["Booking.com", "Email/phone", "Expedia", "Umfulana"]


def test_revenue_per_night_shows_every_source(chart_axes):
    ax = analytics.chart_revenue_per_night(ROWS)
    assert bar_labels(ax) == ["Booking.com", "Email/phone", "Expedia", "Umfulana"]


def test_umfulana_bookings_include_breakfast(monkeypatch):
    worksheet = FakeWorksheet.from_rows(COLUMNS, [{
        "booking_source": "Umfulana", "status": "Confirmed", "reference": "M0001",
        "arrival_date": "01/05/2026", "departure_date": "03/05/2026", "breakfast": ""}])
    monkeypatch.setattr(analytics, "get_worksheet", lambda: worksheet)

    [row] = analytics.load_data()
    assert row["breakfast"] is True
