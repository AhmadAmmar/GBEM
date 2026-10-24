"""Repeated spatial cross-validation: uncertainty of the headline results and sensitivity to the block size.

    python repeat_cv.py --area belfast|london --year 2024 [--sample 50000] [--blocks 1 2 5] [--seeds 3]
                        [--featuresets eo eo_morph eo_morph_floor_phys]

The main results (models/baseline.py) use one assignment of 2 km blocks to five folds. Here the blocks are 1, 2 and 5 km
squares and, for each size, the blocks are assigned to five folds at random with --seeds different seeds. For every
feature set, block size and seed the SAP regressor and the band classifier (LightGBM, settings of baseline.py) are
evaluated out of fold: SAP MAE and R2, band accuracy, macro-F1 and quadratic weighted kappa.
The summary gives, per feature set and block size, the mean over seeds and the range, and the mean over all runs with
a 95% interval (t distribution over runs). Larger blocks put test homes further from training homes; if performance
falls with block size, part of the 2 km estimate still rests on spatial proximity.
Outputs in data/<area>/model/results/: repeat_cv_<tag>.csv (every run) and repeat_cv_<tag>_summary.csv
"""
import argparse, pathlib, sys, time
import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy import stats
from sklearn.metrics import mean_absolute_error, r2_score
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import baseline as B
from safeio import keep                      # existing outputs are archived, never overwritten


def folds(x, y, km, seed, k=5):
    blocks = pd.Series(np.floor(x / (km * 1000)).astype(int).astype(str) + "_" + np.floor(y / (km * 1000)).astype(int).astype(str))
    u = blocks.unique()
    f = dict(zip(np.random.default_rng(seed).permutation(u), np.arange(len(u)) % k))
    return blocks.map(f).to_numpy()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--sample", type=int); ap.add_argument("--blocks", nargs="+", type=float, default=[1, 2, 5])
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--featuresets", nargs="+", default=["eo", "eo_morph", "eo_morph_floor_phys"])
    a = ap.parse_args()
    d, dd = B.load(a.area, [a.year])
    if a.sample and len(d) > a.sample:
        d = d.sample(n=a.sample, random_state=42).reset_index(drop=True)
    yb = d["label_rating"].to_numpy()
    yi = np.searchsorted(B.BANDS, yb)
    sap = pd.to_numeric(d["label_sap"], errors="coerce").to_numpy("float64")
    rows = []
    for fs in a.featuresets:
        X = B.features(d, dd, B.SETS[fs])
        for km in a.blocks:
            for seed in range(a.seeds):
                t0 = time.time()
                f = folds(d["x"].to_numpy(), d["y"].to_numpy(), km, seed)
                ps, pb = np.full(len(d), np.nan), np.empty(len(d), dtype=object)
                for k in range(5):
                    tr, te = f != k, f == k
                    ok = tr & ~np.isnan(sap)
                    ps[te] = lgb.LGBMRegressor(**B.LGBM).fit(X[ok], sap[ok]).predict(X[te])
                    clf = lgb.LGBMClassifier(class_weight="balanced", **B.LGBM).fit(X[tr], yi[tr])
                    pb[te] = np.array(B.BANDS)[clf.classes_[clf.predict_proba(X[te]).argmax(1)]]
                ok = ~np.isnan(sap)
                m = B.cls_metrics(yb, pb.astype(str))
                rows.append({"area": a.area, "year": a.year, "n": len(d), "featureset": fs, "block_km": km, "seed": seed,
                             "sap_mae": mean_absolute_error(sap[ok], ps[ok]), "sap_r2": r2_score(sap[ok], ps[ok]),
                             "accuracy": m["accuracy"], "macro_f1": m["macro_f1"], "qwk": m["qwk"],
                             "seconds": round(time.time() - t0)})
                r = rows[-1]
                print(f"{fs:22s} {km:>3} km seed {seed}: MAE {r['sap_mae']:.2f} R2 {r['sap_r2']:.3f} acc {r['accuracy']:.3f} "
                      f"QWK {r['qwk']:.3f} ({r['seconds']} s)", flush=True)
    res = pd.DataFrame(rows)
    tag = f"{a.year}" + (f"_s{a.sample // 1000}k" if a.sample else "")
    out = B.DATA / a.area / "model/results"
    res.round(4).to_csv(keep(out / f"repeat_cv_{tag}.csv"), index=False)
    summ = []
    for (fs, km), g in res.groupby(["featureset", "block_km"]):
        row = {"area": a.area, "featureset": fs, "block_km": km, "runs": len(g)}
        for c in ("sap_mae", "sap_r2", "accuracy", "macro_f1", "qwk"):
            v = g[c].to_numpy(); h = stats.t.ppf(0.975, len(v) - 1) * v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else np.nan
            row.update({f"{c}_mean": v.mean(), f"{c}_ci_low": v.mean() - h, f"{c}_ci_high": v.mean() + h})
        summ.append(row)
    s = pd.DataFrame(summ).round(4)
    s.to_csv(keep(out / f"repeat_cv_{tag}_summary.csv"), index=False)
    print(s[["featureset", "block_km", "sap_mae_mean", "sap_r2_mean", "qwk_mean", "qwk_ci_low", "qwk_ci_high"]].to_string(index=False))


if __name__ == "__main__":
    main()
