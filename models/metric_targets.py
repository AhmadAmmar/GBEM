"""Fabric or heating system? Can open data estimate the separate metrics proposed for EPC reform?

    python metric_targets.py --area belfast|london --year 2024 [--sample 50000] [--featureset eo_morph_phys]

Reform of the EPC regime in England has proposed rating homes on several metrics instead of one band (fabric
performance, heating system, energy cost, smart readiness). Here the labels are built from the certificates and the
predictors are open data only (satellite, form, streets, LiDAR, physics geometry; --featureset of baseline.py):
  fabric         space-heating demand per m2 from the envelope and the certificate's wall, roof, floor and glazing
                 descriptions (analysis/physics_check.py, q_as_described_kwh_m2): a fabric metric independent of the
                 heating system
  heating        main heating efficiency rating on the certificate (Very Poor 1 ... Very Good 5)
  gas heated     main heating fuel is mains gas (1/0)
  sap            the SAP score, for comparison
LightGBM, spatial 5-fold cross-validation (2 km blocks). Metrics: R2 and Spearman correlation (fabric, sap), quadratic
weighted kappa and accuracy (heating), ROC AUC (gas heated).
Output: data/<area>/model/results/metric_targets_<year>.csv
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy import stats
from sklearn.model_selection import GroupKFold
from sklearn.metrics import r2_score, cohen_kappa_score, accuracy_score, roc_auc_score
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import baseline as B
from safeio import keep                      # existing outputs are archived, never overwritten

RATING = {"very poor": 1, "poor": 2, "average": 3, "good": 4, "very good": 5}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--sample", type=int); ap.add_argument("--featureset", default="eo_morph_phys")
    a = ap.parse_args()
    d, dd = B.load(a.area, [a.year])
    if a.sample and a.sample < len(d):
        d = d.sample(n=a.sample, random_state=42).reset_index(drop=True)
    d["id_cert"] = d["id_cert"].astype(str)
    ph = pd.read_parquet(B.DATA / a.area / "analysis/physics_cert.parquet", columns=["cert_id", "q_as_described_kwh_m2"]).rename(columns={"cert_id": "id_cert"})
    c = pd.read_parquet(B.DATA / a.area / "epc/certificates_linked.parquet", columns=["cert_id", "MAINHEAT_ENERGY_EFF", "MAIN_FUEL"]).rename(columns={"cert_id": "id_cert"})
    c["id_cert"] = c["id_cert"].astype(str)
    d = d.merge(ph.drop_duplicates("id_cert"), on="id_cert", how="left").merge(c.drop_duplicates("id_cert"), on="id_cert", how="left")
    fuel = d["MAIN_FUEL"].astype("string").str.lower().fillna("")
    T = {"fabric": d["q_as_described_kwh_m2"].where(d["q_as_described_kwh_m2"].between(5, 1000)),
         "heating": d["MAINHEAT_ENERGY_EFF"].astype("string").str.strip().str.lower().map(RATING),
         "gas heated": pd.Series(np.where(fuel.eq(""), np.nan, fuel.str.contains("gas") & ~fuel.str.contains("lpg|bottled")).astype(float), index=d.index),
         "sap": pd.to_numeric(d["label_sap"], errors="coerce")}
    X = B.features(d, dd, B.SETS[a.featureset])
    g = (np.floor(d["x"] / 2000).astype(int).astype(str) + "_" + np.floor(d["y"] / 2000).astype(int).astype(str)).to_numpy()
    rows = []
    for name, t in T.items():
        y = pd.to_numeric(t, errors="coerce").to_numpy("float64")
        ok = ~np.isnan(y)
        idx = np.flatnonzero(ok)
        p = np.full(len(y), np.nan)
        for tr, te in GroupKFold(n_splits=5).split(idx, groups=g[idx]):
            if name == "gas heated":
                m = lgb.LGBMClassifier(**B.LGBM).fit(X.iloc[idx[tr]], y[idx[tr]])
                p[idx[te]] = m.predict_proba(X.iloc[idx[te]])[:, 1]
            else:
                m = lgb.LGBMRegressor(**B.LGBM).fit(X.iloc[idx[tr]], y[idx[tr]])
                p[idx[te]] = m.predict(X.iloc[idx[te]])
        yy, pp = y[ok], p[ok]
        r = {"area": a.area, "year": a.year, "featureset": a.featureset, "target": name, "n": int(ok.sum())}
        if name == "gas heated":
            r.update({"auc": roc_auc_score(yy, pp), "prevalence": yy.mean()})
        elif name == "heating":
            pr = np.clip(np.round(pp), 1, 5)
            r.update({"qwk": cohen_kappa_score(yy.astype(int), pr.astype(int), weights="quadratic"), "accuracy": accuracy_score(yy, pr),
                      "spearman": stats.spearmanr(yy, pp)[0]})
        else:
            r.update({"r2": r2_score(yy, pp), "spearman": stats.spearmanr(yy, pp)[0]})
        rows.append(r)
        print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()}, flush=True)
    pd.DataFrame(rows).round(4).to_csv(keep(B.DATA / a.area / "model/results" / f"metric_targets_{a.year}.csv"), index=False)


if __name__ == "__main__":
    main()
