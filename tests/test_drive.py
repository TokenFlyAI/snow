"""Drive-time table (scripts/build_drive_table.py), without the network."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_drive_table as b  # noqa: E402

DENVER, VAIL = (39.7392, -104.9903), (39.6061, -106.3550)
PASS = {"id": "p", "name": "Test Pass", "lat": 39.5, "lon": -105.6, "detours": ["town"]}
TOWN = (39.9, -105.7)


def test_minutes():
    assert b.minutes(0) == 10
    assert b.minutes(94) == 70
    assert b.minutes(94, trains=1) == 90


def test_distance_helpers():
    assert 110 < b.gc_km(DENVER, VAIL) < 125
    line = [(39.0, -105.6), (40.0, -105.6)]                        # north-south through the pass
    assert b.min_km(line, (39.5, -105.6)) < 0.01
    off = b.min_km(line, (39.5, -105.6 + 1.0 / 86))              # ~1 km east of the line
    assert 0.9 < off < 1.1
    assert b.min_km(line, (39.5, -105.0)) == math.inf             # far away: not within NEAR_KM


def test_closure_must_be_roughly_on_the_way():
    straight = b.gc_km(DENVER, VAIL)
    assert b.maybe_on_route([DENVER, VAIL], straight * 1.3, {"lat": 39.65, "lon": -105.7})
    assert not b.maybe_on_route([DENVER, VAIL], straight * 1.3, {"lat": 37.0, "lon": -105.7})


def test_closures_on_reports_near_misses():
    path = [DENVER, (39.6, -105.6), (39.4, -105.6), VAIL]           # north-south over the pass
    near = []
    assert b.closures_on(path, [DENVER, VAIL], 200, [PASS], near) == ["p"]
    shifted = {**PASS, "lon": -105.6 + 1.0 / 86}                      # 1 km off the road
    assert b.closures_on(path, [DENVER, VAIL], 200, [shifted], near) == []
    assert near and near[0][0] == "p"


class FakeOsrm:
    """table: road km by destination; route: by stop count (2: direct, 3: through the detour)."""

    def __init__(self, direct, detour, osrm_min=None):
        self.direct, self.detour, self.osrm_min, self.requests = direct, detour, osrm_min, 0

    def table(self, src, dests):
        km = self.direct["km"]
        return [(km, self.osrm_min if self.osrm_min is not None else b.minutes(km))] * len(dests)

    def route(self, stops):
        return self.direct if len(stops) == 2 else self.detour


def run(osrm):
    city = {"id": "denver", "lat": DENVER[0], "lon": DENVER[1]}
    resort = {"id": "vail", "lat": VAIL[0], "lon": VAIL[1]}
    return b.drive(osrm, city, [resort], [PASS], {"town": TOWN}, log=lambda *_: None)


def test_route_over_a_closed_pass_takes_the_detour():
    direct = {"km": 170, "path": [DENVER, (39.5, -105.6), VAIL], "ferry": False, "trains": 0}
    detour = {"km": 260, "path": [DENVER, TOWN, VAIL], "ferry": False, "trains": 0}
    got = run(FakeOsrm(direct, detour))
    assert got == {"vail": {"min": b.minutes(260), "km": 260, "via": ["p"]}}


def test_open_route_and_car_trains_and_ferries():
    open_road = {"km": 170, "path": [DENVER, (39.8, -105.9), VAIL], "ferry": False, "trains": 0}
    assert run(FakeOsrm(open_road, None)) == {"vail": {"min": b.minutes(170), "km": 170}}
    # a ferry makes OSRM's own time far longer than ours: the route is looked at and dropped
    boat = {**open_road, "ferry": True}
    assert run(FakeOsrm(boat, None, osrm_min=3 * b.minutes(170))) == {}
    train = {**open_road, "trains": 1}
    assert run(FakeOsrm(train, None, osrm_min=3 * b.minutes(170)))["vail"]["min"] == b.minutes(170) + b.TRAIN_MIN


def test_car_train_names():
    assert b.CAR_TRAIN.search("BLS Autoverlad Lötschberg")
    assert b.CAR_TRAIN.search("Autoverlad Vereina")
    assert not b.CAR_TRAIN.search("BC Ferries: Tsawwassen - Swartz Bay")
