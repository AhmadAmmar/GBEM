"""Does Earth observation add anything over the certificates of neighbouring homes? Two deployment scenarios, with
uncertainty.

    python neighbour_baseline.py --area belfast|london --year 2024 [--sample 30000] [--seeds 2] [--top 150]

Scenarios (5-fold cross-validation):
  gap filling    a home without a certificate among certified neighbours: folds grouped by building footprint (all
                 dwellings of a building in the same fold), otherwise random
  unseen area    a part of the city without certificates: folds of square blocks of 1, 2 and 5 km
Neighbour features of every home come from the training homes only (for training homes, leaving out their own
building): inverse-distance-weighted mean SAP of the 10 nearest certified homes, mean SAP within 100 m and 250 m,
number of certified homes within 250 m, distance to the nearest.
Models (SAP score; band from the predicted score):
  knn            inverse-distance-weighted mean SAP of the 10 nearest training homes (no model)
  neighbours     LightGBM on the neighbour features only
  eo_morph       LightGBM on satellite, climate, form, streets, LiDAR (the --top features by LightGBM gain on the
                 whole sample, to keep run times reasonable)
  eo_morph+nb    both
Uncertainty: every configuration is run with --seeds different fold assignments; for each scenario and seed, a
1,000-fold bootstrap over 1 km cells gives a 95% interval of the difference in SAP MAE between eo_morph+nb and knn
(negative: Earth observation and form improve on interpolation).
Output: data/<area>/model/results/neighbour_baseline_<year>.csv and neighbour_bootstrap_<year>.csv
"""
import argparse, pathlib, sys, time
import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy.spatial import cKDTree
from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_absolute_error, r2_score
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import baseline as B
from safeio import keep                      # existing outputs are archived, never overwritten

NB = ["nb_idw10", "nb_mean100", "nb_mean250", "nb_count250", "nb_dist1"]


def neighbour_features(xy_q, xy_t, sap_t, fp_q=None, fp_t=None):
    """features of query points from training points; with fp ids, a query never uses its own building"""
    tree = cKDTree(xy_t)
    k = min(30, len(xy_t))
    dist, idx = tree.query(xy_q, k=k)
    if fp_q is not None:
        same = fp_t[idx] == fp_q[:, None]
        dist = np.where(same, np.inf, dist)
    order = np.argsort(dist, axis=1)
    dist = np.take_along_axis(dist, order, 1)[:, :10]; idx = np.take_along_axis(idx, order, 1)[:, :10]
    w = 1 / np.maximum(dist, 5) ** 2
    w[~np.isfinite(dist)] = 0
    s = sap_t[idx]
    ws = w.sum(1)
    out = {"nb_idw10": np.where(ws > 0, (w * s).sum(1) / np.maximum(ws, 1e-12), np.nan),     # no neighbour outside the building
           "nb_dist1": np.where(np.isfinite(dist[:, 0]), dist[:, 0], np.nan)}
    for r in (100, 250):
        lst = tree.query_ball_point(xy_q, r)
        means, counts = np.full(len(xy_q), np.nan), np.zeros(len(xy_q))
        for i, l in enumerate(lst):
            if fp_q is not None and len(l):
                l = [j for j in l if fp_t[j] != fp_q[i]]
            if l:
                means[i] = sap_t[l].mean(); counts[i] = len(l)
        out[f"nb_mean{r}"] = means
        if r == 250:
            out["nb_count250"] = counts
    return pd.DataFrame(out)


def score(y, p):
    ok = ~np.isnan(y) & ~np.isnan(p)
    yb, pb = B.sap_to_band(y[ok]), B.sap_to_band(p[ok])
    return {"sap_mae": mean_absolute_error(y[ok], p[ok]), "sap_r2": r2_score(y[ok], p[ok]), **B.cls_metrics(yb, pb)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--sample", type=int); ap.add_argument("--seeds", type=int, default=2); ap.add_argument("--top", type=int, default=150)
    a = ap.parse_args()
    d, dd = B.load(a.area, [a.year])
    d = d[pd.to_numeric(d["label_sap"], errors="coerce").notna() & d["x"].notna()].reset_index(drop=True)
    if a.sample and a.sample < len(d):
        d = d.sample(n=a.sample, random_state=42).reset_index(drop=True)
    X = B.features(d, dd, B.SETS["eo_morph"])
    y = pd.to_numeric(d["label_sap"], errors="coerce").to_numpy("float64")
    gain = lgb.LGBMRegressor(**B.LGBM).fit(X, y).booster_.feature_importance("gain")
    X = X[X.columns[np.argsort(gain)[::-1][:a.top]]]
    xy = d[["x", "y"]].to_numpy("float64")
    fp = d["id_fp"].astype(str).fillna("none").to_numpy()
    cell1 = (np.floor(d["x"] / 1000).astype(int).astype(str) + "_" + np.floor(d["y"] / 1000).astype(int).astype(str)).to_numpy()
    print(f"{a.area} {a.year}: {len(d):,} certificates, {X.shape[1]} EO/form features", flush=True)
    rows, boots = [], []
    scen = [("gap filling", None)] + [(f"unseen area {km} km", km) for km in (1, 2, 5)]
    for name, km in scen:
        for seed in range(a.seeds):
            t0 = time.time()
            if km is None:
                g = fp
            else:
                off = np.random.default_rng(seed).uniform(0, km * 1000, 2)        # shifted block grid per seed
                g = (np.floor((d["x"] + off[0]) / (km * 1000)).astype(int).astype(str) + "_" +
                     np.floor((d["y"] + off[1]) / (km * 1000)).astype(int).astype(str)).to_numpy()
            ug = np.unique(g); perm = dict(zip(ug, np.random.default_rng(100 + seed).permutation(len(ug))))
            gid = np.array([perm[v] for v in g])
            P = {m: np.full(len(d), np.nan) for m in ("knn", "neighbours", "eo_morph", "eo_morph+nb")}
            for tr, te in GroupKFold(n_splits=5).split(X, groups=gid):
                nb_te = neighbour_features(xy[te], xy[tr], y[tr])
                nb_tr = neighbour_features(xy[tr], xy[tr], y[tr], fp[tr], fp[tr])      # leave own building out
                P["knn"][te] = nb_te["nb_idw10"].to_numpy()
                m = lgb.LGBMRegressor(**B.LGBM)
                P["neighbours"][te] = m.fit(nb_tr, y[tr]).predict(nb_te)
                P["eo_morph"][te] = lgb.LGBMRegressor(**B.LGBM).fit(X.iloc[tr], y[tr]).predict(X.iloc[te])
                Xtr = pd.concat([X.iloc[tr].reset_index(drop=True), nb_tr], axis=1)
                Xte = pd.concat([X.iloc[te].reset_index(drop=True), nb_te], axis=1)
                P["eo_morph+nb"][te] = lgb.LGBMRegressor(**B.LGBM).fit(Xtr, y[tr]).predict(Xte)
            for mname, p in P.items():
                rows.append({"area": a.area, "scenario": name, "seed": seed, "model": mname, "n": len(d), **score(y, p)})
            # block bootstrap of the MAE difference (eo_morph+nb - knn) over 1 km cells
            e1, e0 = np.abs(P["eo_morph+nb"] - y), np.abs(P["knn"] - y)
            cdf = pd.DataFrame({"c": cell1, "d": e1 - e0, "w": 1}).groupby("c").agg(s=("d", "sum"), n=("w", "sum"))
            rng = np.random.default_rng(seed)
            draws = [cdf.iloc[rng.integers(0, len(cdf), len(cdf))].pipe(lambda t: t["s"].sum() / t["n"].sum()) for _ in range(1000)]
            boots.append({"area": a.area, "scenario": name, "seed": seed, "mae_diff_eo_nb_minus_knn": (e1 - e0).mean(),
                          "ci_low": np.percentile(draws, 2.5), "ci_high": np.percentile(draws, 97.5)})
            r = {m: rows[-4 + i]["sap_mae"] for i, m in enumerate(P)}
            print(f"  {name:20s} seed {seed}: SAP MAE knn {r['knn']:.2f} | neighbours {r['neighbours']:.2f} | eo_morph {r['eo_morph']:.2f} | "
                  f"eo_morph+nb {r['eo_morph+nb']:.2f}  (diff 95% CI {boots[-1]['ci_low']:+.2f} to {boots[-1]['ci_high']:+.2f}; {time.time() - t0:.0f} s)", flush=True)
    out = B.DATA / a.area / "model/results"
    pd.DataFrame(rows).round(4).to_csv(keep(out / f"neighbour_baseline_{a.year}.csv"), index=False)
    pd.DataFrame(boots).round(4).to_csv(keep(out / f"neighbour_bootstrap_{a.year}.csv"), index=False)
    print("written", out)


if __name__ == "__main__":
    main()
