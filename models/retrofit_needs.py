"""Retrofit needs for homes without a certificate: can satellite, morphology and LiDAR features tell which building
element is poor?

    python retrofit_needs.py --area belfast --years 2024 [--sample 50000] [--featureset eo_morph]

Targets, from the certificate's element ratings (Poor or Very Poor = 1; Average, Good, Very Good = 0; unrated left out):
walls, roof, windows, main heating, heating controls, hot water. Also "any of walls/roof/windows poor" (fabric).
Features: a feature set of baseline.py (default eo_morph: satellite + morphology + streets + LiDAR), i.e. information
available for every building. LightGBM binary classifiers with spatial 5-fold cross-validation (2 km blocks).
Metrics: ROC AUC, average precision (vs the prevalence), and the share of the poor homes found in the top 20% of
predicted risk (how well a survey could be targeted).
Output in data/<area>/model/results/: retrofit_needs_<tag>.csv (metrics) and retrofit_oof_<tag>.parquet (out-of-fold
probabilities per certificate, for maps).
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score, average_precision_score
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import baseline as B
from safeio import keep                      # existing outputs are archived, never overwritten

ELEMENTS = {"walls": "WALLS_ENERGY_EFF", "roof": "ROOF_ENERGY_EFF", "windows": "WINDOWS_ENERGY_EFF",
            "mainheat": "MAINHEAT_ENERGY_EFF", "controls": "MAINHEATC_ENERGY_EFF", "hotwater": "HOT_WATER_ENERGY_EFF"}


def targets(area, cert_ids):
    c = pd.read_parquet(B.DATA / area / "epc/certificates_linked.parquet", columns=["cert_id"] + list(ELEMENTS.values()))
    c["cert_id"] = c["cert_id"].astype(str)
    c = c.drop_duplicates("cert_id").set_index("cert_id").reindex(cert_ids)
    out = pd.DataFrame(index=c.index)
    for k, col in ELEMENTS.items():
        v = c[col].astype("string").str.strip().str.lower()
        out[k] = np.select([v.isin(["poor", "very poor"]), v.isin(["average", "good", "very good"])], [1.0, 0.0], np.nan)
    fab = out[["walls", "roof", "windows"]]
    out["fabric"] = np.where(fab.eq(1).any(axis=1), 1.0, np.where(fab.notna().any(axis=1), 0.0, np.nan))
    return out.reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--years", nargs="+", type=int, required=True)
    ap.add_argument("--sample", type=int); ap.add_argument("--featureset", default="eo_morph")
    a = ap.parse_args()
    tag = "-".join(map(str, a.years)) + (f"_s{a.sample // 1000}k" if a.sample else "") + f"_{a.featureset}"
    d, dd = B.load(a.area, a.years)
    if a.sample and a.sample < len(d):
        d = d.sample(n=a.sample, random_state=42).reset_index(drop=True)
    X = B.features(d, dd, B.SETS[a.featureset])
    T = targets(a.area, d["id_cert"].astype(str))
    blocks = (np.floor(d["x"] / 2000).astype(int).astype(str) + "_" + np.floor(d["y"] / 2000).astype(int).astype(str)).to_numpy()
    rows, oof = [], pd.DataFrame({"id_cert": d["id_cert"], "x": d["x"], "y": d["y"]})
    params = {**B.LGBM, "n_estimators": 250}
    for k in T.columns:
        y = T[k].to_numpy()
        ok = ~np.isnan(y)
        if ok.sum() < 500 or y[ok].sum() < 50:
            print(f"  {k}: too few rated / poor ({int(ok.sum())} / {int(np.nansum(y))})"); continue
        p = np.full(len(d), np.nan)
        idx = np.flatnonzero(ok)
        for tr, te in GroupKFold(n_splits=5).split(idx, groups=blocks[idx]):
            m = lgb.LGBMClassifier(is_unbalance=True, **params).fit(X.iloc[idx[tr]], y[idx[tr]])
            p[idx[te]] = m.predict_proba(X.iloc[idx[te]])[:, 1]
        yy, pp = y[ok], p[ok]
        top = pp >= np.quantile(pp, 0.8)
        rows.append({"area": a.area, "years": "-".join(map(str, a.years)), "featureset": a.featureset, "element": k,
                     "n_rated": int(ok.sum()), "prevalence": yy.mean(), "auc": roc_auc_score(yy, pp),
                     "avg_precision": average_precision_score(yy, pp), "share_found_in_top20": yy[top].sum() / yy.sum(),
                     "lift_top20": yy[top].mean() / yy.mean()})
        oof[f"p_{k}"] = p
        r = rows[-1]
        print(f"  {k:9s} n {r['n_rated']:6d} prevalence {r['prevalence']:.2f} AUC {r['auc']:.3f} AP {r['avg_precision']:.3f} "
              f"top-20% finds {r['share_found_in_top20']:.0%} (lift {r['lift_top20']:.1f})", flush=True)
    out = B.DATA / a.area / "model/results"
    pd.DataFrame(rows).round(4).to_csv(keep(out / f"retrofit_needs_{tag}.csv"), index=False)
    oof.to_parquet(keep(out / f"retrofit_oof_{tag}.parquet"), index=False)
    print("written", out)


if __name__ == "__main__":
    main()
