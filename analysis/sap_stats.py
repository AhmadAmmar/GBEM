"""Descriptive statistics of the label (SAP score and A-G band) for each city: the certificates used for modelling and the
current certified stock. For the data chapter and for defining the scale wherever results are reported.

    python sap_stats.py [--year 2024]

Inputs: data/<area>/model/dataset_<year>.parquet (label_sap, label_rating: one certificate per property, the year's
modelling set) and data/<area>/analysis/stock_current.parquet (sap, band: latest valid certificate per property).
SAP bands (SAP 2012 / RdSAP): A 92 and above, B 81-91, C 69-80, D 55-68, E 39-54, F 21-38, G 1-20.
Output: data/sap_stats_<year>.csv (one row per city and set): n, mean, standard deviation, minimum, 5th, 25th, 50th,
75th and 95th percentiles, maximum, share above 100, the mean absolute error of predicting the median for every
dwelling (the reference against which a model's MAE is read), and the share of each band.
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"
BANDS = "ABCDEFG"


def stats(sap, band):
    s = pd.to_numeric(sap, errors="coerce").dropna()
    q = s.quantile([0.05, 0.25, 0.5, 0.75, 0.95])
    row = {"n": len(s), "mean": s.mean(), "sd": s.std(), "min": s.min(), "p05": q[0.05], "p25": q[0.25], "median": q[0.5],
           "p75": q[0.75], "p95": q[0.95], "max": s.max(), "share_above_100": (s > 100).mean(),
           "mae_of_median": (s - q[0.5]).abs().mean()}    # the error of predicting the median for every dwelling
    b = pd.Series(band).astype(str).str.strip().str.upper()
    row.update({f"share_{x}": (b == x).mean() for x in BANDS})
    return row


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--year", type=int, default=2024)
    a = ap.parse_args()
    rows = []
    for area in ("london", "belfast"):
        d = pd.read_parquet(DATA / area / f"model/dataset_{a.year}.parquet", columns=["label_sap", "label_rating"])
        rows.append({"area": area, "set": f"certificates {a.year} (modelling set)", **stats(d["label_sap"], d["label_rating"])})
        c = pd.read_parquet(DATA / area / "analysis/stock_current.parquet", columns=["sap", "band"])
        rows.append({"area": area, "set": "current certified stock", **stats(c["sap"], c["band"])})
    out = pd.DataFrame(rows)
    p = DATA / f"sap_stats_{a.year}.csv"
    out.round(4).to_csv(keep(p), index=False)
    print(out.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
