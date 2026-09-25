"""Pure logic: rules, cold-chain, risk, SAR grid, geo, datasets."""
import csv
import math
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.config import settings
from app.services import coldchain, geo, risk, rules, sar


def item(**k):
    d = dict(id="X-1", consignment="C", name="Thing", weight_kg=10, category="", hazard=False, route="air", current_node="Cape Town hub")
    d.update(k)
    return SimpleNamespace(**d)


# ---------------------------------------------------------------- cargo rules
def test_hazard_cannot_go_by_air():
    assert rules.check_item(item(hazard=True, category="battery", route="air"))["code"] == "NO_AIR"


def test_fuel_is_arranged_at_cape_town_when_shipped():
    assert rules.check_item(item(hazard=True, category="fuel", route="ship"))["code"] == "ARRANGE_CT"


def test_soil_needs_declaration_and_plain_item_is_ok():
    assert rules.check_item(item(category="soil"))["code"] == "DECLARATION"
    assert rules.check_item(item())["code"] == "OK"


def test_handoff_must_follow_route_order():
    with pytest.raises(rules.RuleViolation, match="Out of order"):
        rules.validate_handoff(item(), "Bharati", [item()])


def test_handoff_onto_air_leg_checks_hazard_and_weight():
    with pytest.raises(rules.RuleViolation, match="hazardous"):
        rules.validate_handoff(item(hazard=True, category="gas"), "Novo airfield (Maitri)", [])
    heavy = [item(id=f"H{i}", weight_kg=700) for i in range(3)]
    with pytest.raises(rules.RuleViolation, match="limit"):
        rules.validate_handoff(heavy[0], "Novo airfield (Maitri)", heavy)
    rules.validate_handoff(item(), "Novo airfield (Maitri)", [item()])      # fine


def test_air_limit_states():
    assert rules.check_consignment([item(weight_kg=1000)])["state"] == "ok"
    assert rules.check_consignment([item(weight_kg=1600)])["state"] == "warn"
    assert rules.check_consignment([item(weight_kg=1900)])["state"] == "over"


# ---------------------------------------------------------------- cold chain
def series(rate, n=48, start=-26.0, noise=0.0):
    t0 = datetime(2026, 11, 1, 0, 0)
    return [(t0 + timedelta(minutes=10 * i), start + rate * (i / 6) + (noise if i % 2 else -noise)) for i in range(n)]


def test_warming_sample_gets_eta():
    r = coldchain.analyze(series(0.8), -15.0)
    assert r["rate_c_per_h"] == pytest.approx(0.8, abs=0.05)
    expected = (-15.0 - r["current"]) / 0.8
    assert r["eta_h"] == pytest.approx(expected, abs=0.5)
    assert r["status"] in ("warning", "critical")


def test_stable_sample_is_ok_with_no_eta():
    r = coldchain.analyze(series(0.0, noise=0.1), -15.0)
    assert r["status"] == "ok" and r["eta_h"] is None


def test_spike_is_flagged_not_deleted_and_ignored_by_trend():
    data = series(0.0, noise=0.1)
    data[20] = (data[20][0], -12.0)
    r = coldchain.analyze(data, -15.0)
    assert r["outliers"] == 1
    assert len(r["series"]) == len(data)                       # raw kept
    assert next(s for s in r["series"] if s["outlier"])["raw"] == -12.0
    assert r["status"] == "ok"                                 # the spike alone must not raise a breach warning


def test_already_breached():
    assert coldchain.analyze(series(0.0, start=-10.0), -15.0)["status"] == "breached"


def test_too_little_data():
    assert coldchain.analyze(series(0.5, n=2), -15.0)["status"] == "nodata"


# ---------------------------------------------------------------- risk
def test_weights_sum_to_one():
    assert sum(risk.WEIGHTS.values()) == pytest.approx(1.0)


def test_score_extremes_and_bands():
    lo = risk.compute(0, 0, 20, 0, 0)
    hi = risk.compute(100, 60, 0, 900, 100)
    assert lo["score"] == 0 and lo["band"] == "LOW"
    assert hi["score"] == pytest.approx(1.0) and hi["band"] == "HIGH"


def test_score_is_monotonic_in_each_input():
    base = risk.compute(50, 20, 8, 200, 10)["score"]
    assert risk.compute(70, 20, 8, 200, 10)["score"] > base
    assert risk.compute(50, 35, 8, 200, 10)["score"] > base
    assert risk.compute(50, 20, 2, 200, 10)["score"] > base
    assert risk.compute(50, 20, 8, 400, 10)["score"] > base
    assert risk.compute(50, 20, 8, 200, 60)["score"] > base


def test_why_names_the_biggest_part_and_stale_data_warns():
    r = risk.compute(95, 5, 15, 10, 60)
    assert "Sea ice" in r["why"] and "old" in r["why"]


# ---------------------------------------------------------------- SAR grid
def test_grid_probabilities_sum_to_one_and_peak_near_center():
    g = sar.search_grid(-71.0, 74.8, 95, 24, 215)
    assert len(g["cells"]) == sar.ROWS * sar.COLS
    assert sum(c["p"] for c in g["cells"]) == pytest.approx(1.0, abs=0.01)
    best = max(g["cells"], key=lambda c: c["p"])
    assert best["row"] in (1, 2) and best["col"] in (2, 3)


def test_grid_shifts_downwind():
    east_wind = sar.search_grid(-71.0, 74.8, 90, 30, 200)       # wind FROM the east blows toward the west
    assert east_wind["center"][1] < 74.8
    assert sar.search_grid(-71.0, 74.8, 90, 0, 200)["shift_km"] == 0


def test_stronger_wind_or_longer_silence_widens_or_shifts_more():
    assert sar.search_grid(-71, 74, 90, 40, 200)["shift_km"] > sar.search_grid(-71, 74, 90, 10, 200)["shift_km"]
    assert sar.search_grid(-71, 74, 90, 20, 400)["sigma_km"] > sar.search_grid(-71, 74, 90, 20, 100)["sigma_km"]


# ---------------------------------------------------------------- geo
def test_haversine_known_distance():
    assert geo.haversine_km(0, 0, 0, 1) == pytest.approx(111.19, abs=0.3)


def test_land_and_sea_classification_and_ice_gradient():
    assert geo.is_ocean(-60.0, 50.0)                            # open Southern Ocean
    assert not geo.is_ocean(-75.0, 60.0)                        # inland
    assert geo.sea_ice(-75.0, 60.0) is None
    near, far = geo.sea_ice(-68.6, 74.0), geo.sea_ice(-60.0, 52.0)
    assert near is not None and far is not None and near > far


def test_route_sampling_endpoints():
    pts = geo.sample_route([[-60, 50], [-65, 60]], 5)
    assert pts[0] == (-60, 50) and pts[-1] == pytest.approx((-65, 60))


# ---------------------------------------------------------------- datasets
def rows(name):
    with open(settings.data_dir / name, newline="") as f:
        return list(csv.DictReader(f))


def test_dataset_sizes_match_the_story():
    assert len(rows("personnel.csv")) == 37
    assert len(rows("assets.csv")) == 126
    assert sum(r["status"] == "in_transit" for r in rows("cargo.csv")) == 18


def test_no_hazardous_cargo_is_planned_by_air():
    assert not [r for r in rows("cargo.csv") if r["hazard"] == "1" and r["route"] == "air"]


def test_air_cargo_per_consignment_within_limit():
    tot = {}
    for r in rows("cargo.csv"):
        if r["route"] == "air":
            tot[r["consignment"]] = tot.get(r["consignment"], 0) + float(r["weight_kg"])
    assert max(tot.values()) <= rules.rules()["air_limit_kg"]["min"]


def test_ids_are_unique():
    for f in ("personnel.csv", "assets.csv", "cargo.csv", "inventory.csv"):
        ids = [r["id"] for r in rows(f)]
        assert len(ids) == len(set(ids)), f
