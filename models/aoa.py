"""Area of applicability: where can a model's predictions be trusted? (Meyer and Pebesma 2021, dissimilarity index)

    python aoa.py [--year 2024] [--sample 50000] [--top 60]

For a model trained on data X_train, the dissimilarity index of a new point is its distance to the nearest training
point in the space of standardised predictors weighted by their importance, divided by the mean distance between
training points: DI = d_min / mean(d_train). The threshold is the upper whisker (Q3 + 1.5 IQR) of the DI of the
training points measured against the other cross-validation folds (2 km blocks). Points above it lie outside the
area of applicability (AOA): the model has not seen similar conditions.
Features: the --top numeric predictors of the core set (models/transfer.py, with LiDAR) by LightGBM gain on the
training area; missing values set to the training median.
Applied to:
  within    each area: test folds of spatial CV against their training folds - share outside, and SAP error inside
            vs outside (does DI flag larger errors?)
  transfer  London model -> Belfast certificates and Belfast model -> London sample: share outside, error inside
            vs outside
  stock     Belfast model -> all Belfast dwelling buildings (models/stock_predict.py features), share outside
Output: data/model_transfer/aoa_<year>.csv and aoa_<year>_points.parquet (DI per point and experiment)
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import GroupKFold
from sklearn.neighbors import NearestNeighbors
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import baseline as B
import transfer as T
from safeio import keep                      # existing outputs are archived, never overwritten


def blocks(d, km=2.0):
    return (np.floor(d["x"] / (km * 1000)).astype(int).astype(str) + "_" + np.floor(d["y"] / (km * 1000)).astype(int).astype(str)).to_numpy()


def numeric(X):
    return X[[c for c in X.columns if str(X[c].dtype) != "category"]]


class AOA:
    def __init__(self, Xtr, ytr, groups, top):
        X = numeric(Xtr)
        imp = lgb.LGBMRegressor(**B.LGBM).fit(X, ytr).booster_.feature_importance("gain")
        order = np.argsort(imp)[::-1][:top]
        self.cols = list(X.columns[order])
        w = imp[order] / imp[order].sum()
        self.med = X[self.cols].median()
        self.sd = X[self.cols].std().replace(0, 1)
        self.w = w
        Z = self.z(X)
        self.nn = NearestNeighbors(n_neighbors=1).fit(Z)
        rng = np.random.default_rng(0)
        s = Z[rng.choice(len(Z), min(3000, len(Z)), replace=False)]
        dd = np.sqrt(((s[:, None, :] - s[None, :, :]) ** 2).sum(-1))
        self.mean_d = dd[np.triu_indices(len(s), 1)].mean()
        # training DI against the other folds -> threshold
        di = np.full(len(Z), np.nan)
        for tr, te in GroupKFold(n_splits=5).split(Z, groups=groups):
            di[te] = NearestNeighbors(n_neighbors=1).fit(Z[tr]).kneighbors(Z[te])[0][:, 0] / self.mean_d
        q1, q3 = np.nanpercentile(di, [25, 75])
        self.threshold = q3 + 1.5 * (q3 - q1)
        self.train_di = di

    def z(self, X):
        Z = (X[self.cols].astype("float64").fillna(self.med) - self.med) / self.sd
        return Z.to_numpy() * self.w

    def di(self, X):
        return self.nn.kneighbors(self.z(numeric(X)))[0][:, 0] / self.mean_d


def err_split(di, thr, err, name, rows, extra):
    out = di > thr
    rows.append({"experiment": name, **extra, "points": len(di), "share_outside_aoa": out.mean(), "threshold": thr,
                 "di_median": np.median(di), "sap_mae_inside": np.nanmean(err[~out]) if (~out).any() else np.nan,
                 "sap_mae_outside": np.nanmean(err[out]) if out.any() else np.nan})
    r = rows[-1]
    print(f"  {name:40s} outside AOA {r['share_outside_aoa']:.1%}  MAE inside {r['sap_mae_inside']:.2f} outside {r['sap_mae_outside']:.2f}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2024); ap.add_argument("--sample", type=int, default=50000)
    ap.add_argument("--top", type=int, default=60)
    a = ap.parse_args()
    lon, lon_dd = T.load("london", [a.year], a.sample)
    bel, bel_dd = T.load("belfast", [a.year], None)
    cols = T.common_columns([lon_dd, bel_dd], T.SETS["core_lidar"], [lon, bel])
    data = {"london": lon, "belfast": bel}
    X = {k: T.matrix(v, cols) for k, v in data.items()}
    sap = {k: pd.to_numeric(v["label_sap"], errors="coerce").to_numpy("float64") for k, v in data.items()}
    rows, pts = [], []
    for area in ("belfast", "london"):
        g = blocks(data[area])
        # within: spatial CV error vs DI
        di = np.full(len(g), np.nan); err = np.full(len(g), np.nan); thr = []
        for tr, te in GroupKFold(n_splits=5).split(X[area], groups=g):
            ok = ~np.isnan(sap[area][tr])
            m = AOA(X[area].iloc[tr][ok], sap[area][tr][ok], g[tr][ok], a.top)
            di[te] = m.di(X[area].iloc[te]); thr.append(m.threshold)
            reg = lgb.LGBMRegressor(**B.LGBM).fit(X[area].iloc[tr][ok], sap[area][tr][ok])
            err[te] = np.abs(reg.predict(X[area].iloc[te]) - sap[area][te])
        err_split(di, np.mean(thr), err, f"within {area} (spatial CV)", rows, {"model_area": area, "target_area": area})
        pts.append(pd.DataFrame({"experiment": f"within {area}", "id_cert": data[area]["id_cert"], "di": di, "abs_err": err}))
    for src, tgt in (("london", "belfast"), ("belfast", "london")):
        ok = ~np.isnan(sap[src])
        m = AOA(X[src][ok], sap[src][ok], blocks(data[src])[ok], a.top)
        reg = lgb.LGBMRegressor(**B.LGBM).fit(X[src][ok], sap[src][ok])
        di = m.di(X[tgt]); err = np.abs(reg.predict(X[tgt]) - sap[tgt])
        err_split(di, m.threshold, err, f"{src} model -> {tgt}", rows, {"model_area": src, "target_area": tgt})
        pts.append(pd.DataFrame({"experiment": f"{src} -> {tgt}", "id_cert": data[tgt]["id_cert"], "di": di, "abs_err": err}))
    # stock: Belfast model applied to all dwelling buildings
    sp = B.DATA / "belfast/gee_v2/features" / f"stock_{a.year}.parquet"
    if sp.exists():
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        import stock_predict as SP
        S = SP.building_table("belfast", a.year)
        XS = T.matrix(S, cols)
        ok = ~np.isnan(sap["belfast"])
        m = AOA(X["belfast"][ok], sap["belfast"][ok], blocks(bel)[ok], a.top)
        di = m.di(XS)
        rows.append({"experiment": "belfast model -> all dwelling buildings", "model_area": "belfast", "target_area": "belfast stock",
                     "points": len(di), "share_outside_aoa": float((di > m.threshold).mean()), "threshold": m.threshold, "di_median": float(np.median(di))})
        print(f"  belfast stock: outside AOA {rows[-1]['share_outside_aoa']:.1%} of {len(di):,} buildings", flush=True)
        pts.append(pd.DataFrame({"experiment": "belfast stock", "id_cert": S["id_fp"], "di": di, "abs_err": np.nan}))
    pd.DataFrame(rows).round(4).to_csv(keep(T.OUT / f"aoa_{a.year}.csv"), index=False)
    pd.concat(pts, ignore_index=True).to_parquet(keep(T.OUT / f"aoa_{a.year}_points.parquet"), index=False)
    print("written", T.OUT)


if __name__ == "__main__":
    main()
