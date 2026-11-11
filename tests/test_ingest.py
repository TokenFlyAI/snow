import httpx
import numpy as np
import pytest

from pipeline.config import MODEL_BY_ID
from pipeline.ingest import open_meteo as om
from tests.helpers import make_resort


def _payload(n=4, elevation=2100.0):
    return {"elevation": elevation, "hourly": {
        "time": [f"2026-01-10T0{i}:00" for i in range(n)],
        "precipitation": [0.0, 1.5, None, 2.0], "temperature_2m": [-1.0, -2.0, -3.0, None]}}


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_parse_location_maps_null_to_nan():
    md = om.parse_location(_payload(), "gfs_global", "x")
    assert md.grid_elevation == 2100.0
    assert md.time[1] == np.datetime64("2026-01-10T01", "h")
    assert np.isnan(md.get("precipitation")[2]) and md.get("precipitation")[1] == 1.5
    assert np.isnan(md.get("not_requested")).all()
    assert md.has_data


def test_fetch_model_sends_one_request_with_all_coordinates():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=[_payload(), _payload(elevation=1500.0)])

    resorts = [make_resort(), make_resort(id="other", lat=40.0, lon=-111.0)]
    usage = {}
    out = om.fetch_model(_client(handler), MODEL_BY_ID["gfs_global"], resorts, usage=usage)
    assert seen["latitude"] == "39.2000,40.0000" and seen["elevation"] == "nan,nan"
    assert seen["models"] == "gfs_global" and "temperature_700hPa" in seen["hourly"]
    assert out["other"].grid_elevation == 1500.0
    assert usage["requests"] == 1 and usage["weighted_calls"] > 2


def test_single_location_response_is_a_dict():
    out = om.fetch_model(_client(lambda r: httpx.Response(200, json=_payload())),
                         MODEL_BY_ID["gfs_global"], [make_resort()])
    assert list(out) == ["test-mountain"]


def test_api_error_is_raised_without_retry():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(400, json={"error": True, "reason": "No data is available for this location"})

    with pytest.raises(om.OpenMeteoError, match="No data"):
        om.fetch_model(_client(handler), MODEL_BY_ID["gfs_global"], [make_resort()])
    assert len(calls) == 1


def test_rate_limit_is_retried(monkeypatch):
    monkeypatch.setattr(om.time, "sleep", lambda s: None)
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429) if len(calls) < 3 else httpx.Response(200, json=_payload())

    out = om.fetch_model(_client(handler), MODEL_BY_ID["gfs_global"], [make_resort()])
    assert len(calls) == 3 and "test-mountain" in out


def test_call_weight_matches_free_tier_rules():
    assert om.call_weight(10, 14, 1) == 1.0
    assert om.call_weight(15, 14, 1) == pytest.approx(1.5)
    assert om.call_weight(10, 28, 1) == pytest.approx(2.0)
    assert om.call_weight(20, 14, 5) == pytest.approx(10.0)
