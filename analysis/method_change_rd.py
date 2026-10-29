"""Did RdSAP 10 (15 June 2025) move EPC ratings? Regression discontinuity in lodgement date, with placebo cut-offs.

    python method_change_rd.py --area london|belfast [--cutoff 2025-06-15] [--placebo 2024-06-15 2023-06-15]

Why: method_change.py compares repeat certificates that span the cut-off with earlier repeat pairs, but its estimate is
about the same at placebo cut-offs, so it measures the secular drift
of re-assessments, not the change of method. The cut-off is sharp in England and Wales: after 15 June 2025 certificates
could only be lodged with RdSAP 10 (no transition period for EPCs), so certificates lodged just before and just after
it differ in method but not, on average, in the dwellings assessed.
Estimate: SAP of RdSAP certificates (REPORT_TYPE 2) regressed on post, months from the cut-off and their interaction
(separate linear trends each side), with fixed effects for property type, built form, age band and fuel group; the
coefficient of post is the jump at the cut-off. Robust (HC1) 95% intervals. Outcomes: SAP and the share rated C or better.
Lodgements bunched in the last days before the cut-off (assessors clearing RdSAP 9.94 jobs; MHCLG statistics for
April-June 2025), and the bunched certificates differ in dwelling mix, so the main estimate is a donut design that
leaves out the --donut days before the cut-off (default 14). Variants: bandwidths 30-180 days, linear or quadratic
trends, donut 0 or 14; subgroups by age band, property type and fuel group; balance tests (does the dwelling mix jump?);
weekly lodgement counts; the same at placebo cut-offs, where no jump is expected.
Northern Ireland: the date RdSAP 10 took effect there is not confirmed; the Belfast estimate at 15 June 2025 is a test,
not an assumption.
Outputs in data/<area>/analysis/: method_change_rd.csv (estimates), method_change_rd_balance.csv,
method_change_rd_weekly.csv
"""
import argparse, pathlib, sys
import pandas as pd
import statsmodels.formula.api as smf
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import method_change as M
from safeio import keep                      # existing outputs are archived, never overwritten

TREND = {1: "post + t + post:t", 2: "post + t + post:t + I(t**2) + post:I(t**2)"}
FE = " + C(pt) + C(bf) + C(ag) + C(fg)"
COLS = ["sap", "c_or_better", "t", "post", "pt", "bf", "ag", "fg"]
GROUPS = {"age_group": "ag", "property_type": "pt", "fuel_group": "fg"}


def prepare(e):
    for k, s in [("pt", "PROPERTY_TYPE"), ("bf", "BUILT_FORM"), ("ag", "age_group"), ("fg", "fuel_group")]:
        e[k] = e[s].astype(object).astype(str)
    e["c_or_better"] = e["CURRENT_ENERGY_RATING"].astype(str).isin(list("ABC")).astype(float)
    return e


def window(e, c, bw, donut):
    d = e[(e.date >= c - pd.Timedelta(days=bw)) & (e.date < c + pd.Timedelta(days=bw))]
    d = d[(d.date < c - pd.Timedelta(days=donut)) | (d.date >= c)].copy()
    d["t"] = (d.date - c).dt.days / 30.0
    d["post"] = (d.t >= 0).astype(int)
    return d


def jump(d, outcome, poly, min_n=3000):
    if len(d) < min_n:
        return None
    f = smf.ols(f"{outcome} ~ {TREND[poly]}{FE}", d[COLS]).fit(cov_type="HC1")
    lo, hi = f.conf_int().loc["post"]
    return {"n": len(d), "jump": f.params["post"], "ci_low": lo, "ci_high": hi}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--cutoff", default="2025-06-15")
    ap.add_argument("--placebo", nargs="*", default=["2024-06-15", "2023-06-15"])
    ap.add_argument("--donut", type=int, default=14)
    a = ap.parse_args()
    e = prepare(M.load(a.area))
    rows, bal, weeks = [], [], []
    for cut, kind in [(a.cutoff, "method")] + [(p, "placebo") for p in a.placebo]:
        c = pd.Timestamp(cut)
        tag = {"cutoff": cut, "kind": kind}
        for bw in (30, 60, 90, 180):
            for donut in sorted({0, a.donut}):
                for poly in (1, 2):
                    d = window(e, c, bw, donut)
                    for y in ("sap", "c_or_better"):
                        r = jump(d, y, poly, min_n=1000)
                        if r:
                            rows.append({**tag, "bandwidth_days": bw, "donut_days": donut, "trend": poly, "outcome": y,
                                         "group": "all", "value": "all", **r})
        d = window(e, c, 180, a.donut)
        for col, k in GROUPS.items():
            for v, x in d.groupby(k):
                for y in ("sap", "c_or_better"):
                    r = jump(x, y, 1)
                    if r:
                        rows.append({**tag, "bandwidth_days": 180, "donut_days": a.donut, "trend": 1, "outcome": y,
                                     "group": col, "value": v, **r})
        for donut in sorted({0, a.donut}):
            d = window(e, c, 90, donut)
            for k in ("pt", "ag", "fg"):
                for v in d[k].value_counts().index[:5]:
                    d["y"] = (d[k] == v).astype(float)
                    f = smf.ols(f"y ~ {TREND[1]}", d[["y", "t", "post"]]).fit(cov_type="HC1")
                    lo, hi = f.conf_int().loc["post"]
                    bal.append({**tag, "donut_days": donut, "variable": k, "value": v, "jump_share": f.params["post"],
                                "ci_low": lo, "ci_high": hi})
        w = e[(e.date >= c - pd.Timedelta(days=56)) & (e.date < c + pd.Timedelta(days=56))]
        for wk, n in w.groupby((w.date - c).dt.days // 7).size().items():
            weeks.append({**tag, "week_from_cutoff": wk, "lodgements": n})
    d = DATA / a.area / "analysis"
    out = pd.DataFrame(rows)
    out.round(4).to_csv(keep(d / "method_change_rd.csv"), index=False)
    pd.DataFrame(bal).round(4).to_csv(keep(d / "method_change_rd_balance.csv"), index=False)
    pd.DataFrame(weeks).to_csv(keep(d / "method_change_rd_weekly.csv"), index=False)
    main_ = out[(out.group == "all") & (out.bandwidth_days == 90) & (out.trend == 1)]
    print(main_.round(3).to_string(index=False))


DATA = M.DATA

if __name__ == "__main__":
    main()
