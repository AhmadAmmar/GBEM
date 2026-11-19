"""Is 2 km the right block size? Spatial autocorrelation range of SAP and of the model's residuals, and how far test
homes are from the nearest training home under each validation design.

    python residual_range.py --area belfast|london [--tag <model run tag>] [--featureset eo_morph] [--sample 20000]

Block cross-validation should hold out blocks at least as large as the range over which residuals stay correlated
(Roberts et al. 2017; Valavi et al. 2019), and the distances from test to training points should resemble those from
the places to be mapped to the nearest certificate (Milà et al. 2022; Linnenbrink et al. 2024, kNNDM).
1. Empirical semivariogram (binned, up to 10 km, 40 bins) of the SAP score and of the out-of-fold residual of the
   feature set (models/baseline.py, spatial CV), on a random sample of certificates; the range is read as the first
   lag where the semivariance reaches 95% of its plateau (mean of the last quarter of lags).
2. Nearest-neighbour distances: (a) prediction: every uncertified dwelling building (models/stock_predict.py) to its
   nearest certificate; (b) random 5-fold CV: each certificate to its nearest certificate in other folds; (c) block CV
   with 1, 2 and 5 km blocks: each certificate to the nearest certificate outside its block's fold. Reported as
   quantiles; the design whose distribution is closest to (a) (Wasserstein distance) is the one that matches the
   use of the map.
Outputs in data/<area>/model/results/: residual_range_<tag>.csv (variogram), nn_distances_<tag>.csv (quantiles and
Wasserstein distance per design), and figure data/<area>/model/figures/residual_range_<tag>.png
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.stats import wasserstein_distance
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "models"))
from safeio import keep
import baseline as B
from sklearn.model_selection import GroupKFold, KFold

TAG = {"london": "2024_s50k", "belfast": "2024"}


def variogram(xy, v, maxd=10000, bins=40, pairs=3_000_000, seed=0):
    """Binned semivariance from random pairs of points."""
    r = np.random.default_rng(seed)
    i, j = r.integers(0, len(v), pairs), r.integers(0, len(v), pairs)
    h = np.hypot(*(xy[i] - xy[j]).T)
    ok = (h > 0) & (h <= maxd)
    g = 0.5 * (v[i] - v[j]) ** 2
    edges = np.linspace(0, maxd, bins + 1)
    k = np.digitize(h[ok], edges) - 1
    out = pd.DataFrame({"k": k, "g": g[ok]}).groupby("k")["g"].agg(["mean", "size"]).reindex(range(bins))
    out["lag_m"] = (edges[:-1] + edges[1:]) / 2
    return out.rename(columns={"mean": "semivariance", "size": "pairs"}).reset_index(drop=True)


def range_of(vg):
    """First lag at which the semivariance reaches 95% of the plateau (mean of the last quarter)."""
    s = vg["semivariance"].to_numpy()
    sill = np.nanmean(s[-len(s) // 4:])
    hit = np.where(s >= 0.95 * sill)[0]
    return float(vg["lag_m"].iloc[hit[0]]) if len(hit) else np.nan, float(sill)


def nn_out_of_fold(xy, folds):
    """Distance from each point to the nearest point in the other folds."""
    d = np.full(len(xy), np.nan)
    for tr, te in folds:
        d[te] = cKDTree(xy[tr]).query(xy[te])[0]
    return d


def main():
    """Variograms and nearest-neighbour distance distributions for one area."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--tag"); ap.add_argument("--featureset", default="eo_morph")
    ap.add_argument("--sample", type=int, default=20000)
    a = ap.parse_args()
    tag = a.tag or TAG[a.area]
    res = B.DATA / a.area / "model/results"
    o = pd.read_parquet(res / f"oof_{tag}.parquet").dropna(subset=["x", "y", "actual_sap", f"sap_lgbm_{a.featureset}"])
    o = o.sample(min(a.sample, len(o)), random_state=0)
    xy = o[["x", "y"]].to_numpy(float)
    rows, ranges = [], {}
    for name, v in [("SAP", o["actual_sap"].to_numpy(float)),
                    (f"residual {a.featureset}", (o[f"sap_lgbm_{a.featureset}"] - o["actual_sap"]).to_numpy(float))]:
        vg = variogram(xy, v); vg["variable"] = name; rows.append(vg)
        ranges[name] = range_of(vg)
    vgs = pd.concat(rows)
    vgs.round(4).to_csv(keep(res / f"residual_range_{tag}.csv"), index=False)
    # distances: prediction targets vs CV designs
    stock = B.DATA / a.area / "model/stock/stock_pred_2024.parquet"
    dist = {}
    if stock.exists():
        import geopandas as gpd
        s = pd.read_parquet(stock, columns=["fp_id", "certified"])
        fp = gpd.read_file(B.DATA / a.area / "model/stock/dwelling_fp.gpkg", columns=["fp_id"])
        fp = fp[fp["fp_id"].isin(s.loc[~s["certified"].astype(bool), "fp_id"])]
        pts = fp.geometry.representative_point()
        txy = np.c_[pts.x, pts.y]
        txy = txy[np.random.default_rng(0).choice(len(txy), min(len(txy), 50000), replace=False)]
        dist["prediction (uncertified buildings)"] = cKDTree(xy).query(txy)[0]
    dist["random 5-fold"] = nn_out_of_fold(xy, list(KFold(5, shuffle=True, random_state=0).split(xy)))
    for km in (1, 2, 5):
        b = (np.floor(xy[:, 0] / (km * 1000)).astype(int).astype(str) + "_" + np.floor(xy[:, 1] / (km * 1000)).astype(int).astype(str))
        dist[f"block {km} km"] = nn_out_of_fold(xy, list(GroupKFold(5).split(xy, groups=b)))
    ref = dist.get("prediction (uncertified buildings)")
    q = []
    for k, v in dist.items():
        q.append({"design": k, "n": len(v), **{f"p{p}": np.nanpercentile(v, p) for p in (10, 25, 50, 75, 90)},
                  "wasserstein_to_prediction": wasserstein_distance(v, ref) if ref is not None else np.nan})
    q = pd.DataFrame(q)
    for k, (r, sill) in ranges.items():
        q[f"range_m {k}"] = r
    q.round(1).to_csv(keep(res / f"nn_distances_{tag}.csv"), index=False)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
    for name, g in vgs.groupby("variable"):
        ax[0].plot(g["lag_m"] / 1000, g["semivariance"], marker=".", label=f"{name} (range {ranges[name][0] / 1000:.1f} km)")
    ax[0].axvline(2, ls="--", c="grey"); ax[0].set_xlabel("lag (km)"); ax[0].set_ylabel("semivariance (SAP points$^2$)")
    ax[0].set_title("Spatial autocorrelation"); ax[0].legend(fontsize=8)
    for k, v in dist.items():
        ax[1].hist(np.clip(v, 0, 3000), bins=60, histtype="step", density=True, label=k)
    ax[1].set_xlabel("distance to nearest training certificate (m, capped at 3 km)"); ax[1].set_title("Prediction vs validation distances")
    ax[1].legend(fontsize=8)
    figs = B.DATA / a.area / "model/figures"; figs.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(); fig.savefig(keep(figs / f"residual_range_{tag}.png"), dpi=150)
    print(q.round(1).to_string(index=False))


if __name__ == "__main__":
    main()
