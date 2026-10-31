"""Invariants of the HEM inputs and weather files. Tests needing local campaign data skip when it is absent."""
import csv, glob, json, pathlib, sys
import numpy as np
import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hem"))
import hem_geometry as hg
from make_archetypes import FORMS, RSI_RSE, Y, HDD_LONDON, r_construction

HT = ROOT.parent / "data/hem_trial"
C = HT / "campaign_fullyear_2026-10-30"
BENCH = HT / "benchmark_local_fullyear_2026-10-30"
SETTINGS = ("london", "belfast", "londonwindbel", "belfastwindlon")
need = pytest.mark.skipif(not C.exists(), reason="campaign data not on this machine")


def hem(form, setting="london", v=0):
    return json.load(open(C / f"{form}_{setting}/variant_{v:03d}.json"))


def test_surface_accounting_on_a_small_case():
    d = {"Zone": {"z": {"BuildingElement": {
        "wall": {"type": "BuildingElementOpaque", "area": 10}, "win": {"type": "BuildingElementTransparent", "height": 2, "width": 2},
        "party wall": {"type": "BuildingElementAdjacentConditionedSpace", "area": 7},
        "internal wall": {"type": "BuildingElementAdjacentConditionedSpace", "area": 100},
        "entrence door": {"type": "BuildingElementAdjacentConditionedSpace", "area": 2}}}}}
    assert hg.envelope_area(d) == 23     # the partition must not count: the 2026-10-31 error


def test_construction_resistance_inverts_to_u():
    for u, pitch in ((2.1, 90), (0.45, 90), (0.16, 0)):
        assert 1 / (r_construction(u, pitch) + RSI_RSE[pitch]) == pytest.approx(u)


@need
@pytest.mark.parametrize("form", FORMS)
def test_envelope_does_not_depend_on_form(form):
    # re-typing a surface from party to exposed cannot change the dwelling's total envelope
    assert hg.envelope_area(hem(form)) == pytest.approx(hg.envelope_area(hem("flat_mid")), abs=0.01)


@need
def test_envelope_value_and_input_mismatch():
    assert hg.envelope_area(hem("flat_mid")) == pytest.approx(124.6, abs=0.1)
    assert hem("flat_mid")["InfiltrationVentilation"]["Leaks"]["env_area"] == 220     # known limitation of the base


@pytest.mark.skipif(not BENCH.exists(), reason="benchmark not on this machine")
def test_exposed_area_matches_hem_own_form_factor():
    # independent check: the engine reports heat-loss form factor = exposed area / floor area
    files = glob.glob(str(BENCH / "b*.json"))
    assert files
    for j in files:
        d = json.load(open(j))
        r = next(iter(glob.glob(j[:-5] + "__results/*results_static.csv")))
        row = next(x for x in csv.reader(open(r)) if x and x[0] == "Heat loss form factor")
        assert hg.surface_areas(d)["exposed"] == pytest.approx(float(row[2]) * hg.floor_area(d), rel=1e-3), j


@need
def test_design_counts():
    n = {f: len(pd.read_csv(C / f"{f}_london/variants.csv")) for f in FORMS}
    assert n == dict(flat_mid=27, flat_ground=54, flat_top=81, bungalow_terrace=162, bungalow_semi=162, bungalow_detached=162)
    assert sum(len(glob.glob(str(C / f"{f}_{s}/variant_*.json"))) for f in FORMS for s in SETTINGS) == 2592


@need
@pytest.mark.parametrize("form", FORMS)
def test_inputs_cover_a_full_year_at_half_hours(form):
    assert hem(form)["SimulationTime"] == {"start": 0, "end": 8760, "step": 0.5}   # the January-June error


@need
@pytest.mark.parametrize("form", FORMS)
def test_settings_differ_only_in_nothing_but_weather(form):
    assert hem(form, "london", 3) == hem(form, "belfast", 3) == hem(form, "londonwindbel", 3)


@need
@pytest.mark.parametrize("form", FORMS)
def test_indicator_recomputed_from_the_input(form):
    v = pd.read_csv(C / f"{form}_london/variants.csv")
    for i in (0, len(v) // 2, len(v) - 1):
        d = hem(form, v=i); r = v.iloc[i]; ua = env = 0.0
        for z in d["Zone"].values():
            for e in z["BuildingElement"].values():
                a = e.get("area") or e.get("height", 0) * e.get("width", 0)
                if e["type"] == "BuildingElementGround":
                    ua += e["u_value"] * a; env += a
                elif "Adjacent" not in e["type"]:
                    ua += a / (e["thermal_resistance_construction"] + RSI_RSE[e["pitch"] if e["type"] != "BuildingElementTransparent" else 90]); env += a
        vol = hg.volume(d); n = r.air_permeability * 220 / vol / 20
        hlc = ua + Y * env + 0.33 * n * vol
        assert hlc == pytest.approx(r.hlc_proxy, abs=0.3)
        assert hlc * HDD_LONDON * 24 / 1000 / hg.floor_area(d) == pytest.approx(r.q_proxy_kwh_m2, abs=0.5)


def epw(name):
    return pd.read_csv(next((C / "weather").glob(name)), skiprows=8, header=None)


@need
def test_wind_swap_changes_only_wind():
    lon, bel, lb = epw("GBR_ENG*"), epw("GBR_NIR*"), epw("london_with*")
    other = [c for c in lon.columns if c not in (20, 21)]
    pd.testing.assert_frame_equal(lon[other], lb[other])
    assert np.allclose(lb[[20, 21]].values, bel[[20, 21]].values)
    assert len(lon) == 8760


@need
def test_degree_days_by_hand_formula():
    e = epw("GBR_ENG*"); d = e[6].groupby(np.arange(8760) // 24).mean()
    assert sum(max(0, 15.5 - x) for x in d) == pytest.approx(1599, abs=1)
