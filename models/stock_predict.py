"""Predicted energy rating for every dwelling building, not only the certified ones (whole-stock estimates).

    python stock_predict.py --area belfast --year 2024 [--featureset eo_morph] [--skip-extract]

1. Dwelling buildings: footprints with at least one address point (dwellings_fp.n_uprn >= 1; address points include
   some non-domestic addresses). Written to data/<area>/model/stock/dwelling_fp.gpkg.
2. Satellite features for these footprints: gee/extract.py --buildings (same variables as for certificates; the point
   is the footprint's representative point). Output gee_v2/features/stock_<year>.parquet.
3. Morphology, addresses per footprint, LiDAR (+ derived), streetscape added as in epc/assemble.py.
4. LightGBM (band classifier and SAP regressor, settings of baseline.py) trained on all certificates of the year with
   the feature set, then applied to every dwelling building. A building with several dwellings gets one prediction,
   weighted by its addresses in the summaries.
Outputs in data/<area>/model/stock/:
  stock_pred_<year>.parquet   fp_id, n_uprn, certified (has a certificate of the year), pred_sap, pred_band,
                              p_FG (probability of band F or G), confidence
  stock_units_<year>.csv      per 250 m cell and neighbourhood: dwellings, predicted mean SAP and F-G share for all
                              dwellings, and for the certified ones only (how unrepresentative certificates are)
Predictions carry the model error (spatial CV of baseline.py); use them for areas, not for individual homes.
"""
import argparse, pathlib, subprocess, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import lightgbm as lgb
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "epc"))
import baseline as B
from assemble import lidar_derived
from safeio import keep                      # existing outputs are archived, never overwritten

CODE = pathlib.Path(__file__).resolve().parents[1]


def building_table(area, year):
    e = B.DATA / area / "epc"
    f = pd.read_parquet(B.DATA / area / "gee_v2/features" / f"stock_{year}.parquet")
    f = f.drop(columns=[c for c in ("fp_id", "UPRN", "link_method", "year") if c in f]).rename(columns={"rec_id": "id_fp"})
    f["id_fp"] = f["id_fp"].astype(str)
    morph = pd.read_parquet(e / "morphology.parquet").merge(pd.read_parquet(e / "dwellings_fp.parquet"), on="fp_id", how="left")
    morph = morph.rename(columns={c: f"morph_{c}" for c in morph.columns if c != "fp_id"})
    morph["fp_id"] = morph["fp_id"].astype(str)
    d = f.merge(morph, left_on="id_fp", right_on="fp_id", how="left").drop(columns=["fp_id"])
    for name in ("lidar_fp.parquet", "streetscape_fp.parquet"):
        if (e / name).exists():
            t = pd.read_parquet(e / name); t["fp_id"] = t["fp_id"].astype(str)
            d = d.merge(t, left_on="id_fp", right_on="fp_id", how="left").drop(columns=["fp_id"])
    if "lidar_valid_share" in d:
        d = lidar_derived(d)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--featureset", default="eo_morph"); ap.add_argument("--skip-extract", action="store_true")
    a = ap.parse_args()
    out = B.DATA / a.area / "model/stock"; out.mkdir(parents=True, exist_ok=True)
    e = B.DATA / a.area / "epc"
    gpkg = out / "dwelling_fp.gpkg"
    if not a.skip_extract:
        fp = gpd.read_parquet(e / "footprints.parquet", columns=["fp_id", "geometry"])
        dw = pd.read_parquet(e / "dwellings_fp.parquet", columns=["fp_id", "n_uprn"])
        fp = fp.merge(dw, on="fp_id", how="inner")
        fp = fp[fp["n_uprn"] >= 1]
        fp["fp_id"] = fp["fp_id"].astype(str)
        if gpkg.exists():
            keep(gpkg)                                            # archive the earlier file before writing a new one
        fp.to_file(gpkg, driver="GPKG")
        print(f"{a.area}: {len(fp):,} dwelling buildings ({int(fp['n_uprn'].sum()):,} addresses)", flush=True)
        subprocess.run([sys.executable, str(CODE / "gee/extract.py"), "--area", a.area, "--year", str(a.year),
                        "--buildings", str(gpkg), "--id", "fp_id", "--tag", "stock", "--no-csv"], check=True)
    # train on the certificates of the year
    d, dd = B.load(a.area, [a.year])
    X = B.features(d, dd, B.SETS[a.featureset])
    cols = list(X.columns)
    cats = {c: X[c].cat.categories for c in cols if str(X[c].dtype) == "category"}
    y = np.searchsorted(B.BANDS, d["label_rating"].to_numpy())
    sap = pd.to_numeric(d["label_sap"], errors="coerce").to_numpy("float64")
    clf = lgb.LGBMClassifier(class_weight="balanced", **B.LGBM).fit(X, y)
    ok = ~np.isnan(sap)
    reg = lgb.LGBMRegressor(**B.LGBM).fit(X[ok], sap[ok])
    # predict every dwelling building
    S = building_table(a.area, a.year)
    XS = S.reindex(columns=cols).copy()
    for c in cols:
        if c in cats:
            XS[c] = pd.Categorical(XS[c].astype("string"), categories=cats[c])
        else:
            XS[c] = pd.to_numeric(XS[c], errors="coerce").astype("float32")
    pr = np.zeros((len(XS), len(B.BANDS))); pr[:, clf.classes_] = clf.predict_proba(XS)
    certified = set(d["id_fp"].dropna().astype(str))
    res = pd.DataFrame({"fp_id": S["id_fp"], "n_uprn": pd.to_numeric(S["morph_n_uprn"], errors="coerce").fillna(1).clip(lower=1),
                        "certified": S["id_fp"].isin(certified), "pred_sap": reg.predict(XS),
                        "pred_band": np.array(B.BANDS)[pr.argmax(1)], "p_FG": pr[:, 5] + pr[:, 6], "confidence": pr.max(1)})
    res.to_parquet(keep(out / f"stock_pred_{a.year}.parquet"), index=False)
    # summaries: all dwellings vs certified only, weighted by addresses
    fp = gpd.read_parquet(e / "footprints.parquet", columns=["fp_id", "geometry"])
    fp["fp_id"] = fp["fp_id"].astype(str)
    c = shapely_centroids(fp)
    res = res.merge(c, on="fp_id", how="left")
    res["cell"] = (np.floor(res["x"] / 250).astype(int)).astype(str) + "_" + (np.floor(res["y"] / 250).astype(int)).astype(str)
    w = res["n_uprn"]
    rows = []
    for key in ("cell",):
        for k, g in res.groupby(key):
            gw, gc = g["n_uprn"], g[g["certified"]]
            rows.append({"unit": key, "id": k, "dwellings": gw.sum(), "certified_buildings": int(g["certified"].sum()),
                         "pred_sap_all": np.average(g["pred_sap"], weights=gw), "pred_FG_all": np.average(g["p_FG"], weights=gw),
                         "pred_sap_certified": np.average(gc["pred_sap"], weights=gc["n_uprn"]) if len(gc) else np.nan})
    u = pd.DataFrame(rows)
    u.round(3).to_csv(keep(out / f"stock_units_{a.year}.csv"), index=False)
    tot = {"dwellings": int(w.sum()), "buildings": len(res), "certified_buildings": int(res["certified"].sum()),
           "pred_sap_all": float(np.average(res["pred_sap"], weights=w)),
           "pred_sap_certified": float(np.average(res.loc[res["certified"], "pred_sap"], weights=res.loc[res["certified"], "n_uprn"])),
           "pred_FG_all": float(np.average(res["p_FG"], weights=w)),
           "pred_FG_certified": float(np.average(res.loc[res["certified"], "p_FG"], weights=res.loc[res["certified"], "n_uprn"]))}
    print({k: round(v, 3) if isinstance(v, float) else v for k, v in tot.items()})
    print("written", out)


def shapely_centroids(fp):
    c = fp.geometry.centroid
    return pd.DataFrame({"fp_id": fp["fp_id"], "x": c.x.to_numpy(), "y": c.y.to_numpy()})


if __name__ == "__main__":
    main()
