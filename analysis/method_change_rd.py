"""Did RdSAP 10 (15 June 2025) move EPC ratings? Regression discontinuity in lodgement date, with placebo cut-offs.

    python method_change_rd.py --area london|belfast [--cutoff 2025-06-15] [--placebo 2024-06-15 2023-06-15]

Why: method_change.py compares repeat certificates that span the cut-off with earlier repeat pairs, but its estimate is
about the same at placebo cut-offs, so it measures the secular drift
of re-assessments, not the change of method. The cut-off is sharp in England and Wales: after 15 June 2025 certificates
could only be lodged with RdSAP 10 (no transition period for EPCs), so certificates lodged just before and just after
it differ in method but not, on average, in the dwellings assessed.
Estimate: SAP of RdSAP certificates (REPORT_TYPE 2) regressed on post, months from the cut-off and their interaction
(separate linear trends each side), with fixed effects for property type, built form, age band and fuel group; the
coefficient of post is the jump at the cut-off. Robust (HC1) 95% intervals. Bandwidths 90 and 180 days; overall and by
age band, property type and fuel group; the same at placebo cut-offs, where no jump is expected.
Northern Ireland: the date RdSAP 10 took effect there is not confirmed; the Belfast estimate at 15 June 2025 is a test,
not an assumption.
Output: data/<area>/analysis/method_change_rd.csv
"""
import argparse, pathlib, sys
import pandas as pd
import statsmodels.formula.api as smf
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import method_change as M
from safeio import keep                      # existing outputs are archived, never overwritten

FORMULA = "sap ~ post + t + post:t + C(pt) + C(bf) + C(ag) + C(fg)"
GROUPS = {"age_group": "ag", "property_type": "pt", "fuel_group": "fg"}


def prepare(e):
    for k, s in [("pt", "PROPERTY_TYPE"), ("bf", "BUILT_FORM"), ("ag", "age_group"), ("fg", "fuel_group")]:
        e[k] = e[s].astype(object).astype(str)
    return e


def jump(d, cut, bw, group, value, kind, min_n=3000):
    if len(d) < min_n:
        return None
    f = smf.ols(FORMULA, d[["sap", "t", "post", "pt", "bf", "ag", "fg"]]).fit(cov_type="HC1")
    lo, hi = f.conf_int().loc["post"]
    return {"cutoff": cut, "kind": kind, "bandwidth_days": bw, "group": group, "value": value, "n": len(d),
            "jump_sap": f.params["post"], "ci_low": lo, "ci_high": hi}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--cutoff", default="2025-06-15")
    ap.add_argument("--placebo", nargs="*", default=["2024-06-15", "2023-06-15"])
    a = ap.parse_args()
    e = prepare(M.load(a.area))
    rows = []
    for cut, kind in [(a.cutoff, "method")] + [(p, "placebo") for p in a.placebo]:
        c = pd.Timestamp(cut)
        for bw in (90, 180):
            d = e[(e.date >= c - pd.Timedelta(days=bw)) & (e.date < c + pd.Timedelta(days=bw))].copy()
            d["t"] = (d.date - c).dt.days / 30.0
            d["post"] = (d.t >= 0).astype(int)
            rows.append(jump(d, cut, bw, "all", "all", kind, min_n=1000))
            if bw == 180:
                for col, k in GROUPS.items():
                    for v, x in d.groupby(k):
                        rows.append(jump(x, cut, bw, col, v, kind))
    out = pd.DataFrame([r for r in rows if r])
    out.round(3).to_csv(keep(DATA / a.area / "analysis" / "method_change_rd.csv"), index=False)
    print(out.round(2).to_string(index=False))


DATA = M.DATA

if __name__ == "__main__":
    main()
