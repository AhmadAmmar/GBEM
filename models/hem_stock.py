"""The proposed HEM EPC metrics (proxies of analysis/hem_metrics.py) predicted for every dwelling building, certified
or not, from open data.

    python hem_stock.py --area london|belfast [--year 2024] [--featureset eo_morph]

Targets, from the certificates of the year:
  fabric_c   fabric proxy at or below the C/D boundary q* (analysis/hem_metrics.py; q* read from
             hem_metrics_summary.csv)
  fossil     primary heating fuel is fossil (at most D on the proposed heating metric); heat networks and unknown fuel
             are left out of training
LightGBM classifiers (settings of baseline.py) on the feature set, with spatial 5-fold cross-validation (2 km blocks)
for AUC and calibration (mean predicted vs observed share). The final models are fitted on all certificates of the year
and applied to every dwelling building (stock_predict.building_batches), weighted by addresses in the summaries.
Outputs in data/<area>/model/stock/: hem_stock_pred_<year>.parquet (fp_id, n_uprn, certified, p_fabric_c, p_fossil),
hem_stock_summary_<year>.csv (CV skill; predicted shares for all dwellings and for certified buildings only),
hem_stock_cells_<year>.parquet (per 500 m cell).
Predictions are for areas, not individual homes.
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import lightgbm as lgb
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "analysis"))
import baseline as B
import stock_predict as SP
from hem_metrics import fuel_class
from safeio import keep                      # existing outputs are archived, never overwritten


def targets(area, d):
    s = pd.read_csv(B.DATA / area / "analysis/hem_metrics_summary.csv").set_index("measure")["value"]
    qstar = float(s["fabric proxy C/D boundary q* (kWh/m2/yr)"])
    ph = pd.read_parquet(B.DATA / area / "analysis/physics_cert.parquet", columns=["cert_id", "q_as_described_kwh_m2"])
    c = pd.read_parquet(B.DATA / area / "epc/certificates_linked.parquet", columns=["cert_id", "MAIN_FUEL"])
    for t in (ph, c):
        t["cert_id"] = t["cert_id"].astype(str)
    m = d[["id_cert"]].astype(str).merge(ph.drop_duplicates("cert_id"), left_on="id_cert", right_on="cert_id", how="left") \
        .merge(c.drop_duplicates("cert_id"), on="cert_id", how="left")
    q = m["q_as_described_kwh_m2"].where(m["q_as_described_kwh_m2"].between(10, 1000))
    fc = fuel_class(m["MAIN_FUEL"])
    return {"fabric_c": np.where(q.notna(), (q <= qstar).astype(float), np.nan),
            "fossil": np.where(fc.isin(["fossil", "electric", "biomass or mixed"]), fc.eq("fossil").astype(float), np.nan)}, qstar


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--featureset", default="eo_morph")
    a = ap.parse_args()
    out = B.DATA / a.area / "model/stock"
    d, dd = B.load(a.area, [a.year])
    d["id_cert"] = d["id_cert"].astype(str)
    T, qstar = targets(a.area, d)
    X = B.features(d, dd, B.SETS[a.featureset])
    cols = list(X.columns)
    cats = {c: X[c].cat.categories for c in cols if str(X[c].dtype) == "category"}
    g = (np.floor(d["x"] / 2000).astype(int).astype(str) + "_" + np.floor(d["y"] / 2000).astype(int).astype(str)).to_numpy()
    rows, models = [], {}
    for name, y in T.items():
        idx = np.flatnonzero(~np.isnan(y))
        p = np.full(len(y), np.nan)
        for tr, te in GroupKFold(n_splits=5).split(idx, groups=g[idx]):
            m = lgb.LGBMClassifier(**B.LGBM).fit(X.iloc[idx[tr]], y[idx[tr]])
            p[idx[te]] = m.predict_proba(X.iloc[idx[te]])[:, 1]
        rows.append({"measure": f"{name}: spatial CV AUC", "value": roc_auc_score(y[idx], p[idx])})
        rows.append({"measure": f"{name}: observed share (certificates {a.year})", "value": y[idx].mean()})
        rows.append({"measure": f"{name}: mean CV prediction", "value": p[idx].mean()})
        rows.append({"measure": f"{name}: n", "value": len(idx)})
        models[name] = lgb.LGBMClassifier(**B.LGBM).fit(X.iloc[idx], y[idx])
        print(rows[-4:], flush=True)
    certified = set(d["id_fp"].dropna().astype(str))
    parts = []
    for S in SP.building_batches(a.area, a.year, need=cols + ["morph_n_uprn"]):
        XS = S.reindex(columns=cols)
        for c in cols:
            if c in cats:
                XS[c] = pd.Categorical(XS[c].astype("string"), categories=cats[c])
            else:
                XS[c] = pd.to_numeric(XS[c], errors="coerce").astype("float32")
        parts.append(pd.DataFrame({"fp_id": S["id_fp"].astype(str).to_numpy(),
                                   "n_uprn": pd.to_numeric(S["morph_n_uprn"], errors="coerce").fillna(1).clip(lower=1).to_numpy(),
                                   "certified": S["id_fp"].astype(str).isin(certified).to_numpy(),
                                   "p_fabric_c": models["fabric_c"].predict_proba(XS)[:, 1],
                                   "p_fossil": models["fossil"].predict_proba(XS)[:, 1]}))
        print(f"  predicted {sum(len(p) for p in parts):,} buildings", flush=True)
    res = pd.concat(parts, ignore_index=True)
    res.to_parquet(keep(out / f"hem_stock_pred_{a.year}.parquet"), index=False)
    w = res["n_uprn"]; cw = res.loc[res.certified, "n_uprn"]
    for col in ("p_fabric_c", "p_fossil"):
        rows.append({"measure": f"{col}: all dwellings", "value": np.average(res[col], weights=w)})
        rows.append({"measure": f"{col}: certified buildings", "value": np.average(res.loc[res.certified, col], weights=cw)})
    rows += [{"measure": "dwellings (addresses)", "value": int(w.sum())}, {"measure": "buildings", "value": len(res)},
             {"measure": "fabric C/D boundary q*", "value": qstar}]
    s = pd.DataFrame(rows)
    s.round(4).to_csv(keep(out / f"hem_stock_summary_{a.year}.csv"), index=False)
    fp = gpd.read_parquet(B.DATA / a.area / "epc/footprints.parquet", columns=["fp_id", "geometry"])
    fp["fp_id"] = fp["fp_id"].astype(str)
    res = res.merge(SP.shapely_centroids(fp), on="fp_id", how="left").dropna(subset=["x"])
    res["cx"] = (res.x // 500) * 500 + 250; res["cy"] = (res.y // 500) * 500 + 250
    res["wf"] = res.p_fabric_c * res.n_uprn; res["wo"] = res.p_fossil * res.n_uprn
    cells = res.groupby(["cx", "cy"]).agg(dwellings=("n_uprn", "sum"), wf=("wf", "sum"), wo=("wo", "sum")).reset_index()
    cells["fabric_c"] = cells.wf / cells.dwellings; cells["fossil"] = cells.wo / cells.dwellings
    cells[cells.dwellings >= 10].drop(columns=["wf", "wo"]).to_parquet(keep(out / f"hem_stock_cells_{a.year}.parquet"), index=False)
    print(s.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
