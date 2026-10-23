"""Which urban forms and streetscapes perform better, how much, and why.

    python morph_types.py --area belfast [--years 2020 2021 2022 2023 2024 2025] [--k 7]

1. Typology: every 250 m grid cell with at least 10 certificates is described by the median form of its buildings and
   streets (building cover, height, footprint area, shared walls, addresses per footprint, compactness, street width,
   H/W, setback, frontage, distance to a major road). k-means (k types, standardised measures) groups the cells; each
   type is named from its strongest traits. Per type: certificates, mean SAP, share F-G, poor walls / roof / windows,
   heat pumps, PV, and the age bands it is made of.
2. Explanation: LightGBM predicts the SAP score from morphology, streetscape and LiDAR only (no satellite, no
   certificate attributes). SHAP contributions (LightGBM pred_contrib) of out-of-fold models (spatial 5-fold, 2 km
   blocks) give the mean absolute effect of each measure and, binned by deciles of the measure, its direction (how the
   predicted SAP changes along the measure, everything else as observed).
Inputs: data/<area>/model/dataset_<year>.parquet, data/<area>/epc/streetscape_fp.parquet, analysis/cert_enriched.
Outputs in data/<area>/analysis/: morph_types_cells.parquet, morph_types_summary.csv, morph_shap_importance.csv,
morph_shap_dependence.csv, morph_cv.csv
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.cluster import KMeans
from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_absolute_error, r2_score
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "models"))
from safeio import keep                      # existing outputs are archived, never overwritten
import baseline as B

DATA = B.DATA
FORM = {"morph_bcov_100": "building cover 100 m", "height": "building height", "morph_area_m2": "footprint area",
        "morph_shared_wall_ratio": "shared walls", "morph_n_uprn": "addresses per building", "morph_compactness": "compactness",
        "st_width_m": "street width", "st_hw": "street H/W", "st_setback_m": "setback", "st_frontage": "frontage density",
        "morph_major_road_dist_m": "distance to major road"}
TRAIT = {  # words for high / low values of a measure, used to name the types
    "morph_bcov_100": ("dense", "sparse"), "height": ("tall", "low-rise"), "morph_area_m2": ("large blocks", "small footprints"),
    "morph_shared_wall_ratio": ("terraced / attached", "detached"), "morph_n_uprn": ("multi-dwelling", "single-dwelling"),
    "st_width_m": ("wide streets", "narrow streets"), "st_hw": ("deep canyons", "open streets"), "st_setback_m": ("set back", "street-front"),
    "st_frontage": ("continuous frontage", "gappy frontage"), "morph_major_road_dist_m": ("away from main roads", "on main roads"),
    "morph_compactness": ("compact shapes", "irregular shapes")}


def load(area, years):
    d, dd = B.load(area, years)
    st = pd.read_parquet(DATA / area / "epc/streetscape_fp.parquet")
    d = d.drop(columns=[c for c in d.columns if c.startswith("st_")]).merge(st, left_on="id_fp", right_on="fp_id", how="left")
    d["height"] = pd.to_numeric(d.get("lidar_height_med_m"), errors="coerce").where(pd.to_numeric(d.get("lidar_valid_share"), errors="coerce") >= 0.5)
    d["height"] = d["height"].fillna(pd.to_numeric(d.get("morph_height_m"), errors="coerce"))
    d["sap"] = pd.to_numeric(d["label_sap"], errors="coerce")
    return d, dd


def name_type(z):
    """two strongest traits of a cluster centre (standardised)"""
    order = z.abs().sort_values(ascending=False).index[:3]
    words = [TRAIT[k][0] if z[k] > 0 else TRAIT[k][1] for k in order if abs(z[k]) > 0.35]
    return ", ".join(words[:3]) or "mixed / average"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--years", nargs="+", type=int, default=list(range(2020, 2026)))
    ap.add_argument("--k", type=int, default=7)
    a = ap.parse_args()
    out = DATA / a.area / "analysis"
    d, dd = load(a.area, a.years)
    print(f"{a.area}: {len(d):,} certificates {a.years[0]}-{a.years[-1]}", flush=True)
    # 1. typology of 250 m cells
    d["cell"] = (np.floor(d["x"] / 250).astype(int)).astype(str) + "_" + (np.floor(d["y"] / 250).astype(int)).astype(str)
    for c in FORM:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    cells = d.groupby("cell").agg(n=("sap", "size"), sap=("sap", "mean"), **{c: (c, "median") for c in FORM})
    cells = cells[cells["n"] >= 10].dropna(subset=list(FORM))
    Z = cells[list(FORM)].copy()
    for c in ("morph_area_m2", "morph_n_uprn", "st_setback_m", "morph_major_road_dist_m", "st_frontage"):
        Z[c] = np.log1p(Z[c].clip(lower=0))
    Z = (Z - Z.mean()) / Z.std()
    km = KMeans(n_clusters=a.k, n_init=20, random_state=42).fit(Z)
    cells["type_id"] = km.labels_
    centres = pd.DataFrame(km.cluster_centers_, columns=list(FORM))
    names = {i: name_type(centres.loc[i]) for i in range(a.k)}
    cells["type"] = cells["type_id"].map(names)
    # certificate-level outcomes per type (all certificates of the cells of the type)
    e = pd.read_parquet(out / "cert_enriched.parquet", columns=["cert_id", "band", "poor_walls", "poor_roof", "poor_windows", "fuel", "pv", "age_band"])
    e = e.rename(columns={"cert_id": "id_cert"})
    m = d[["id_cert", "cell", "sap"]].merge(e, on="id_cert", how="left").merge(cells[["type_id", "type"]], left_on="cell", right_index=True, how="inner")
    summ = m.groupby(["type_id", "type"]).agg(cells=("cell", "nunique"), certificates=("sap", "size"), sap_mean=("sap", "mean"),
                                               share_FG=("band", lambda s: s.isin(["F", "G"]).mean()),
                                               share_AC=("band", lambda s: s.isin(["A", "B", "C"]).mean()),
                                               poor_walls=("poor_walls", "mean"), poor_roof=("poor_roof", "mean"),
                                               poor_windows=("poor_windows", "mean"), heat_pump=("fuel", lambda s: s.eq("heat pump").mean()),
                                               pv=("pv", "mean"),
                                               main_age_bands=("age_band", lambda s: "; ".join(f"{k} {v:.0%}" for k, v in s.value_counts(normalize=True).head(3).items())))
    summ = summ.join(cells.groupby("type_id")[list(FORM)].median().rename(columns=lambda c: f"median_{c}"), on="type_id")
    summ = summ.sort_values("sap_mean", ascending=False)
    summ.round(3).to_csv(keep(out / "morph_types_summary.csv"))
    ij = cells.index.to_series().str.split("_", expand=True).astype(int)
    cells["cx"], cells["cy"] = (ij[0] + .5) * 250, (ij[1] + .5) * 250
    cells.reset_index().to_parquet(keep(out / "morph_types_cells.parquet"), index=False)
    print(summ[["cells", "certificates", "sap_mean", "share_FG", "poor_walls"]].round(2).to_string(), flush=True)
    # 2. explanation: SAP from form only, SHAP contributions out of fold
    groups = ["morphology", "streets", "lidar"]
    dd2 = pd.concat([dd, pd.DataFrame({"column": [c for c in d.columns if c.startswith("st_")], "group": "streets"})]).drop_duplicates("column")
    X = B.features(d, dd2, groups)
    y = d["sap"].to_numpy("float64")
    ok = ~np.isnan(y)
    X, y, dsub = X[ok].reset_index(drop=True), y[ok], d[ok].reset_index(drop=True)
    blocks = (np.floor(dsub["x"] / 2000).astype(int).astype(str) + "_" + np.floor(dsub["y"] / 2000).astype(int).astype(str)).to_numpy()
    pred = np.full(len(y), np.nan)
    contrib = np.zeros((len(y), X.shape[1]))
    for tr, te in GroupKFold(n_splits=5).split(X, groups=blocks):
        mdl = lgb.LGBMRegressor(**{**B.LGBM, "colsample_bytree": 0.8}).fit(X.iloc[tr], y[tr])
        pred[te] = mdl.predict(X.iloc[te])
        contrib[te] = mdl.predict(X.iloc[te], pred_contrib=True)[:, :-1]
    pd.DataFrame([{"area": a.area, "years": f"{a.years[0]}-{a.years[-1]}", "n": len(y), "features": "morphology + streetscape + LiDAR",
                   "sap_mae": mean_absolute_error(y, pred), "sap_r2": r2_score(y, pred)}]).round(4).to_csv(keep(out / "morph_cv.csv"), index=False)
    print(f"SAP from form only (spatial CV): MAE {mean_absolute_error(y, pred):.2f}, R2 {r2_score(y, pred):.3f}", flush=True)
    imp = pd.DataFrame({"feature": X.columns, "mean_abs_shap": np.abs(contrib).mean(0)}).sort_values("mean_abs_shap", ascending=False)
    imp.round(4).to_csv(keep(out / "morph_shap_importance.csv"), index=False)
    dep = []
    for f in imp["feature"].head(15):
        j = list(X.columns).index(f)
        x = X[f]
        if str(x.dtype) == "category":
            for k, g in pd.DataFrame({"x": x.astype(str), "s": contrib[:, j]}).groupby("x"):
                if len(g) >= 30:
                    dep.append({"feature": f, "bin": k, "x_median": np.nan, "n": len(g), "shap_mean": g["s"].mean()})
            continue
        q = pd.qcut(x, 10, duplicates="drop")
        for k, g in pd.DataFrame({"x": x, "q": q, "s": contrib[:, j]}).dropna().groupby("q", observed=True):
            dep.append({"feature": f, "bin": str(k), "x_median": g["x"].median(), "n": len(g), "shap_mean": g["s"].mean()})
    pd.DataFrame(dep).round(4).to_csv(keep(out / "morph_shap_dependence.csv"), index=False)
    print("top form effects:", ", ".join(f"{r.feature} {r.mean_abs_shap:.2f}" for r in imp.head(8).itertuples()))
    print("written", out)


if __name__ == "__main__":
    main()
