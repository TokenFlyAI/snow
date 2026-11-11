from datetime import date

import numpy as np
import pytest

from pipeline.process import aggregate


def _t(s: str) -> np.datetime64:
    return np.datetime64(s, "h")


def test_hour_assignment_to_ski_day_pacific():
    # PST = UTC-8. Values are stamped at the END of the hour they cover.
    times = np.array([
        _t("2026-01-15T00"),   # 15:00-16:00 PST Jan 14 -> day of Jan 14
        _t("2026-01-15T01"),   # 16:00-17:00 PST Jan 14 -> night of Jan 15
        _t("2026-01-15T16"),   # 07:00-08:00 PST Jan 15 -> night of Jan 15
        _t("2026-01-15T17"),   # 08:00-09:00 PST Jan 15 -> day of Jan 15
        _t("2026-01-16T00"),   # 15:00-16:00 PST Jan 15 -> day of Jan 15
    ])
    idx = aggregate.index_hours(times, "America/Los_Angeles")
    assert idx.ski_date == [date(2026, 1, 14), date(2026, 1, 15), date(2026, 1, 15),
                            date(2026, 1, 15), date(2026, 1, 15)]
    assert list(idx.is_night) == [False, True, True, False, False]


def test_night_and_day_totals_for_a_full_ski_day():
    times = _t("2026-01-14T00") + np.arange(72).astype("timedelta64[h]")
    idx = aggregate.index_hours(times, "America/Los_Angeles")
    night, day, cal = aggregate.day_masks(idx, date(2026, 1, 15))
    assert night.sum() == 16 and day.sum() == 8 and cal.sum() == 24
    snow = np.ones(72)
    assert aggregate.window_sum(snow, night) == 16.0
    assert aggregate.window_sum(snow, day) == 8.0


def test_tokyo_is_handled_in_local_time():
    times = _t("2026-01-14T00") + np.arange(72).astype("timedelta64[h]")
    idx = aggregate.index_hours(times, "Asia/Tokyo")
    night, day, _ = aggregate.day_masks(idx, date(2026, 1, 15))
    # night starts 16:00 JST Jan 14 = 07:00 UTC -> first stamp 08:00 UTC
    assert times[night][0] == _t("2026-01-14T08")
    assert night.sum() == 16 and day.sum() == 8


def test_window_sum_requires_coverage():
    v = np.array([1.0, 1.0, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan])
    mask = np.ones(8, dtype=bool)
    assert np.isnan(aggregate.window_sum(v, mask))            # 25 % coverage: unknown, not "2 cm"
    v[2:7] = 1.0
    assert aggregate.window_sum(v, mask) == pytest.approx(7.0)
    assert np.isnan(aggregate.window_sum(v, np.zeros(8, dtype=bool)))
