"""Who was in the rush of EPC lodgements before RdSAP 10 (15 June 2025), and does it look like portfolios?

    python rush_composition.py --area london

Compares the last week under the old method (8-14 June 2025) with the eight weeks before it and the same week of 2024, among RdSAP
certificates (report type 2). Prints shares by dwelling type, tenure and transaction type, and three batch signals: certificates lodged on
the same day as at least four others in the postcode, in a postcode with at least ten in the week, and with an inspection over 14 days old.

The register names no owner, assessor or client, so these signals are consistent with portfolios and cannot prove them.
"""
import argparse, pathlib, re
import pandas as pd
from safeio import keep

ROOT = pathlib.Path(__file__).resolve().parents[2]
COLS = ["REPORT_TYPE", "LODGEMENT_DATE", "INSPECTION_DATE", "POSTCODE", "PROPERTY_TYPE", "CONSTRUCTION_AGE_BAND", "TENURE", "TRANSACTION_TYPE"]
WINDOWS = {"rush": ("2025-06-08", "2025-06-14"), "before": ("2025-04-13", "2025-06-07"), "same week 2024": ("2024-06-08", "2024-06-14")}


def age_1950_75(band):
    """True for bands wholly within 1950-1975."""
    y = [int(v) for v in re.findall(r"\b(1[89]\d\d|20\d\d)\b", str(band))]
    return len(y) == 2 and y[0] >= 1950 and y[1] <= 1976


def tenure(t):
    t = str(t).lower()
    if "owner" in t:
        return "owner-occupied"
    if "social" in t:
        return "social rented"
    if "private" in t:
        return "private rented"
    return "unknown"


def signals(w):
    """Shares for one window of certificates."""
    day = w.groupby(["POSTCODE", "lodged"]).POSTCODE.transform("size")
    week = w.groupby(["POSTCODE", "week"]).POSTCODE.transform("size")
    t = w.TENURE.map(tenure)
    return {"certificates": len(w), "per week": len(w) / w.week.nunique(),
            "1950-75 flat or maisonette": (w.PROPERTY_TYPE.isin(["Flat", "Maisonette"]) & w.CONSTRUCTION_AGE_BAND.map(age_1950_75)).mean(),
            "flat or maisonette": w.PROPERTY_TYPE.isin(["Flat", "Maisonette"]).mean(),
            "social rented": (t == "social rented").mean(), "private rented": (t == "private rented").mean(),
            "owner-occupied": (t == "owner-occupied").mean(), "tenure unknown": (t == "unknown").mean(),
            "5+ same postcode same day": (day >= 5).mean(), "10+ same postcode same week": (week >= 10).mean(),
            "inspected over 14 days before": ((w.lodged - w.inspected).dt.days > 14).mean()}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--area", default="london")
    a = ap.parse_args()
    d = pd.read_parquet(ROOT / "data" / a.area / "epc/certificates.parquet", columns=COLS)
    d = d[d.REPORT_TYPE.astype(str).str.strip().isin(["2", "2.0"])].copy()
    d["lodged"], d["inspected"] = pd.to_datetime(d.LODGEMENT_DATE, errors="coerce"), pd.to_datetime(d.INSPECTION_DATE, errors="coerce")
    res = {}
    for name, (lo, hi) in WINDOWS.items():
        w = d[d.lodged.between(lo, hi)].copy()
        w["week"] = (w.lodged - pd.Timestamp(lo)).dt.days // 7
        res[name] = signals(w)
    r = pd.DataFrame(res)
    b, u = res["before"], res["rush"]
    excess = u["certificates"] - b["per week"]
    r.loc["usual-week ratio"] = [u["certificates"] / b["per week"], 1.0, res["same week 2024"]["certificates"] / b["per week"]]
    print(r.round(3).to_string())
    print(f"excess certificates: {excess:.0f}")
    for k in ["1950-75 flat or maisonette", "social rented", "private rented", "owner-occupied", "5+ same postcode same day"]:
        print(f"share of the excess that is {k}: {(u[k] * u['certificates'] - b[k] * b['per week']) / excess:.3f}")
    out = ROOT / "data" / a.area / "analysis/rush_composition.csv"
    keep(out)
    r.to_csv(out)
