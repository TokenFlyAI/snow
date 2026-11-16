"""data/pass_products.yaml is consistent with data/resorts.yaml (pipeline/passes.py)."""
import yaml

from pipeline.passes import PRODUCTS_FILE, access, blocked, load_products

RESORTS = {r["id"]: r for r in yaml.safe_load((PRODUCTS_FILE.parent / "resorts.yaml").read_text())["resorts"]}


def test_products_only_list_resorts_of_their_pass():
    products = load_products()
    assert {p["id"] for p in products} == {"ikon-base", "epic-local"}
    acc = access(products)                    # raises on a resort listed twice
    for p in products:
        for rid in acc[p["id"]]:
            assert rid in RESORTS, rid
            assert p["pass"] in RESORTS[rid]["passes"], f"{rid} is not on {p['pass']}"


def test_whole_destinations_are_listed():
    """A destination (Niseko United, Dolomiti Superski, ...) is either on a product or not, as a whole."""
    for p in load_products():
        listed = access([p])[p["id"]]
        dests = {RESORTS[r].get("destination") for r in listed} - {None}
        for rid, r in RESORTS.items():
            if r.get("destination") in dests and p["pass"] in r["passes"] and rid not in listed:
                # Aspen Snowmass is the one exception: Ikon Base is Snowmass only
                assert r["destination"] == "aspen-snowmass" and p["id"] == "ikon-base", rid


def test_blackouts():
    acc = access(load_products())
    assert blocked(acc["ikon-base"]["mammoth"], "2026-12-27")
    assert not blocked(acc["ikon-base"]["mammoth"], "2026-12-31")
    assert not blocked(acc["epic-local"]["breckenridge"], "2026-12-27")      # unlimited, no peak dates
    assert blocked(acc["epic-local"]["park-city"], "2026-11-27")
    assert blocked(acc["epic-local"]["verbier"], "2027-02-10")                # Verbier's own extra period
    assert not blocked(acc["epic-local"]["park-city"], "2027-02-10")
    assert acc["epic-local"]["vail"]["shared"] and acc["epic-local"]["vail"]["days"] == 10
    assert acc["epic-local"]["verbier"]["blackout"][-1] == ["2027-02-06", "2027-02-20"]     # Feb 13-14 merged in
    assert "jackson-hole" not in acc["ikon-base"] and "aspen-mountain" not in acc["ikon-base"]
