"""Baseline models for EPC band and SAP score, with spatially grouped cross-validation and feature-group comparisons.

    python baseline.py --area belfast --years 2024 [--models lgbm rf] [--featuresets eo eo_morph eo_morph_ctx all]
                       [--folds 5] [--block-km 2] [--tag <name>] [--sample <n>]

Data: data/<area>/model/dataset_<year>.parquet (code/epc/assemble.py), with the coordinates of each certificate. Within
the selected years one certificate per property and year is used (the latest of that year).

Validation:
  spatial   5-fold cross-validation with folds made of square blocks of --block-km (default 2 km): every certificate is
            predicted by a model trained only on other areas (out-of-fold). All certificates of a building or property
            fall in the same block, so none is in training and test.
  random    5-fold cross-validation with random folds, for comparison only (the design common in the literature).
Feature sets (groups from data/<area>/model/data_dictionary.csv):
  eo            satellite and climate: Sentinel-2, Sentinel-1, thermal (single- and multi-year), climate, night lights,
                GHSL, land cover, terrain
  eo_morph      + footprint morphology, dwellings per footprint, streets, LiDAR (where available)
  eo_morph_ctx  + Census ward context (Belfast)
  all           + attributes recorded on the certificate (property type, built form, floor area, age band, ...)
Models: LightGBM (gradient boosting; handles missing values) and random forest (300 trees). Targets: the A-G band
(classification) and, for LightGBM, the SAP score (regression; the predicted score is also turned into a band).
Metrics: accuracy, balanced accuracy, macro-F1, quadratic weighted kappa (ordinal agreement), share within one band;
MAE and R2 for the SAP score.
Output, data/<area>/model/results/:
  baseline_<tag>.csv           metrics per model, feature set, validation and target
  oof_<tag>.parquet            out-of-fold predictions per certificate (spatial validation), for maps and dashboards
  importance_<tag>.csv         LightGBM gain importance per feature (spatial validation, mean over folds)
"""
import argparse, os, time, pathlib
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold, KFold
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, f1_score, cohen_kappa_score,
                             mean_absolute_error, r2_score)
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

PHD = pathlib.Path(__file__).resolve().parents[2]
DATA = PHD / "data"
BANDS = list("ABCDEFG")
SAP_BANDS = [(92, "A"), (81, "B"), (69, "C"), (55, "D"), (39, "E"), (21, "F"), (-999, "G")]   # SAP score -> band
SETS = {"eo": ["sentinel2", "sentinel1", "thermal_landsat", "thermal_modis", "thermal_multiyear", "climate",
               "night_lights", "built_volume_ghsl", "landcover", "terrain"]}
SETS["eo_morph_nolidar"] = SETS["eo"] + ["morphology", "streets"]           # to isolate what LiDAR adds
SETS["eo_morph"] = SETS["eo"] + ["morphology", "streets", "lidar"]
SETS["eo_morph_floor"] = SETS["eo_morph"] + ["floor_position"]                # + where a flat sits in its building
SETS["eo_morph_fps"] = SETS["eo_morph"] + ["sentinel_fpstats"]                # + footprint min / max / SD (fp_stats.py)
SETS["eo_morph_phys"] = SETS["eo_morph"] + ["physics"]                        # + envelope geometry for heat loss (physics.py)
SETS["eo_morph_floor_phys"] = SETS["eo_morph_floor"] + ["physics"]
SETS["embed"] = ["embedding"]                                                  # pretrained embeddings alone (batch b7)
SETS["eo_embed"] = SETS["eo"] + ["embedding"]
SETS["eo_morph_embed"] = SETS["eo_morph"] + ["embedding"]
SETS["eo_morph_ctx"] = SETS["eo_morph"] + ["census_context"]
SETS["all"] = SETS["eo_morph_ctx"] + ["certificate_attributes", "floor_position"]
# identifiers of a place or a data source rather than properties of the building: they would let a model learn locations
NOT_FEATURES = {"census_ward_code", "lidar_survey", "lidar_survey_year", "morph_source", "morph_src_dataset"}
# LightGBM settings shared by the classifier and the SAP regressor: 30% of the features per tree and 63 histogram bins
# keep fits fast with ~700 mostly correlated satellite features
LGBM = dict(n_estimators=300, learning_rate=0.08, num_leaves=31, min_child_samples=20, subsample=0.8, subsample_freq=1,
            colsample_bytree=0.3, max_bin=63, force_col_wise=True, n_jobs=os.cpu_count(), verbose=-1, random_state=42)


def sap_to_band(s):
    return np.array([next(b for lo, b in SAP_BANDS if v >= lo) for v in s])


def cls_metrics(y, p):
    yi, pi = np.searchsorted(BANDS, y), np.searchsorted(BANDS, p)
    return {"accuracy": accuracy_score(y, p), "balanced_accuracy": balanced_accuracy_score(y, p),
            "macro_f1": f1_score(y, p, average="macro"), "qwk": cohen_kappa_score(yi, pi, weights="quadratic"),
            "within_one_band": float(np.mean(np.abs(yi - pi) <= 1))}


def load(area, years):
    dd = pd.read_csv(DATA / area / "model" / "data_dictionary.csv")
    frames = [pd.read_parquet(DATA / area / "model" / f"dataset_{y}.parquet") for y in years]
    d = pd.concat(frames, ignore_index=True)
    xy = pd.read_parquet(DATA / area / "epc" / "certificates_linked.parquet", columns=["cert_id", "x", "y"])
    xy["cert_id"] = xy["cert_id"].astype(str)
    d = d.merge(xy.drop_duplicates("cert_id").rename(columns={"cert_id": "id_cert"}), on="id_cert", how="left")
    d = d.sort_values("inspection_date").drop_duplicates(["id_uprn", "year"], keep="last")   # one per property and year
    d = d[d["label_rating"].isin(BANDS)].reset_index(drop=True)
    d = floor_features(d)
    dd = pd.concat([dd, pd.DataFrame({"column": ["fl_pos", "fl_num", "fl_storeys", "fl_rel"], "group": "floor_position"})])
    return d, dd


def floor_features(d):
    """Where a dwelling sits in its building (the satellite and footprint features are the same for every flat of a
    building, but heat loss through the ground floor and the roof differs by floor):
      fl_pos      house | ground | middle | top   (flats and maisonettes; from the floor level and top-storey flag)
      fl_num      floor number (0 = ground), where the certificate gives a number
      fl_storeys  storeys of the building: footprint data, else LiDAR 90th percentile height / 3 m
      fl_rel      relative height in the building: 0 ground ... 1 top
    The floor comes from the certificate; for homes without one it would come from the address (e.g. "Flat 5, 2nd
    floor") or be unknown, so this set measures what knowing the floor is worth."""
    pt = d.get("epc_property_type", pd.Series(index=d.index, dtype=object)).astype("string").str.lower()
    lv = d.get("epc_floor_level", pd.Series(index=d.index, dtype=object)).astype("string").str.strip().str.lower().fillna("")
    top = d.get("epc_flat_top_storey", pd.Series(index=d.index, dtype=object)).astype("string").str.upper().fillna("")
    flat = pt.isin(["flat", "maisonette"]).fillna(False)
    num = pd.to_numeric(lv.str.extract(r"^(-?\d+)")[0], errors="coerce")
    num = num.where(~lv.str.contains("ground|basement"), 0)
    ground = num.eq(0) | lv.str.contains("ground|basement")
    is_top = top.eq("Y") | lv.str.contains("top")
    middle = lv.str.contains("mid") | num.gt(0)
    b = lambda s: s.fillna(False).to_numpy(bool)               # nullable booleans (missing = False)
    flat, is_top, ground, middle = b(flat), b(is_top), b(ground), b(middle)
    d["fl_pos"] = pd.Series(np.select([~flat, flat & is_top, flat & ground, flat & middle], ["house", "top", "ground", "middle"],
                                      "unknown"), index=d.index).where(pt.notna())
    d["fl_num"] = num.where(flat)
    storeys = pd.to_numeric(d.get("morph_num_floors"), errors="coerce")
    if "lidar_height_p90_m" in d:
        storeys = storeys.fillna((pd.to_numeric(d["lidar_height_p90_m"], errors="coerce") / 3).round().clip(lower=1))
    d["fl_storeys"] = storeys
    rel = d["fl_num"] / (storeys - 1).clip(lower=1)
    rel = rel.where(~(flat & is_top), 1.0).where(~(flat & ground), 0.0)
    d["fl_rel"] = rel.clip(0, 1).where(flat)
    return d


def features(d, dd, groups):
    cols = [c for c in dd.loc[dd["group"].isin(groups), "column"] if c in d.columns and c not in NOT_FEATURES]
    X = d[cols].copy()
    for c in X.columns:
        if X[c].dtype == object or str(X[c].dtype).startswith(("string", "category", "bool")):
            num = pd.to_numeric(X[c].astype("string"), errors="coerce")
            if num.notna().sum() >= 0.9 * X[c].notna().sum() > 0:
                X[c] = num.astype("float32")         # numbers stored as text (floor area, rooms, floor level)
            else:
                X[c] = X[c].astype("category")
        else:
            X[c] = X[c].astype("float32")
    return X


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--years", nargs="+", type=int, required=True)
    ap.add_argument("--models", nargs="+", default=["lgbm", "rf"]); ap.add_argument("--featuresets", nargs="+", default=list(SETS))
    ap.add_argument("--folds", type=int, default=5); ap.add_argument("--block-km", type=float, default=2.0)
    ap.add_argument("--tag"); ap.add_argument("--rf-max-rows", type=int, default=60000)
    ap.add_argument("--sample", type=int, help="random sample of this many certificates (seed 42), for large areas")
    a = ap.parse_args()
    tag = a.tag or f"{'-'.join(map(str, a.years))}" + (f"_s{a.sample // 1000}k" if a.sample else "")
    d, dd = load(a.area, a.years)
    if a.sample and a.sample < len(d):
        d = d.sample(n=a.sample, random_state=42).reset_index(drop=True)
    blocks = (np.floor(d["x"] / (a.block_km * 1000)).astype(int).astype(str) + "_" +
              np.floor(d["y"] / (a.block_km * 1000)).astype(int).astype(str))
    splits = {"spatial": list(GroupKFold(n_splits=a.folds).split(d, groups=blocks)),
              "random": list(KFold(n_splits=a.folds, shuffle=True, random_state=42).split(d))}
    y = d["label_rating"].to_numpy(); ycode = np.searchsorted(BANDS, y)
    sap = pd.to_numeric(d["label_sap"], errors="coerce").to_numpy()
    print(f"{a.area} {a.years}: {len(d):,} certificates, {blocks.nunique()} blocks of {a.block_km} km; bands",
          pd.Series(y).value_counts().sort_index().to_dict(), flush=True)
    rows, oof, imp = [], pd.DataFrame({"id_cert": d["id_cert"], "id_fp": d["id_fp"], "x": d["x"], "y": d["y"], "year": d["year"],
                                       "fl_pos": d["fl_pos"], "actual": y, "actual_sap": sap}), []
    for fs in a.featuresets:
        X = features(d, dd, SETS[fs])
        if X.shape[1] == 0:
            continue
        for val, sp in splits.items():
            for m in a.models:
                if m == "rf" and len(d) > a.rf_max_rows:
                    continue                                   # random forest on very large sets: too slow, skipped
                t0 = time.time()
                pred = np.empty(len(d), dtype=object); proba = np.zeros((len(d), len(BANDS)))
                pred_sap = np.full(len(d), np.nan); gains = np.zeros(X.shape[1])
                for tr, te in sp:
                    if m == "lgbm":
                        clf = lgb.LGBMClassifier(class_weight="balanced", **LGBM)
                        clf.fit(X.iloc[tr], ycode[tr])
                        pr = np.zeros((len(te), len(BANDS))); pr[:, clf.classes_] = clf.predict_proba(X.iloc[te])
                        proba[te] = pr; pred[te] = np.array(BANDS)[pr.argmax(1)]
                        gains += clf.booster_.feature_importance("gain")
                        ok = ~np.isnan(sap[tr])
                        reg = lgb.LGBMRegressor(**LGBM)
                        reg.fit(X.iloc[tr][ok], sap[tr][ok]); pred_sap[te] = reg.predict(X.iloc[te])
                    else:
                        Xn = X.copy()
                        for c in Xn.columns:
                            if str(Xn[c].dtype) == "category":
                                Xn[c] = Xn[c].cat.codes
                        clf = RandomForestClassifier(n_estimators=300, n_jobs=os.cpu_count(), random_state=42, min_samples_leaf=2,
                                                     class_weight="balanced_subsample")
                        clf.fit(Xn.iloc[tr], y[tr]); pred[te] = clf.predict(Xn.iloc[te])
                r = {"area": a.area, "years": "-".join(map(str, a.years)), "n": len(d), "featureset": fs, "n_features": X.shape[1],
                     "validation": val, "model": m, "target": "band", **cls_metrics(y, pred.astype(str)), "seconds": round(time.time() - t0)}
                rows.append(r)
                if m == "lgbm":
                    ok = ~np.isnan(sap)
                    rows.append({**{k: r[k] for k in ("area", "years", "n", "featureset", "n_features", "validation")},
                                 "model": "lgbm", "target": "sap", "mae": mean_absolute_error(sap[ok], pred_sap[ok]),
                                 "r2": r2_score(sap[ok], pred_sap[ok]),
                                 **{f"band_from_sap_{k}": v for k, v in cls_metrics(y[ok], sap_to_band(pred_sap[ok])).items()}})
                if val == "spatial":
                    oof[f"pred_{m}_{fs}"] = pred.astype(str)
                    if m == "lgbm":
                        oof[f"conf_{m}_{fs}"] = proba.max(1)
                        oof[f"sap_{m}_{fs}"] = pred_sap
                        imp.append(pd.DataFrame({"featureset": fs, "feature": X.columns, "gain": gains / len(sp)}))
                print(f"  {fs:13s} {val:8s} {m:5s} acc {r['accuracy']:.3f} macroF1 {r['macro_f1']:.3f} "
                      f"QWK {r['qwk']:.3f} within1 {r['within_one_band']:.3f} ({r['seconds']} s)", flush=True)
    out = DATA / a.area / "model" / "results"; out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).round(4).to_csv(keep(out / f"baseline_{tag}.csv"), index=False)
    oof.to_parquet(keep(out / f"oof_{tag}.parquet"), index=False)
    if imp:
        pd.concat(imp).sort_values(["featureset", "gain"], ascending=[True, False]).to_csv(keep(out / f"importance_{tag}.csv"), index=False)
    groups(oof, a.area).round(4).to_csv(keep(out / f"groups_{tag}.csv"), index=False)
    print("written", out)


def groups(oof, area):
    """Spatial out-of-fold results (LightGBM) by floor position, and at building level: for footprints with several
    certificates (blocks of flats, subdivided houses) the mean predicted SAP against the mean actual SAP."""
    rows = []
    for c in [c for c in oof.columns if c.startswith("pred_lgbm_")]:
        fs = c[len("pred_lgbm_"):]
        s = oof[f"sap_lgbm_{fs}"]
        for pos, g in oof.groupby("fl_pos"):
            ok = g["actual_sap"].notna()
            rows.append({"area": area, "featureset": fs, "level": "dwelling", "group": f"floor: {pos}", "n": len(g),
                         **cls_metrics(g["actual"].to_numpy(), g[c].to_numpy()),
                         "sap_mae": mean_absolute_error(g.loc[ok, "actual_sap"], s[g.index][ok])})
        b = oof.assign(p=s).groupby("id_fp").agg(n=("actual_sap", "size"), a=("actual_sap", "mean"), p=("p", "mean"),
                                                 sd=("actual_sap", "std"))
        for lab, sel in (("buildings with 1 certificate", b["n"] == 1), ("buildings with 2+ certificates", b["n"] >= 2),
                         ("buildings with 5+ certificates", b["n"] >= 5)):
            g = b[sel & b["a"].notna()]
            if len(g) >= 20:
                rows.append({"area": area, "featureset": fs, "level": "building", "group": lab, "n": len(g),
                             "sap_mae": mean_absolute_error(g["a"], g["p"]), "sap_r2": r2_score(g["a"], g["p"]),
                             "within_building_sd": g["sd"].mean()})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    main()
