"""How much of the model's error is label error? Evaluation against repeat certificates of the same home.

    python noise_eval.py --area belfast|london [--tag <model run tag>] [--days 365]

Homes certified twice within --days days with the same main fuel, type, built form and floor area (within 10%), as in
analysis/ground_truth.py, where one of the two certificates has an out-of-fold prediction (models/baseline.py,
spatial cross-validation). For each pair: the prediction p of the certificate in the model run, its own SAP s1, the
other certificate's SAP s2, and their mean m = (s1 + s2) / 2. Reported per feature set (LightGBM SAP regressor):
  MAE(p, s1)    the usual error
  MAE(p, s2)    error against an independent assessment of the same home
  MAE(p, m)     error against a less noisy label (the mean of two assessments)
  MAE(s1, s2)   disagreement between the two certificates
If part of MAE(p, s1) is label noise, MAE(p, m) is smaller; with independent assessment errors of equal variance,
the noise in a single certificate is MAE(s1, s2) / sqrt(2) (for a normal error, mean absolute values scale this way).
Output: data/<area>/model/results/noise_eval_<tag>.csv
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"
TAG = {"london": "2024_s50k", "belfast": "2024"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--tag"); ap.add_argument("--days", type=int, default=365)
    a = ap.parse_args()
    tag = a.tag or TAG[a.area]
    e = pd.read_parquet(DATA / a.area / "analysis/cert_enriched.parquet",
                        columns=["cert_id", "uprn", "date", "sap", "fuel", "property_type", "built_form", "floor_area"])
    e = e[e["uprn"].notna() & ~e["uprn"].isin(["nan", "None"]) & e["sap"].notna() & e["date"].notna()].sort_values(["uprn", "date"])
    e["cert_id"] = e["cert_id"].astype(str)
    pairs = []
    for shift in (1, -1):                                   # the other certificate before or after
        o = e.groupby("uprn")[["cert_id", "date", "sap", "fuel", "property_type", "built_form", "floor_area"]].shift(shift)
        p = pd.DataFrame({"cert_id": e["cert_id"], "s1": e["sap"], "s2": o["sap"], "gap": (e["date"] - o["date"]).dt.days.abs(),
                          "ok": e["fuel"].eq(o["fuel"]) & e["property_type"].eq(o["property_type"]) & e["built_form"].eq(o["built_form"])
                                & ((e["floor_area"] / o["floor_area"] - 1).abs().fillna(0) <= 0.1)})
        pairs.append(p[p["ok"] & (p["gap"] > 0) & (p["gap"] <= a.days)])
    pr = pd.concat(pairs).drop_duplicates("cert_id")
    oof = pd.read_parquet(DATA / a.area / "model/results" / f"oof_{tag}.parquet")
    oof["id_cert"] = oof["id_cert"].astype(str)
    d = pr.merge(oof, left_on="cert_id", right_on="id_cert", how="inner")
    rows = []
    for c in [c for c in oof.columns if c.startswith("sap_lgbm_")]:
        p = d[c]
        ok = p.notna() & d["s2"].notna()
        m = (d["s1"] + d["s2"]) / 2
        rows.append({"area": a.area, "featureset": c[len("sap_lgbm_"):], "pairs": int(ok.sum()),
                     "mae_vs_own": (p - d["s1"])[ok].abs().mean(), "mae_vs_other": (p - d["s2"])[ok].abs().mean(),
                     "mae_vs_mean_of_two": (p - m)[ok].abs().mean(), "mae_cert_vs_cert": (d["s1"] - d["s2"])[ok].abs().mean(),
                     "noise_single_cert_est": (d["s1"] - d["s2"])[ok].abs().mean() / np.sqrt(2)})
    res = pd.DataFrame(rows)
    res.round(3).to_csv(keep(DATA / a.area / "model/results" / f"noise_eval_{tag}.csv"), index=False)
    print(f"{a.area}: {len(d):,} repeat pairs with an out-of-fold prediction")
    print(res.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
