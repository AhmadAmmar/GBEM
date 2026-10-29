"""How much did the change of assessment method (RdSAP 2012 / 9.94 to RdSAP 10, from 15 June 2025) shift EPC ratings?
Within-property comparison of repeated certificates.
Superseded as the estimate of the method effect by method_change_rd.py: this design gives similar shifts at placebo
cut-offs (secular drift of re-assessments), so its output is not the effect of the method.

    python method_change.py --area london|belfast [--cutoff 2025-06-15]

Why: models trained on certificates learn the rating of the method in force. RdSAP 10 replaced RdSAP 9.94 for existing
dwellings in England and Wales on 15 June 2025 (GOV.UK, Standard Assessment Procedure); Northern Ireland uses the same
methodology. The registers do not record the method version, so it is taken from the lodgement date.

Pairs: consecutive certificates of the same property (UPRN), both RdSAP (REPORT_TYPE 2), 30-730 days apart, with no
recorded change of main fuel, property type or built form and floor area within 10%. Each pair is "before" (both lodged
before the cut-off), "spanning" (first before, second on or after) or "after" (both on or after).
Estimate: the change in SAP between the two certificates, regressed on spanning and after (reference: before) and the
gap in years; the coefficient of spanning is the shift attributable to the change of method, net of the drift between
reassessments of the same unchanged dwelling. 95% intervals by bootstrap over properties (500 resamples). The same is
estimated by property type, main fuel and age band, and the band change of spanning pairs is tabulated.
Outputs in data/<area>/analysis/: method_change.csv (estimates), method_change_bands.csv (band transitions of
spanning pairs), method_change_monthly.csv (mean SAP of RdSAP certificates by lodgement month, raw and adjusted for
property type, built form, age band and fuel).
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"
BANDS = "ABCDEFG"


def load(area):
    cols = ["UPRN", "LODGEMENT_DATE", "REPORT_TYPE", "sap_score", "CURRENT_ENERGY_RATING", "MAIN_FUEL", "PROPERTY_TYPE",
            "BUILT_FORM", "TOTAL_FLOOR_AREA", "CONSTRUCTION_AGE_BAND", "MAINHEAT_DESCRIPTION"]
    e = pd.read_parquet(DATA / area / "epc/certificates_linked.parquet", columns=cols)
    e["date"] = pd.to_datetime(e["LODGEMENT_DATE"], errors="coerce").dt.tz_localize(None)
    e["sap"] = pd.to_numeric(e["sap_score"], errors="coerce")
    e["area_m2"] = pd.to_numeric(e["TOTAL_FLOOR_AREA"], errors="coerce")
    e = e[(e["REPORT_TYPE"].astype(str) == "2") & e["sap"].between(1, 150) & e["date"].notna() & e["UPRN"].notna()]
    e["uprn"] = e["UPRN"].astype(str)
    fuel = e["MAIN_FUEL"].astype(str).str.lower()
    e["fuel_group"] = np.select([fuel.str.contains("mains gas"), fuel.str.contains("electric"), fuel.str.contains("oil")],
                                ["mains gas", "electricity", "oil"], "other")
    age = e["CONSTRUCTION_AGE_BAND"].astype(str)
    yr = pd.to_numeric(age.str.extract(r"(\d{4})")[0], errors="coerce")
    e["age_group"] = pd.cut(yr, [0, 1918, 1949, 1975, 1990, 2002, 2100],
                            labels=["before 1919", "1919-1949", "1950-1975", "1976-1990", "1991-2002", "2003 on"]).astype(str)
    return e.sort_values(["uprn", "date"])


def pairs(e, cutoff, lo=30, hi=730):
    prev = e.groupby("uprn").shift()
    p = pd.DataFrame({"uprn": e["uprn"], "d0": prev["date"], "d1": e["date"], "sap0": prev["sap"], "sap1": e["sap"],
                      "band0": prev["CURRENT_ENERGY_RATING"], "band1": e["CURRENT_ENERGY_RATING"],
                      "property_type": e["PROPERTY_TYPE"], "fuel_group": e["fuel_group"], "age_group": e["age_group"]})
    same = (e["MAIN_FUEL"].eq(prev["MAIN_FUEL"]) & e["PROPERTY_TYPE"].eq(prev["PROPERTY_TYPE"]) & e["BUILT_FORM"].eq(prev["BUILT_FORM"])
            & ((e["area_m2"] / prev["area_m2"] - 1).abs() <= 0.10))
    p = p[same & prev["date"].notna()].copy()
    p["gap_days"] = (p["d1"] - p["d0"]).dt.days
    p = p[p["gap_days"].between(lo, hi)]
    c = pd.Timestamp(cutoff)
    p["kind"] = np.where(p["d1"] < c, "before", np.where(p["d0"] < c, "spanning", "after"))
    p["delta"] = p["sap1"] - p["sap0"]
    p["gap_years"] = p["gap_days"] / 365.25
    return p


def fit(p):
    """OLS of the SAP change on spanning, after and the gap: coefficient of spanning"""
    X = np.column_stack([np.ones(len(p)), (p["kind"] == "spanning").to_numpy(float), (p["kind"] == "after").to_numpy(float), p["gap_years"].to_numpy()])
    beta, *_ = np.linalg.lstsq(X, p["delta"].to_numpy(), rcond=None)
    return beta[1]


def estimate(p, label, value, rng, reps=500):
    n = p["kind"].value_counts()
    if n.get("spanning", 0) < 30 or n.get("before", 0) < 30:
        return None
    est = fit(p)
    ids = p["uprn"].unique()
    groups = p.groupby("uprn").indices
    boot = []
    for _ in range(reps):
        take = rng.choice(ids, size=len(ids), replace=True)
        idx = np.concatenate([groups[i] for i in take])
        q = p.iloc[idx]
        if (q["kind"] == "spanning").sum() and (q["kind"] == "before").sum():
            boot.append(fit(q))
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return {"group": label, "value": value, "pairs_before": int(n.get("before", 0)), "pairs_spanning": int(n.get("spanning", 0)),
            "pairs_after": int(n.get("after", 0)), "mean_change_before": p.loc[p.kind == "before", "delta"].mean(),
            "mean_change_spanning": p.loc[p.kind == "spanning", "delta"].mean(),
            "shift_sap": est, "ci_low": lo, "ci_high": hi}


def monthly(e, start="2023-01-01"):
    """mean SAP of RdSAP certificates by lodgement month, raw and adjusted for the mix of dwellings (fixed effects of
    property type, built form, age band and fuel group, at their overall shares)"""
    m = e[e["date"] >= start].copy()
    m["month"] = m["date"].dt.to_period("M").astype(str)
    X = pd.get_dummies(m[["month", "PROPERTY_TYPE", "BUILT_FORM", "age_group", "fuel_group"]].astype(str), drop_first=False, dtype=float)
    month_cols = [c for c in X.columns if c.startswith("month_")]
    other = [c for c in X.columns if not c.startswith("month_")]
    A = X[month_cols + other[1:]].to_numpy()
    beta, *_ = np.linalg.lstsq(A, m["sap"].to_numpy(), rcond=None)
    adj = beta[:len(month_cols)] + X[other[1:]].mean().to_numpy() @ beta[len(month_cols):]
    raw = m.groupby("month")["sap"].agg(["size", "mean"])
    return pd.DataFrame({"month": [c.replace("month_", "") for c in month_cols], "adjusted_mean_sap": adj}).merge(
        raw.rename(columns={"size": "n", "mean": "raw_mean_sap"}).reset_index(), on="month")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--cutoff", default="2025-06-15")
    a = ap.parse_args()
    rng = np.random.default_rng(0)
    e = load(a.area)
    p = pairs(e, a.cutoff)
    rows = [estimate(p, "all", "all", rng)]
    for col in ("property_type", "fuel_group", "age_group"):
        for v, g in p.groupby(col):
            rows.append(estimate(g, col, v, rng))
    out = pd.DataFrame([r for r in rows if r])
    d = DATA / a.area / "analysis"
    out.round(3).to_csv(keep(d / "method_change.csv"), index=False)
    s = p[p.kind == "spanning"]
    bands = pd.crosstab(s["band0"], s["band1"], normalize="index").reindex(index=list(BANDS), columns=list(BANDS)).fillna(0)
    bands.round(3).to_csv(keep(d / "method_change_bands.csv"))
    monthly(e).round(2).to_csv(keep(d / "method_change_monthly.csv"), index=False)
    share = lambda k: (p[p.kind == k]["band1"] != p[p.kind == k]["band0"]).mean()
    print(f"{a.area}: pairs {p.kind.value_counts().to_dict()}; band changed: before {share('before'):.3f}, spanning {share('spanning'):.3f}")
    print(out.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
