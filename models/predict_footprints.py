"""Predicted energy rating for chosen building footprints, for any year with satellite data (monitoring prototype).

    python predict_footprints.py --area london --fp-ids 123 456 [--years 2020 2021 2022 2023 2024 2025]
    python predict_footprints.py --area belfast --polygon area_of_interest.geojson [--years ...]

A user selects buildings, by footprint id or by drawing an area of interest (every dwelling footprint that intersects it
is taken). For each requested year, the satellite features of these footprints are extracted from that year's Earth
Engine composites (gee/extract.py --buildings), building form, LiDAR and street measures are added as for the whole-stock
estimates (models/stock_predict.py), and one model, trained once on the certificates of --model-year and cached, predicts
the SAP score, the band and the probability of band F or G. Using one fixed model means that a change between years
comes only from a change in what is observed (for example new or altered buildings, vegetation, surface temperature),
not from a change in the model.

Each prediction carries a dissimilarity index (DI, Meyer and Pebesma 2021: distance to the nearest training certificate
in standardised feature space, weighted by importance, over the mean distance between training certificates) and a flag
for predictions outside the area of applicability (DI above the threshold of models/aoa.py). Predictions are estimates for
screening areas; at dwelling level their error is that of the spatial cross-validation (Chapter 5 of the thesis).

Limits of this prototype: satellite years are those already exported (2020-2025; new years need an Earth Engine export,
or, for small areas, on-demand extraction through the Earth Engine API); footprints must be in the area's footprint
layer (new outlines need morphology and street measures computed with epc/morphology.py and epc/streetscape.py).

Output: data/<area>/model/deploy/predictions_<name>.csv (fp_id, year, pred_sap, pred_band, p_FG, di, outside_aoa) and,
the first time, the cached model lgbm_<featureset>_<model-year>.joblib with its feature list and training statistics.
"""
import argparse, hashlib, pathlib, subprocess, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import lightgbm as lgb
import joblib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import baseline as B
from stock_predict import building_table
from safeio import keep                      # existing outputs are archived, never overwritten

CODE = pathlib.Path(__file__).resolve().parents[1]


def model(area, year, featureset, sample, out):
    f = out / f"lgbm_{featureset}_{year}.joblib"
    if f.exists():
        return joblib.load(f)
    d, dd = B.load(area, [year])
    if sample and len(d) > sample:
        d = d.sample(n=sample, random_state=42).reset_index(drop=True)
    X = B.features(d, dd, B.SETS[featureset])
    cols = list(X.columns)
    cats = {c: X[c].cat.categories for c in cols if str(X[c].dtype) == "category"}
    y = np.searchsorted(B.BANDS, d["label_rating"].to_numpy())
    sap = pd.to_numeric(d["label_sap"], errors="coerce").to_numpy("float64")
    clf = lgb.LGBMClassifier(class_weight="balanced", **B.LGBM).fit(X, y)
    ok = ~np.isnan(sap)
    reg = lgb.LGBMRegressor(**B.LGBM).fit(X[ok], sap[ok])
    # area of applicability: standardised numeric predictors weighted by importance (top 60, as models/aoa.py)
    num = [c for c in cols if c not in cats]
    imp = pd.Series(reg.booster_.feature_importance("gain"), index=cols)[num].sort_values(ascending=False).head(60)
    T = X[imp.index].astype("float64")
    med, sd = T.median(), T.std().replace(0, 1)
    Z = ((T.fillna(med) - med) / sd * (imp / imp.sum())).to_numpy()
    from scipy.spatial.distance import pdist
    rng = np.random.default_rng(42)
    sub = Z[rng.choice(len(Z), size=min(3000, len(Z)), replace=False)]
    mean_d = float(pdist(sub).mean())                            # mean distance between training certificates
    thr = None
    a = B.DATA / "model_transfer" / f"aoa_{year}.csv"
    if a.exists():
        t = pd.read_csv(a)
        r = t[t["experiment"] == f"within {area} (spatial CV)"]
        thr = float(r["threshold"].iat[0]) if len(r) else None
    m = {"clf": clf, "reg": reg, "cols": cols, "cats": cats, "aoa_cols": list(imp.index), "med": med, "sd": sd,
         "w": (imp / imp.sum()), "Ztrain": Z, "mean_d": mean_d, "threshold": thr, "featureset": featureset, "year": year}
    joblib.dump(m, f)
    return m


def predict(m, S):
    XS = S.reindex(columns=m["cols"])
    for c in m["cols"]:
        XS[c] = pd.Categorical(XS[c].astype("string"), categories=m["cats"][c]) if c in m["cats"] else \
            pd.to_numeric(XS[c], errors="coerce").astype("float32")
    pr = np.zeros((len(XS), len(B.BANDS))); pr[:, m["clf"].classes_] = m["clf"].predict_proba(XS)
    T = S.reindex(columns=m["aoa_cols"]).apply(pd.to_numeric, errors="coerce").astype("float64")
    Z = ((T.fillna(m["med"]) - m["med"]) / m["sd"] * m["w"]).to_numpy()
    from scipy.spatial import cKDTree
    dmin = cKDTree(m["Ztrain"]).query(Z, k=1)[0]
    di = dmin / m["mean_d"]
    return pd.DataFrame({"pred_sap": m["reg"].predict(XS).round(1), "pred_band": np.array(B.BANDS)[pr.argmax(1)],
                         "p_FG": (pr[:, 5] + pr[:, 6]).round(3), "di": di.round(3),
                         "outside_aoa": (di > m["threshold"]) if m["threshold"] else np.nan})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--fp-ids", nargs="+"); ap.add_argument("--polygon")
    ap.add_argument("--years", nargs="+", type=int, default=[2020, 2021, 2022, 2023, 2024, 2025])
    ap.add_argument("--model-year", type=int, default=2024); ap.add_argument("--featureset", default="eo_morph")
    ap.add_argument("--sample", type=int, default=50000); ap.add_argument("--name", default=None)
    a = ap.parse_args()
    e = B.DATA / a.area / "epc"
    out = B.DATA / a.area / "model" / "deploy"; out.mkdir(parents=True, exist_ok=True)
    fp = gpd.read_parquet(e / "footprints.parquet", columns=["fp_id", "geometry"])
    fp["fp_id"] = fp["fp_id"].astype(str)
    if a.fp_ids:
        sel = fp[fp["fp_id"].isin(a.fp_ids)]
    elif a.polygon:
        aoi = gpd.read_file(a.polygon).to_crs(fp.crs)
        sel = fp[fp.intersects(aoi.union_all())]
    else:
        raise SystemExit("give --fp-ids or --polygon")
    if sel.empty:
        raise SystemExit("no footprints selected")
    name = a.name or hashlib.sha1(",".join(sorted(sel["fp_id"])).encode()).hexdigest()[:10]
    gpkg = out / f"selection_{name}.gpkg"
    sel.to_file(gpkg, driver="GPKG")
    print(f"{a.area}: {len(sel):,} footprints selected ({name}); training or loading the {a.model_year} model", flush=True)
    m = model(a.area, a.model_year, a.featureset, a.sample, out)
    rows = []
    for y in a.years:
        tag = f"pf_{name}"
        r = subprocess.run([sys.executable, str(CODE / "gee/extract.py"), "--area", a.area, "--year", str(y), "--buildings",
                            str(gpkg), "--id", "fp_id", "--tag", tag, "--no-csv"], capture_output=True, text=True)
        src = B.DATA / a.area / "gee_v2/features" / f"{tag}_{y}.parquet"
        if r.returncode or not src.exists():
            print(f"  {y}: no satellite features ({(r.stderr or '').strip().splitlines()[-1:] or 'no export'})"); continue
        S = building_table(a.area, y, need=m["cols"] + m["aoa_cols"] + ["morph_n_uprn"], src=src)
        p = predict(m, S)
        p.insert(0, "year", y); p.insert(0, "fp_id", S["id_fp"].values)
        rows.append(p)
        print(f"  {y}: mean predicted SAP {p['pred_sap'].mean():.1f}; outside AOA {np.nanmean(p['outside_aoa'].astype(float)):.0%}")
    if rows:
        res = pd.concat(rows, ignore_index=True)
        dest = out / f"predictions_{name}.csv"
        res.to_csv(keep(dest), index=False)
        print("written", dest)


if __name__ == "__main__":
    main()
