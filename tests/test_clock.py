from datetime import date

from freezegun import freeze_time

import clock


@freeze_time("2026-10-14 23:30:00")  # UTC — already 15 October in Belgium
def test_today_is_belgian_date_late_at_night():
    assert clock.today() == date(2026, 10, 15)


@freeze_time("2026-10-14 08:00:00")
def test_today_during_the_day():
    assert clock.today() == date(2026, 10, 14)
