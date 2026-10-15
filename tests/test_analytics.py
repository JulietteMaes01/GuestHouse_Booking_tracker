"""Analytics charts: which sources and meals they count."""
import pytest

import analytics
from bookings import Booking
from config import COLUMNS
from fake_sheet import FakeWorksheet


def booking(source, status="Confirmed", arrival="01/05/2026", cabin="", amount="400"):
    return Booking.from_row({
        "booking_source": source, "status": status, "reference": "M0001",
        "arrival_date": arrival, "departure_date": arrival if cabin else "03/05/2026",
        "amount": amount, "nights": "0" if cabin else "2", "cabane": cabin, "guest_count": "2"})


@pytest.fixture
def chart_axes(monkeypatch):
    """Make chart functions return their matplotlib axes instead of a PNG."""
    monkeypatch.setattr(analytics, "_fig_to_b64", lambda fig: fig.axes[0])


def bar_labels(ax):
    """Channel names under the bars (the second line is the number of bookings)."""
    return [label.get_text().split("\n")[0] for label in ax.get_xticklabels()]


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

    [row] = analytics.load_bookings(worksheet)
    assert row.has_breakfast is True


def test_each_year_gets_its_own_colour(chart_axes):
    rows = [booking("Website", arrival=f"01/05/{year}") for year in (2025, 2026, 2027)]
    ax = analytics.chart_monthly(rows)
    year_colours = {tuple(ax.containers[i].patches[0].get_facecolor()) for i in range(3)}
    assert len(year_colours) == 3


def test_cabin_orders_get_their_own_meal_bar(chart_axes):
    ax = analytics.chart_meals([booking("Website")], [booking("Email/phone", cabin="Bonne aventure")])
    assert [t.get_text() for t in ax.get_legend().get_texts()][-1] == "Livraisons cabanes"


def test_cabin_orders_count_in_revenue_not_in_bookings():
    rows = [booking("Website", amount="400")]
    cabins = [booking("Email/phone", cabin="Bonne aventure", amount="60")]
    numbers = {label: value for _, value, label in analytics.key_numbers(rows, cabins)}
    assert numbers["Revenus nets (après commissions)"] == "460 €"
    assert numbers["Réservations plateformes (hors email/tél)"] == "1"


def test_sources_without_any_amount_are_named():
    rows = [booking("Website"), booking("Social Deal", amount="0")]
    assert analytics._sources_without_amounts(rows) == ["Social Deal"]


def test_cabin_numbers_at_the_top():
    cabins = [booking("Email/phone", cabin="Bonne aventure", amount="60"),
              booking("Email/phone", cabin="Couleurs du monde", amount="45")]
    numbers = {label: value for _, value, label in analytics.key_numbers([booking("Website")], cabins)}
    assert (numbers["Livraisons cabanes"], numbers["Revenus cabanes"]) == ("2", "105 €")


def test_cabin_chart_only_when_there_are_orders(monkeypatch):
    monkeypatch.setattr(analytics, "_fig_to_b64", lambda fig: fig.axes[0])
    assert analytics.chart_cabin_deliveries([]) is None
    ax = analytics.chart_cabin_deliveries([booking("Email/phone", cabin="Bonne aventure", amount="60")])
    assert "1\n60 €" in [t.get_text() for t in ax.texts]
