"""Are the HotSat-1 scenes of any use for EPC prediction? Location, coverage, correlation and added predictive value.

    python assess_hotsat.py

Scenes (data/belfast/hotsat/<scene>/; SatVu "visual" product: 16-bit values on an uncalibrated scale, not temperature):
  20230713T005702  south-west Belfast (Dunmurry/Finaghy/Lambeg), 00:57 UTC, summer night, 3.8 m
  20231008T005100  Southampton, 00:51 UTC, autumn night, 3.7 m
  20231125T143956  Mersey at Runcorn/Widnes, 14:39 UTC, winter afternoon, 5.9 m
Both the single-frame image (<scene>.tiff) and the "experimental stacked" image (<scene>_stacked.tiff) are assessed.
Certificates: Belfast, the NI register (data/belfast/epc/certificates_linked.parquet, latest certificate per UPRN);
England, the certificates with coordinates prepared for the pilot in March 2025 (<scene>.csv, latest per location).

Per certificate:
  hs_pt      mean of the 3 x 3 pixels around the address point (about 11 m for the night scenes)
  hs_anom    hs_pt minus the mean within 250 m (removes the arbitrary offset and gradients across the scene)
Results:
  Spearman correlation of hs_pt and hs_anom with the SAP score, overall and by property type
  added value: SAP predicted with spatial 5-fold cross-validation (500 m blocks, LightGBM) from basic attributes
  (property type, built form, age band, floor area) with and without the HotSat features; for Belfast also from all
  features of the modelling table (Sentinel, Landsat, morphology, LiDAR, Census) with and without HotSat
Output: data/hotsat_assessment/ (hotsat_summary.csv, hotsat_correlation.csv, hotsat_cv.csv, per-certificate samples)
"""
import json, pathlib, sys
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from scipy import ndimage, stats
import lightgbm as lgb
from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_absolute_error, r2_score
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

PHD = pathlib.Path(__file__).resolve().parents[2]
DATA = PHD / "data"
HS = DATA / "belfast" / "hotsat"
OUT = DATA / "hotsat_assessment"
SCENES = {"20230713T005702000": ("belfast", "south-west Belfast", "summer night"),
          "20231008T005100000": ("southampton", "Southampton", "autumn night"),
          "20231125T143956000": ("runcorn", "Runcorn/Widnes", "winter afternoon")}
BASIC = ["property_type", "built_form", "age_band", "floor_area"]
LGBM = dict(n_estimators=300, learning_rate=0.05, num_leaves=15, min_child_samples=20, subsample=0.8, subsample_freq=1,
            colsample_bytree=0.5, verbose=-1, random_state=42, n_jobs=4)


def load_raster(path):
    with rasterio.open(path) as r:
        a = r.read(1).astype("float64")
        nod = r.nodata if r.nodata is not None else 0
        a[a == nod] = np.nan
        return a, r.transform, r.crs.to_epsg()


def sample(a, t, x, y, nb_m=250):
    """hs_pt (3 x 3 mean) and hs_anom (minus the mean within nb_m) at points x, y (raster CRS)."""
    ok = np.isfinite(a)
    z = np.where(ok, a, 0.0)
    m3 = ndimage.uniform_filter(z, 3) / np.maximum(ndimage.uniform_filter(ok.astype(float), 3), 1e-9)
    k = int(round(2 * nb_m / t.a)) | 1
    mk = ndimage.uniform_filter(z, k) / np.maximum(ndimage.uniform_filter(ok.astype(float), k), 1e-9)
    col = np.floor((x - t.c) / t.a).astype(int); row = np.floor((y - t.f) / t.e).astype(int)
    inside = (row >= 1) & (row < a.shape[0] - 1) & (col >= 1) & (col < a.shape[1] - 1)
    pt, nb = np.full(len(x), np.nan), np.full(len(x), np.nan)
    r_, c_ = row[inside], col[inside]
    valid = ok[r_, c_]
    pt[np.flatnonzero(inside)[valid]] = m3[r_, c_][valid]
    nb[np.flatnonzero(inside)[valid]] = mk[r_, c_][valid]
    return pt, pt - nb


def england(scene):
    d = pd.read_csv(HS / f"{scene}_visual_30_hotsat1.csv", low_memory=False)
    d = d.sort_values("INSPECTION_DATE").drop_duplicates(["LATITUDE", "LONGITUDE"], keep="last")
    x, y = Transformer.from_crs(4326, 32630, always_xy=True).transform(d["LONGITUDE"].to_numpy(), d["LATITUDE"].to_numpy())
    return pd.DataFrame({"x": x, "y": y, "sap": pd.to_numeric(d["CURRENT_ENERGY_EFFICIENCY"], errors="coerce"),
                         "band": d["CURRENT_ENERGY_RATING"], "date": d["INSPECTION_DATE"],
                         "property_type": d["PROPERTY_TYPE"], "built_form": d["BUILT_FORM"],
                         "age_band": d["CONSTRUCTION_AGE_BAND"].astype(str).str.replace(r"^England and Wales:\s*", "", regex=True),
                         "floor_area": pd.to_numeric(d["TOTAL_FLOOR_AREA"], errors="coerce")})


def belfast():
    c = pd.read_parquet(DATA / "belfast/epc/certificates_linked.parquet",
                        columns=["cert_id", "UPRN", "x", "y", "inspection_date", "sap_score", "CURRENT_ENERGY_RATING",
                                 "PROPERTY_TYPE", "BUILT_FORM", "CONSTRUCTION_AGE_BAND", "TOTAL_FLOOR_AREA", "year"])
    c = c[c["x"].notna()].sort_values("inspection_date").drop_duplicates("UPRN", keep="last")
    x, y = Transformer.from_crs(29902, 32630, always_xy=True).transform(c["x"].to_numpy(), c["y"].to_numpy())
    return pd.DataFrame({"cert_id": c["cert_id"].astype(str).to_numpy(), "year": c["year"].to_numpy(), "x": x, "y": y,
                         "sap": pd.to_numeric(c["sap_score"], errors="coerce").to_numpy(), "band": c["CURRENT_ENERGY_RATING"].to_numpy(),
                         "date": c["inspection_date"].astype(str).to_numpy(), "property_type": c["PROPERTY_TYPE"].to_numpy(),
                         "built_form": c["BUILT_FORM"].to_numpy(),
                         "age_band": c["CONSTRUCTION_AGE_BAND"].astype(str).str.replace(r"^Northern Ireland:\s*", "", regex=True).to_numpy(),
                         "floor_area": pd.to_numeric(c["TOTAL_FLOOR_AREA"], errors="coerce").to_numpy()})


def belfast_table_features(cert_ids, years):
    """All model features of the Belfast modelling tables for these certificates (any year present)."""
    sys.path.insert(0, str(PHD / "code/models"))
    import baseline as b
    frames = []
    for yr in sorted(set(int(y) for y in years if pd.notna(y))):
        p = DATA / "belfast/model" / f"dataset_{yr}.parquet"
        if p.exists():
            frames.append(pd.read_parquet(p))
    if not frames:
        return None
    d = pd.concat(frames, ignore_index=True)
    d["id_cert"] = d["id_cert"].astype(str)
    d = d[d["id_cert"].isin(set(cert_ids))].drop_duplicates("id_cert")
    dd = pd.read_csv(DATA / "belfast/model/data_dictionary.csv")
    X = b.features(d, dd, b.SETS["eo_morph_ctx"])
    X.index = d["id_cert"].to_numpy()
    return X


def as_X(d, cols):
    X = d[cols].copy()
    for c in X:
        if X[c].dtype == object or str(X[c].dtype).startswith("string"):
            X[c] = X[c].astype("category")
    return X


def cv(X, y, groups, folds=5):
    pred = np.full(len(y), np.nan)
    for tr, te in GroupKFold(n_splits=folds).split(X, y, groups):
        pred[te] = lgb.LGBMRegressor(**LGBM).fit(X.iloc[tr], y[tr]).predict(X.iloc[te])
    return mean_absolute_error(y, pred), r2_score(y, pred)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    summary, corr, cvrows = [], [], []
    for scene, (site, place, timing) in SCENES.items():
        meta = json.loads((HS / f"{scene}_visual_30_hotsat1" / "metadata.json").read_text())
        pr = meta["properties"]
        certs = belfast() if site == "belfast" else england(scene)
        for product in ("visual", "stacked"):
            f = HS / f"{scene}_visual_30_hotsat1" / (f"{scene}_visual_30_hotsat1.tiff" if product == "visual" else f"{scene}_visual_30_hotsat1_stacked.tiff")
            a, t, epsg = load_raster(f)
            assert epsg == 32630
            d = certs.copy()
            d["hs_pt"], d["hs_anom"] = sample(a, t, d["x"].to_numpy(), d["y"].to_numpy())
            d = d[d["hs_pt"].notna() & d["sap"].notna()].reset_index(drop=True)
            d.to_parquet(keep(OUT / f"samples_{site}_{product}.parquet"), index=False)
            summary.append({"scene": scene, "site": site, "place": place, "timing": timing, "product": product,
                            "datetime": pr["datetime"], "gsd_m": round(pr["gsd"], 2), "sun_elevation": round(pr["view:sun_elevation"], 1),
                            "off_nadir": round(pr["view:off_nadir"], 1), "area_km2": round(np.isfinite(a).sum() * t.a ** 2 / 1e6, 1),
                            "certificates": len(d), "dn_p1": float(np.nanpercentile(a, 1)), "dn_p99": float(np.nanpercentile(a, 99))})
            print(f"{site} {product}: {len(d):,} certificates in the scene", flush=True)
            if len(d) < 100:
                continue
            for grp, g in [("all", d)] + [(f"type={k}", v) for k, v in d.groupby("property_type") if len(v) >= 100]:
                for v in ("hs_pt", "hs_anom"):
                    rho, p = stats.spearmanr(g[v], g["sap"])
                    corr.append({"site": site, "product": product, "subset": grp, "n": len(g), "variable": v,
                                 "spearman_sap": round(rho, 3), "p": float(p)})
            groups = (np.floor(d["x"] / 500).astype(int).astype(str) + "_" + np.floor(d["y"] / 500).astype(int).astype(str)).to_numpy()
            y = d["sap"].to_numpy("float64")
            sets = {"basic attributes": as_X(d, BASIC), "basic + HotSat": as_X(d, BASIC + ["hs_pt", "hs_anom"]),
                    "HotSat only": as_X(d, ["hs_pt", "hs_anom"])}
            if site == "belfast":
                F = belfast_table_features(d["cert_id"], d["year"])
                if F is not None:
                    m = d["cert_id"].isin(F.index).to_numpy()
                    dm = d[m].reset_index(drop=True)
                    Fm = F.loc[dm["cert_id"]].reset_index(drop=True)
                    for name, X in {"all table features (Sentinel, Landsat, morphology, LiDAR, Census)": Fm,
                                    "all table features + HotSat": pd.concat([Fm, dm[["hs_pt", "hs_anom"]]], axis=1),
                                    "basic attributes (same certificates)": as_X(dm, BASIC),
                                    "basic + HotSat (same certificates)": as_X(dm, BASIC + ["hs_pt", "hs_anom"])}.items():
                        mae, r2 = cv(X, dm["sap"].to_numpy("float64"), groups[m])
                        cvrows.append({"site": site, "product": product, "features": name, "n": int(m.sum()),
                                       "sap_mae": round(mae, 2), "sap_r2": round(r2, 3)})
            for name, X in sets.items():
                mae, r2 = cv(X, y, groups)
                cvrows.append({"site": site, "product": product, "features": name, "n": len(d), "sap_mae": round(mae, 2), "sap_r2": round(r2, 3)})
    pd.DataFrame(summary).to_csv(keep(OUT / "hotsat_summary.csv"), index=False)
    pd.DataFrame(corr).to_csv(keep(OUT / "hotsat_correlation.csv"), index=False)
    pd.DataFrame(cvrows).to_csv(keep(OUT / "hotsat_cv.csv"), index=False)
    with pd.option_context("display.width", 200, "display.max_colwidth", 80, "display.max_rows", 200):
        print(pd.DataFrame(summary).drop(columns=["scene"]).to_string(index=False))
        print(pd.DataFrame(corr).query("subset == 'all'").to_string(index=False))
        print(pd.DataFrame(cvrows).to_string(index=False))


if __name__ == "__main__":
    main()
