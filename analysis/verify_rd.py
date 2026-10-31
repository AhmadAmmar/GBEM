"""Independent recalculation of the RdSAP 10 regression discontinuity, sharing no estimation code with method_change_rd.py.

    python verify_rd.py --area london|belfast

Reads the certificates directly and fits the model with NumPy least squares and hand-built dummies, giving HC1 intervals as in the paper
and intervals clustered by lodgement day, which allow for certificates on the same day being correlated. Compares each estimate with
method_change_rd.csv. It repeats the calculation and tests one source of error in the intervals; it does not show the design is valid.
"""
import argparse, pathlib, re
import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
COLS = ["REPORT_TYPE", "LODGEMENT_DATE", "sap_score", "UPRN", "CURRENT_ENERGY_RATING", "PROPERTY_TYPE", "BUILT_FORM", "CONSTRUCTION_AGE_BAND", "MAIN_FUEL"]
Z = 1.959964


def fit(y, X, days):
    """OLS coefficient 0 (post) with HC1 and day-clustered standard errors."""
    q, r = np.linalg.qr(X)
    b = np.linalg.solve(r, q.T @ y)
    u = y - X @ b
    inv = np.linalg.inv(r)
    bread = inv @ inv.T
    n, k = X.shape
    hc = bread @ ((X * (u ** 2)[:, None]).T @ X) @ bread * n / (n - k)
    s = pd.DataFrame(X * u[:, None]).groupby(days).sum().to_numpy()
    g = len(s)
    cl = bread @ (s.T @ s) @ bread * (g / (g - 1)) * ((n - 1) / (n - k))
    return b[0], np.sqrt(hc[0, 0]), np.sqrt(cl[0, 0]), g


def design(d, cutoff, poly=1):
    """Column 0 is post: separate trends each side, intercept and full-rank dummies."""
    t = (d.date - cutoff).dt.days.to_numpy() / 30.0
    post = (t >= 0).astype(float)
    cols = [post, np.ones(len(d)), t, post * t]
    if poly == 2:
        cols += [t ** 2, post * t ** 2]
    for c in ["pt", "bf", "ag", "fg"]:
        v = d[c].to_numpy()
        levels = sorted(set(v))
        cols += [(v == x).astype(float) for x in levels[1:]]
    return np.column_stack(cols)


def age_start(band):
    m = re.search(r"\d{4}", str(band))
    return int(m.group()) if m else -1


def load(area):
    e = pd.read_parquet(ROOT / "data" / area / "epc/certificates_linked.parquet", columns=COLS)
    e = e[e.REPORT_TYPE.astype(str) == "2"].copy()
    e["date"] = pd.to_datetime(e.LODGEMENT_DATE, errors="coerce").dt.tz_localize(None)
    e["sap"] = pd.to_numeric(e.sap_score, errors="coerce")
    e = e[e.sap.between(1, 150) & e.date.notna() & e.UPRN.notna()]
    e = e[e.date >= "2022-01-01"]
    fuel = e.MAIN_FUEL.astype(str).str.lower()
    e["fg"] = np.select([fuel.str.contains("mains gas"), fuel.str.contains("electric"), fuel.str.contains("oil")], ["gas", "elec", "oil"], "other")
    start = e.CONSTRUCTION_AGE_BAND.map(age_start)
    # same groups as the paper, so that estimates can be compared
    e["ag"] = np.select([start < 0, start <= 1929, start <= 1949, start <= 1975, start <= 1990, start <= 2002], ["none", "g1", "g2", "g3", "g4", "g5"], "g6")
    e["pt"], e["bf"] = e.PROPERTY_TYPE.astype(object).astype(str), e.BUILT_FORM.astype(object).astype(str)
    e["cb"] = e.CURRENT_ENERGY_RATING.astype(str).isin(list("ABC")).astype(float)
    return e


def estimate(e, cut, donut=14, bw=90, poly=1, outcome="sap"):
    c = pd.Timestamp(cut)
    d = e[(e.date >= c - pd.Timedelta(days=bw)) & (e.date < c + pd.Timedelta(days=bw))]
    d = d[(d.date < c - pd.Timedelta(days=donut)) | (d.date >= c)]
    b, hc, cl, g = fit(d[outcome].to_numpy(float), design(d, c, poly), d.date.dt.strftime("%Y%m%d").to_numpy())
    return {"n": len(d), "days": g, "jump": b, "hc_lo": b - Z * hc, "hc_hi": b + Z * hc, "day_lo": b - Z * cl, "day_hi": b + Z * cl}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--area", default="london")
    a = ap.parse_args()
    e = load(a.area)
    old = pd.read_csv(ROOT / "data" / a.area / "analysis/method_change_rd.csv")
    rows = []
    for cut in ["2025-06-15", "2024-06-15", "2023-06-15"]:
        for donut, bw, poly, y, name in [(14, 90, 1, "sap", "sap"), (14, 90, 1, "cb", "c_or_better"), (0, 90, 1, "sap", "sap"), (0, 90, 1, "cb", "c_or_better"),
                                         (14, 60, 1, "sap", "sap"), (14, 180, 1, "sap", "sap"), (14, 90, 2, "sap", "sap")]:
            r = estimate(e, cut, donut, bw, poly, y)
            o = old[(old.cutoff == cut) & (old.donut_days == donut) & (old.bandwidth_days == bw) & (old.trend == poly) & (old.outcome == name) & (old.group == "all")].iloc[0]
            rows.append({"cutoff": cut, "outcome": name, "donut": donut, "bw": bw, "trend": poly, **r, "saved_n": o.n, "saved_jump": o.jump, "saved_lo": o.ci_low, "saved_hi": o.ci_high})
    r = pd.DataFrame(rows)
    pd.set_option("display.width", 220)
    print(r.round(4).to_string(index=False))
    print("largest difference from saved estimates:", round(float((r.jump - r.saved_jump).abs().max()), 5), "; n differs in", int((r.n != r.saved_n).sum()), "rows")
    r.to_csv(ROOT / "data" / a.area / "analysis/verify_rd.csv", index=False)
