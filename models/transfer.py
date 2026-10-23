"""Transferability: does a model trained in one city, or in earlier years, work elsewhere or later?

    python transfer.py [--year 2024] [--sample 50000]

Core feature set: the columns present in both areas in the groups available everywhere (Sentinel-2, Sentinel-1,
Landsat and MODIS thermal, ERA5, VIIRS, GHSL, land cover, terrain, footprint morphology, streets), with and without
LiDAR (whose vintage differs: Belfast 2006-2014, London up to 2022). Census context (Northern Ireland only), place and
source identifiers and certificate attributes are left out.
Experiments (LightGBM, settings of baseline.py):
  spatial    train London (random sample of --sample certificates of --year) -> predict all Belfast certificates of
             --year, and train Belfast -> predict the London sample; compared with within-area spatial 5-fold CV on the
             same feature set (2 km blocks)
  temporal   per area: train on 2020-2022 (London: --sample per year) -> predict 2024 and 2025; and train 2020-2023 ->
             predict 2025; compared with the within-year spatial CV of the test year
Output: data/model_transfer/transfer_<year>.csv (one row per experiment, feature set and target)
"""
import argparse, pathlib, sys, time
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_absolute_error, r2_score
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import baseline as B
from safeio import keep                      # existing outputs are archived, never overwritten

OUT = B.DATA / "model_transfer"
CORE = ["sentinel2", "sentinel1", "thermal_landsat", "thermal_modis", "thermal_multiyear", "climate", "night_lights",
        "built_volume_ghsl", "landcover", "terrain", "morphology", "streets"]
SETS = {"core": CORE, "core_lidar": CORE + ["lidar"],
        # does physics-informed geometry travel between cities better than spectra? (--sets spectral form_physics core_phys)
        "spectral": ["sentinel2", "sentinel1", "thermal_landsat", "thermal_modis", "thermal_multiyear", "night_lights"],
        "form_physics": ["morphology", "streets", "lidar", "physics"],
        "core_phys": CORE + ["lidar", "physics"]}


def load(area, years, sample, seed=42):
    d, dd = B.load(area, years)
    if sample:
        d = d.groupby("year", group_keys=False).apply(lambda g: g.sample(n=min(sample, len(g)), random_state=seed)).reset_index(drop=True)
    return d, dd


def common_columns(dds, groups, frames):
    cols = None
    for dd, d in zip(dds, frames):
        c = {x for x in dd.loc[dd["group"].isin(groups), "column"] if x in d.columns and x not in B.NOT_FEATURES}
        cols = c if cols is None else cols & c
    return sorted(cols)


def matrix(d, cols, cats=None):
    X = d.reindex(columns=cols).copy()
    for c in X.columns:
        if X[c].dtype == object or str(X[c].dtype).startswith(("string", "category", "bool")):
            num = pd.to_numeric(X[c].astype("string"), errors="coerce")
            if num.notna().sum() >= 0.9 * X[c].notna().sum() > 0:
                X[c] = num.astype("float32")
            else:
                X[c] = pd.Categorical(X[c].astype("string"), categories=(cats or {}).get(c))
        else:
            X[c] = X[c].astype("float32")
    return X


def fit_predict(Xtr, ytr, sap_tr, Xte):
    ycode = np.searchsorted(B.BANDS, ytr)
    clf = lgb.LGBMClassifier(class_weight="balanced", **B.LGBM).fit(Xtr, ycode)
    pr = np.zeros((len(Xte), len(B.BANDS))); pr[:, clf.classes_] = clf.predict_proba(Xte)
    ok = ~np.isnan(sap_tr)
    reg = lgb.LGBMRegressor(**B.LGBM).fit(Xtr[ok], sap_tr[ok])
    return np.array(B.BANDS)[pr.argmax(1)], reg.predict(Xte)


def score(y, pred, sap, psap):
    ok = ~np.isnan(sap)
    return {**B.cls_metrics(y, pred), "sap_mae": mean_absolute_error(sap[ok], psap[ok]), "sap_r2": r2_score(sap[ok], psap[ok]),
            "mean_sap_actual": float(np.nanmean(sap)), "mean_sap_pred": float(np.mean(psap))}


def spatial_cv(d, X, folds=5, km=2.0):
    blocks = (np.floor(d["x"] / (km * 1000)).astype(int).astype(str) + "_" + np.floor(d["y"] / (km * 1000)).astype(int).astype(str))
    y, sap = d["label_rating"].to_numpy(), pd.to_numeric(d["label_sap"], errors="coerce").to_numpy("float64")
    pred, psap = np.empty(len(d), dtype=object), np.full(len(d), np.nan)
    for tr, te in GroupKFold(n_splits=folds).split(X, groups=blocks):
        pred[te], psap[te] = fit_predict(X.iloc[tr], y[tr], sap[tr], X.iloc[te])
    return score(y, pred.astype(str), sap, psap)


def run(name, train, test, cols, rows, fs):
    t0 = time.time()
    Xtr = matrix(train, cols)
    cats = {c: Xtr[c].cat.categories for c in Xtr.columns if str(Xtr[c].dtype) == "category"}
    Xte = matrix(test, cols, cats)
    pred, psap = fit_predict(Xtr, train["label_rating"].to_numpy(), pd.to_numeric(train["label_sap"], errors="coerce").to_numpy("float64"), Xte)
    r = {"experiment": name, "featureset": fs, "n_features": len(cols), "n_train": len(train), "n_test": len(test),
         **score(test["label_rating"].to_numpy(), pred, pd.to_numeric(test["label_sap"], errors="coerce").to_numpy("float64"), psap),
         "seconds": round(time.time() - t0)}
    rows.append(r)
    print(f"  {name:45s} {fs:10s} acc {r['accuracy']:.3f} QWK {r['qwk']:.3f} SAP MAE {r['sap_mae']:.2f} "
          f"(mean SAP {r['mean_sap_actual']:.1f} -> {r['mean_sap_pred']:.1f})", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2024); ap.add_argument("--sample", type=int, default=50000)
    ap.add_argument("--sets", nargs="+", default=["core", "core_lidar"]); ap.add_argument("--no-temporal", action="store_true")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    sets = {k: SETS[k] for k in a.sets}
    name = f"transfer_{a.year}{'_' + a.tag if a.tag else ''}.csv"
    lon, lon_dd = load("london", [a.year], a.sample)
    bel, bel_dd = load("belfast", [a.year], None)
    for fs, groups in sets.items():
        cols = common_columns([lon_dd, bel_dd], groups, [lon, bel])
        print(f"{fs}: {len(cols)} common features", flush=True)
        rows.append({"experiment": f"within London {a.year} (spatial 5-fold CV)", "featureset": fs, "n_features": len(cols),
                     "n_train": len(lon), "n_test": len(lon), **spatial_cv(lon, matrix(lon, cols))})
        rows.append({"experiment": f"within Belfast {a.year} (spatial 5-fold CV)", "featureset": fs, "n_features": len(cols),
                     "n_train": len(bel), "n_test": len(bel), **spatial_cv(bel, matrix(bel, cols))})
        for r in rows[-2:]:
            print(f"  {r['experiment']:45s} {fs:10s} acc {r['accuracy']:.3f} QWK {r['qwk']:.3f} SAP MAE {r['sap_mae']:.2f}", flush=True)
        run(f"London -> Belfast {a.year}", lon, bel, cols, rows, fs)
        run(f"Belfast -> London {a.year}", bel, lon, cols, rows, fs)
    pd.DataFrame(rows).round(4).to_csv(keep(OUT / name), index=False)
    # temporal
    for area in (() if a.no_temporal else ("belfast", "london")):
        dd = None
        frames = {}
        for y in range(2020, 2026):
            frames[y], dd = load(area, [y], a.sample if area == "london" else None)
        for fs, groups in sets.items():
            cols = common_columns([dd] * 6, groups, list(frames.values()))
            tr = pd.concat([frames[y] for y in (2020, 2021, 2022)])
            for ty in (2024, 2025):
                run(f"{area}: 2020-22 -> {ty}", tr, frames[ty], cols, rows, fs)
            run(f"{area}: 2020-23 -> 2025", pd.concat([tr, frames[2023]]), frames[2025], cols, rows, fs)
            for ty in (2024, 2025):
                rows.append({"experiment": f"{area}: within {ty} (spatial 5-fold CV)", "featureset": fs, "n_features": len(cols),
                             "n_train": len(frames[ty]), "n_test": len(frames[ty]), **spatial_cv(frames[ty], matrix(frames[ty], cols))})
                r = rows[-1]
                print(f"  {r['experiment']:45s} {fs:10s} acc {r['accuracy']:.3f} QWK {r['qwk']:.3f} SAP MAE {r['sap_mae']:.2f}", flush=True)
        pd.DataFrame(rows).round(4).to_csv(keep(OUT / name), index=False)   # saved as it goes
    print("written", OUT / name)


if __name__ == "__main__":
    main()
