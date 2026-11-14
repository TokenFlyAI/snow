from datetime import date, datetime, timezone

import httpx
import numpy as np
import pytest

from pipeline.config import ENSEMBLE_BY_ID
from pipeline.ingest import open_meteo_ensemble as ome
from pipeline.process import ensemble as ens
from tests.helpers import make_resort

NOW = datetime(2026, 1, 10, 6, 0, tzinfo=timezone.utc)


# ----------------------------------------------------------------------------- percentiles
def test_percentiles_of_an_even_sample():
    v = np.arange(0.0, 101.0)                      # 0, 1, ... 100 cm
    p10, p50, p90 = ens.weighted_quantiles(v, np.ones(v.size), (0.1, 0.5, 0.9))
    assert p50 == pytest.approx(50.0, abs=0.01)
    assert p10 == pytest.approx(9.6, abs=0.2) and p90 == pytest.approx(90.4, abs=0.2)
    assert p10 < p50 < p90


def test_percentiles_ignore_missing_members_and_respect_weights():
    nan = float("nan")
    assert ens.weighted_quantiles([nan, 4.0, nan], [1, 1, 1], (0.1, 0.5, 0.9)) == [4.0, 4.0, 4.0]
    assert all(np.isnan(x) for x in ens.weighted_quantiles([nan, nan], [1, 1], (0.1, 0.9)))
    assert all(np.isnan(x) for x in ens.weighted_quantiles([], [], (0.5,)))
    # two models: the heavily weighted one pulls the median to its side
    light = ens.weighted_quantiles([0.0, 0.0, 30.0, 30.0], [1, 1, 1, 1], (0.5,))[0]
    heavy = ens.weighted_quantiles([0.0, 0.0, 30.0, 30.0], [1, 1, 9, 9], (0.5,))[0]
    assert light == pytest.approx(15.0) and heavy > 25.0
    # zero-weight members are ignored
    assert ens.weighted_quantiles([1.0, 99.0], [1.0, 0.0], (0.5,)) == [1.0]


def test_percentiles_are_monotonic_for_a_skewed_snow_distribution():
    rng = np.random.default_rng(7)
    v = np.where(rng.random(200) < 0.6, 0.0, rng.gamma(2.0, 8.0, 200))   # mostly dry, a few big totals
    qs = ens.weighted_quantiles(v, np.ones(200), (0.1, 0.25, 0.5, 0.75, 0.9))
    assert qs == sorted(qs) and qs[0] == 0.0 and qs[-1] > 5.0


# ----------------------------------------------------------------------------- probabilities
def test_probability_of_at_least_a_threshold():
    v = [0.0, 1.0, 2.5, 3.0, 15.0, 20.0, 0.0, 0.0, 16.0, 2.4]
    w = np.ones(10)
    assert ens.prob_at_least(v, w, 2.5) == pytest.approx(0.5)     # the threshold itself counts
    assert ens.prob_at_least(v, w, 15.0) == pytest.approx(0.3)
    assert ens.prob_at_least(v, w, 100.0) == 0.0
    assert ens.prob_at_least(v, w, 0.0) == 1.0


def test_probability_skips_missing_members_and_uses_weights():
    nan = float("nan")
    assert ens.prob_at_least([nan, 10.0, 0.0, nan], [1, 1, 1, 1], 2.5) == pytest.approx(0.5)
    assert np.isnan(ens.prob_at_least([nan, nan], [1, 1], 2.5))
    # ECMWF (weight 2 spread over 2 members) says snow, GEFS (weight 1 over 4 members) says dry
    v = [20.0, 20.0, 0.0, 0.0, 0.0, 0.0]
    w = [1.0, 1.0, 0.25, 0.25, 0.25, 0.25]
    assert ens.prob_at_least(v, w, 15.0) == pytest.approx(2.0 / 3.0)


def test_stats_bundle_and_minimum_member_count():
    st = ens.stats(np.linspace(0, 30, 31), np.ones(31), ens.DAY_THRESHOLDS_CM)
    assert st.ok and st.n_members == 31
    assert st.p10 < st.p50 < st.p90 and st.mean == pytest.approx(15.0)
    assert st.prob[2.5] > st.prob[15.0] > 0
    few = ens.stats([1.0, 2.0, 3.0], [1, 1, 1], ens.DAY_THRESHOLDS_CM)
    assert not few.ok                                   # 3 members are not a distribution


# ----------------------------------------------------------------------------- ski-day totals per member
def _hours(start: str, n: int) -> np.ndarray:
    return np.datetime64(start, "h") + np.arange(n).astype("timedelta64[h]")


def test_member_day_totals_follow_the_ski_day():
    # 4 days of hourly data starting 00:00 UTC = 16:00 PST the day before
    t = _hours("2026-01-10T01", 96)                     # stamps are the END of each hour
    members = np.vstack([np.full(96, 0.5), np.full(96, 1.0), np.full(96, np.nan)])
    dates = [date(2026, 1, 10) + (date(2026, 1, 11) - date(2026, 1, 10)) * k for k in range(5)]
    tot = ens.member_day_totals(t, members, "America/Los_Angeles", dates)
    assert tot.shape == (3, 5)
    assert tot[0, :4] == pytest.approx([12.0] * 4)      # 24 h x 0.5 cm: ski day = 16:00 -> 16:00 local
    assert tot[1, :4] == pytest.approx([24.0] * 4)
    assert np.isnan(tot[2]).all()                        # a member without data stays missing
    assert np.isnan(tot[:, 4]).all()                     # nothing fetched for the fifth day


def test_member_day_totals_need_most_of_the_day():
    # Europe: the ski day of "today" began at 15:00 UTC yesterday, before the data starts
    t = _hours("2026-01-10T01", 72)
    tot = ens.member_day_totals(t, np.full((1, 72), 1.0), "Europe/Zurich", [date(2026, 1, 10), date(2026, 1, 11)])
    assert np.isnan(tot[0, 0])                           # only 15 of 24 hours -> not published
    assert tot[0, 1] == pytest.approx(24.0)


def test_raw_document_round_trips_through_the_pool():
    t = _hours("2026-01-10T01", 24 * 6)
    data = {"gfs05": (t, np.vstack([np.full(t.size, 0.1 * (i + 1)) for i in range(10)])),
            "ecmwf_ifs025": (t[:72], np.full((4, 72), 1.0))}
    raw = ens.raw_document("x", 2300, date(2026, 1, 10), 35, "America/Los_Angeles", data, NOW)
    assert raw["start_date"] == "2026-01-10" and raw["models"]["gfs05"]["members"] == 10
    assert raw["models"]["gfs05"]["daily"][0][0] == pytest.approx(2.4)
    assert len(raw["models"]["ecmwf_ifs025"]["daily"][0]) == 3        # trailing empty days are trimmed

    dates = [date(2026, 1, 10 + k) for k in range(8)]
    pool = ens.Pool.from_raw(raw, dates)
    assert pool.n_members == 14 and pool.values.shape == (14, 8)
    assert pool.models_on([0]) == ["gfs05", "ecmwf_ifs025"] and pool.models_on([4]) == ["gfs05"]
    # each model's weight is shared between its members: ECMWF 2.0 / 4, GEFS 1.0 / 10
    assert pool.weights[pool.model_of.index("ecmwf_ifs025")] == pytest.approx(0.5)
    assert pool.weights[0] == pytest.approx(0.1)
    # a later run shifts the calendar by a day: values move with their date
    later = ens.Pool.from_raw(raw, [date(2026, 1, 11 + k) for k in range(8)])
    assert later.values[0, 0] == pool.values[0, 1] and np.isnan(later.values[0, 6])
    assert ens.Pool.from_raw(None, dates).n_members == 0


# ----------------------------------------------------------------------------- windows and calibration
def test_window_totals_fill_gaps_and_require_coverage():
    nan = float("nan")
    values = np.array([[1.0] * 16,
                       [2.0] * 15 + [nan],          # ECMWF: 15 of 16 days -> scaled up, not dropped
                       [3.0] * 8 + [nan] * 8])      # ICON: half the window -> not used
    tot = ens.window_totals(values, range(16))
    assert tot[0] == pytest.approx(16.0) and tot[1] == pytest.approx(32.0) and np.isnan(tot[2])
    # day 0 is unknown to every member (ski day started before the run): use the blend's value for it
    v2 = np.array([[nan, 1.0, 1.0], [nan, 5.0, 5.0]])
    assert np.isnan(ens.window_totals(v2, range(3))).all()
    assert ens.window_totals(v2, range(3), fill={0: 4.0}) == pytest.approx([6.0, 14.0])


def test_calibration_rescales_to_the_blend():
    dates = [date(2026, 1, 10 + k) for k in range(12)]
    raw = {"start_date": "2026-01-10", "models": {"gfs05": {"weight": 1.0, "daily": [[7.0] * 12, [3.5] * 12, [0.0] * 12]}}}
    pool = ens.Pool.from_raw(raw, dates)
    slr = [14.0] * 10                                    # the blend says 14:1, Open-Meteo assumed 7:1
    blend = [14.0] * 10                                  # and twice the ensemble mean (7 cm after the SLR step)
    values, cal = ens.calibrate(pool, slr, blend)
    assert cal.factor == pytest.approx(2.0) and cal.n_days == 10 and cal.slr_default == pytest.approx(14.0)
    assert values[0, 0] == pytest.approx(7.0 * 2.0 * 2.0)            # SLR step x amount factor
    assert values[0, 11] == pytest.approx(28.0)                      # days past the blend use the mean SLR
    assert np.mean(values[:, 3]) == pytest.approx(14.0)              # ensemble mean now equals the blend


def test_calibration_factor_is_limited_and_skipped_for_dry_periods():
    dates = [date(2026, 1, 10 + k) for k in range(10)]
    pool = ens.Pool.from_raw({"start_date": "2026-01-10", "models": {"gfs05": {"daily": [[1.0] * 10, [1.0] * 10]}}}, dates)
    _, cal = ens.calibrate(pool, [7.0] * 10, [50.0] * 10)             # blend 50x the ensemble: capped
    assert cal.factor == ens.FACTOR_LIMITS[1]
    _, cal = ens.calibrate(pool, [7.0] * 10, [0.1] * 10)              # 1 cm in total: no information
    assert cal.factor == 1.0
    _, cal = ens.calibrate(ens.Pool.from_raw(None, dates), [7.0] * 10, [5.0] * 10)
    assert cal.factor == 1.0 and cal.n_days == 0


def test_level_ratio():
    assert ens.level_ratio(15.0, 10.0) == pytest.approx(1.5)
    assert ens.level_ratio(0.0, 10.0) == 0.0             # rain at the base
    assert ens.level_ratio(5.0, 0.2) == 1.0              # too little snow to tell
    assert ens.level_ratio(100.0, 10.0) == 2.5           # capped


# ----------------------------------------------------------------------------- ingest
def _payload(n_members=3, n=4):
    hourly = {"time": [f"2026-01-10T0{i}:00" for i in range(n)], "snowfall": [0.0, 0.7, None, 1.4]}
    for m in range(1, n_members):
        hourly[f"snowfall_member{m:02d}"] = [0.1 * m] * n
    return {"elevation": 2300.0, "hourly": hourly}


def test_parse_members_orders_control_first_and_maps_null_to_nan():
    ed = ome.parse_members(_payload(), "gfs05", "x")
    assert ed.members.shape == (3, 4) and ed.has_data
    assert ed.members[0, 1] == 0.7 and np.isnan(ed.members[0, 2])     # control run
    assert ed.members[2, 0] == pytest.approx(0.2)
    assert ed.time[0] == np.datetime64("2026-01-10T00", "h")
    assert not ome.parse_members({"hourly": {"time": []}}, "gfs05", "x").has_data


def test_fetch_ensemble_requests_mid_elevation_and_counts_members():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        seen["host"] = request.url.host
        return httpx.Response(200, json=[_payload(), _payload()])

    resorts = [make_resort(), make_resort(id="other", lat=40.0, lon=-111.0,
                                          elevation_m={"base": 2600, "mid": 2987, "summit": 3374})]
    usage = {}
    spec = ENSEMBLE_BY_ID["gfs05"]
    out = ome.fetch_ensemble(httpx.Client(transport=httpx.MockTransport(handler)), spec, resorts, usage=usage)
    assert seen["host"] == "ensemble-api.open-meteo.com"
    assert seen["hourly"] == "snowfall" and seen["models"] == "gfs05" and seen["forecast_days"] == "35"
    assert seen["elevation"] == "2300,2987"               # downscaled to mid-mountain, not the grid cell
    assert set(out) == {"test-mountain", "other"}
    # 31 members x 35 days: 3.1 x 2.5 = 7.75 weighted calls per location
    assert usage["weighted_calls"] == pytest.approx(15.5) and usage["by_kind"] == {"ensemble": pytest.approx(15.5)}
