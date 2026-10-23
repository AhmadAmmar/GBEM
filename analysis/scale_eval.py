"""At which scale are the estimates reliable, and are the model's probabilities calibrated?

    python scale_eval.py --area belfast|london [--tag <model run tag>]

Uses the spatial out-of-fold predictions of models/baseline.py (oof_<tag>.parquet: every certificate predicted by a
model that did not see its 2 km block).
1. Scale: actual and predicted SAP averaged over buildings (footprints), streets, neighbourhoods (London LSOA,
   Belfast ward) and 250 m cells, for units with at least 5 certificates (buildings: 2); per scale and feature set:
   units, Spearman and Pearson correlation, R2, MAE of the unit means, and the share of units whose predicted mean
   band (from the mean SAP) equals the actual one. Averaging removes much of the dwelling-level noise; the question is
   how much of the area pattern the model recovers.
2. Calibration: for the band classifier, the top-class probability against the observed accuracy in 10 equal-width
   bins (reliability table) and the expected calibration error ECE = sum_b (n_b / N) |accuracy_b - confidence_b|;
   with class weights "balanced" the probabilities of rare bands are inflated, so ECE is expected to be large.
Outputs in data/<area>/model/results/: scale_<tag>.csv, calibration_<tag>.csv, reliability_<tag>.csv
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
from scipy import stats
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "models"))
from safeio import keep                      # existing outputs are archived, never overwritten
import baseline as B

DATA = B.DATA
TAG = {"london": "2024_s50k", "belfast": "2024"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--tag")
    a = ap.parse_args()
    tag = a.tag or TAG[a.area]
    res = DATA / a.area / "model/results"
    oof = pd.read_parquet(res / f"oof_{tag}.parquet")
    oof["id_cert"] = oof["id_cert"].astype(str)
    e = pd.read_parquet(DATA / a.area / "analysis/cert_enriched.parquet", columns=["cert_id", "fp_id", "street", "nbhd", "cell"])
    e["cert_id"] = e["cert_id"].astype(str)
    d = oof.merge(e.rename(columns={"cert_id": "id_cert"}), on="id_cert", how="left")
    if "id_fp" in d:
        d["fp_id"] = d["fp_id"].fillna(d["id_fp"])
    sets = [c[len("sap_lgbm_"):] for c in d.columns if c.startswith("sap_lgbm_")]
    rows = []
    for fs in sets:
        p = d[f"sap_lgbm_{fs}"]
        for unit, minn in (("certificate", 1), ("fp_id", 2), ("street", 5), ("cell", 5), ("nbhd", 5)):
            if unit == "certificate":
                g = pd.DataFrame({"a": d["actual_sap"], "p": p, "n": 1})
            else:
                g = d.assign(p=p).groupby(unit).agg(a=("actual_sap", "mean"), p=("p", "mean"), n=("actual_sap", "size"))
                g = g[g["n"] >= minn]
            g = g.dropna()
            if len(g) < 20:
                continue
            same = (B.sap_to_band(g["a"].to_numpy()) == B.sap_to_band(g["p"].to_numpy())).mean()
            rows.append({"featureset": fs, "scale": {"fp_id": "building", "nbhd": "neighbourhood", "cell": "250 m cell"}.get(unit, unit),
                         "units": len(g), "certificates_per_unit": g["n"].median(), "spearman": stats.spearmanr(g["a"], g["p"])[0],
                         "pearson": stats.pearsonr(g["a"], g["p"])[0], "r2": 1 - ((g["a"] - g["p"]) ** 2).sum() / ((g["a"] - g["a"].mean()) ** 2).sum(),
                         "mae": (g["a"] - g["p"]).abs().mean(), "same_band_of_mean": same})
    sc = pd.DataFrame(rows)
    sc.round(4).to_csv(keep(res / f"scale_{tag}.csv"), index=False)
    print(sc[sc["featureset"].isin(["eo", "eo_morph", "eo_morph_floor", "all"])].round(3).to_string(index=False))
    cal, rel = [], []
    for fs in [c[len("conf_lgbm_"):] for c in d.columns if c.startswith("conf_lgbm_")]:
        conf = d[f"conf_lgbm_{fs}"].to_numpy()
        ok = (d[f"pred_lgbm_{fs}"] == d["actual"]).to_numpy()
        bins = np.clip((conf * 10).astype(int), 0, 9)
        ece = 0.0
        for b in range(10):
            m = bins == b
            if m.any():
                ece += m.mean() * abs(ok[m].mean() - conf[m].mean())
                rel.append({"featureset": fs, "bin": f"{b / 10:.1f}-{(b + 1) / 10:.1f}", "n": int(m.sum()),
                            "confidence": conf[m].mean(), "accuracy": ok[m].mean()})
        cal.append({"featureset": fs, "n": len(conf), "mean_confidence": conf.mean(), "accuracy": ok.mean(), "ece": ece})
    cal = pd.DataFrame(cal)
    cal.round(4).to_csv(keep(res / f"calibration_{tag}.csv"), index=False)
    pd.DataFrame(rel).round(4).to_csv(keep(res / f"reliability_{tag}.csv"), index=False)
    print(cal.round(3).to_string(index=False))
    print("written", res)


if __name__ == "__main__":
    main()
