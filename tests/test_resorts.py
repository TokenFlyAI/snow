import pytest
from pydantic import ValidationError

from pipeline.config import MODELS, models_for
from pipeline.resorts import ResortDB, load_resorts
from tests.helpers import make_resort


def test_shipped_database_is_valid():
    db = load_resorts()
    assert len(db.resorts) >= 10
    for r in db.resorts:
        assert r.passes, f"{r.id} has no pass"
        assert r.sources, f"{r.id} lists no source for its coordinates/elevations"


def test_elevations_must_be_ordered():
    with pytest.raises(ValidationError):
        make_resort(elevation_m={"base": 2500, "mid": 2300, "summit": 2750})


def test_bad_id_timezone_and_snotel_are_rejected():
    for bad in ({"id": "Bad Id"}, {"timezone": "Mars/Olympus"}, {"snotel": "784-CA"}):
        with pytest.raises(ValidationError):
            make_resort(**bad)


def test_duplicate_ids_and_unknown_regions_are_rejected():
    region = {"id": "tahoe", "name": "Tahoe", "name_zh": "太浩湖"}
    r = make_resort().model_dump()
    with pytest.raises(ValidationError):
        ResortDB(regions=[region], resorts=[r, r])
    with pytest.raises(ValidationError):
        ResortDB(regions=[], resorts=[r])


def test_model_selection_by_region():
    us = {m.id for m in models_for(make_resort())}
    jp = {m.id for m in models_for(make_resort(country="JP", state="Hokkaido", timezone="Asia/Tokyo"))}
    ca = {m.id for m in models_for(make_resort(country="CA", state="BC"))}
    ak = {m.id for m in models_for(make_resort(state="AK"))}
    assert {"ncep_nbm_conus", "ncep_hrrr_conus", "ecmwf_ifs025"} <= us
    assert "jma_seamless" in jp and "ncep_nbm_conus" not in jp
    assert "gem_hrdps_continental" in ca and "ncep_hrrr_conus" not in ca
    assert "ncep_hrrr_conus" not in ak and "gfs_global" in ak
    assert len({m.id for m in MODELS}) == len(MODELS)
