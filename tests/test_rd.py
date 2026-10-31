"""The regression discontinuity must recover a known jump, and both implementations must agree."""
import pathlib, sys
import numpy as np
import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "analysis"), str(ROOT)]
pytest.importorskip("statsmodels")
import method_change_rd as R
import verify_rd as V

CUT = pd.Timestamp("2025-06-15")


def synthetic(jump=2.0, n=20000, seed=1, rush=0.0):
    g = np.random.default_rng(seed)
    d = pd.DataFrame({"date": CUT + pd.to_timedelta(g.integers(-180, 180, n), unit="D")})
    t = (d.date - CUT).dt.days / 30.0
    for k, levels in [("pt", list("FH")), ("bf", list("ST")), ("ag", list("abc")), ("fg", list("xy"))]:
        d[k] = g.choice(levels, n)
    d["post"] = (t >= 0).astype(int)
    d["t"] = t
    d["sap"] = 60 + 0.1 * t + jump * d.post + 3 * (d.pt == "H") - 2 * (d.ag == "a") + g.normal(0, 5, n)
    in_rush = (d.date >= CUT - pd.Timedelta(days=14)) & (d.date < CUT)
    d.loc[in_rush, "sap"] += rush
    d["cb"] = (d.sap >= 69).astype(float)
    d["c_or_better"] = d.cb
    return d


@pytest.mark.parametrize("truth", [0.0, 2.0, -1.5])
def test_independent_fit_recovers_a_known_jump(truth):
    r = V.estimate(synthetic(truth), str(CUT.date()), bw=180)
    assert r["hc_lo"] < truth < r["hc_hi"]
    assert abs(r["jump"] - truth) < 0.4


def test_donut_removes_a_rush_that_would_bias_the_estimate():
    d = synthetic(0.0, rush=8.0)
    assert abs(V.estimate(d, str(CUT.date()), donut=14, bw=60)["jump"]) < 0.6
    assert V.estimate(d, str(CUT.date()), donut=0, bw=60)["jump"] < -1


def test_both_implementations_give_the_same_estimate_and_interval():
    d = synthetic(1.0)
    w = R.window(d.drop(columns=["t", "post"]), CUT, 90, 14)
    a = R.jump(w, "sap", 1)
    b = V.estimate(d, str(CUT.date()), donut=14, bw=90)
    assert a["n"] == b["n"]
    assert a["jump"] == pytest.approx(b["jump"], abs=1e-8)
    assert a["ci_low"] == pytest.approx(b["hc_lo"], abs=1e-3)


def test_window_excludes_the_donut_and_includes_the_cutoff_day():
    d = pd.DataFrame({"date": [CUT - pd.Timedelta(days=x) for x in (15, 14, 1, 0)]})
    assert list(R.window(d, CUT, 90, 14).date) == [CUT - pd.Timedelta(days=15), CUT]


def test_placebo_with_no_jump_is_not_significant_on_average():
    hits = sum(not (r["hc_lo"] < 0 < r["hc_hi"]) for r in (V.estimate(synthetic(0.0, 6000, s), str(CUT.date())) for s in range(20)))
    assert hits <= 4


def test_age_band_groups_match_their_labels():
    import method_change as M
    src = pathlib.Path(M.__file__).read_text(encoding="utf8")
    bands = {"England and Wales: 1900-1929": "before 1930", "England and Wales: 1930-1949": "1930-1949", "England and Wales: before 1900": "before 1930"}
    yr = pd.to_numeric(pd.Series(list(bands)).str.extract(r"(\d{4})")[0])
    got = pd.cut(yr, [0, 1929, 1949], labels=["before 1930", "1930-1949"]).astype(str).tolist()
    assert got == list(bands.values())
    assert "[0, 1929, 1949, 1975" in src, "method_change.py groups 1900-1929 under a label that says before 1919"
