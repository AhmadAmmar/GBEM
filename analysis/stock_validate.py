"""Do whole-stock estimates agree with measured energy use better than certificates alone? (RQ4)

    python stock_validate.py --area london [--year 2024]

England and Wales only (measured domestic gas and electricity by LSOA, DESNZ; none at this scale for Northern
Ireland). Per LSOA:
  certified    mean SAP of the current stock of certificates (analysis/stock.py, units_nbhd)
  predicted    dwelling-weighted mean predicted SAP of all dwelling buildings (models/stock_predict.py)
  measured     mean gas and electricity per meter (DESNZ, same year where available, else the latest)
Spearman correlations of certified and predicted SAP with measured use, with and without controlling for the floor
area of the certified homes (partial correlation on ranks), and the difference certified - predicted per LSOA
(certificate bias) against deprivation (IoD 2025 income decile).
Output: data/<area>/analysis/stock_validation.csv and stock_validation_lsoa.parquet
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
import geopandas as gpd
from scipy import stats
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"


def partial(a, b, c):
    r = pd.DataFrame({"a": a, "b": b, "c": c}).dropna().rank()
    res = lambda y: y - np.polyval(np.polyfit(r["c"], y, 1), r["c"])
    return stats.pearsonr(res(r["a"]), res(r["b"]))[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", default="london"); ap.add_argument("--year", type=int, default=2024)
    a = ap.parse_args()
    if a.area != "london":
        raise SystemExit("measured small-area energy is available for England and Wales only")
    pred = pd.read_parquet(DATA / a.area / "model/stock" / f"stock_pred_{a.year}.parquet")
    fp = gpd.read_parquet(DATA / a.area / "epc/footprints.parquet", columns=["fp_id", "geometry"])
    fp["fp_id"] = fp["fp_id"].astype(str)
    fp = fp[fp["fp_id"].isin(set(pred["fp_id"]))]
    pts = gpd.GeoDataFrame(fp[["fp_id"]], geometry=fp.geometry.representative_point(), crs=fp.crs)
    lsoa = gpd.read_file(DATA / "london/boundaries_ons/lsoa21_bgc_v5_london.gpkg").to_crs(fp.crs)[["LSOA21CD", "geometry"]]
    j = gpd.sjoin(pts, lsoa, how="inner", predicate="within")[["fp_id", "LSOA21CD"]]
    p = pred.merge(j, on="fp_id")
    w = p["n_uprn"]
    agg = p.assign(ws=p["pred_sap"] * w).groupby("LSOA21CD").agg(dwellings=("n_uprn", "sum"), ws=("ws", "sum"))
    agg["pred_sap_all"] = agg["ws"] / agg["dwellings"]
    cert = pd.read_parquet(DATA / a.area / "analysis/units_nbhd.parquet").set_index("nbhd")[["n", "sap_mean", "floor_area"]]
    en = pd.read_parquet(DATA / "london/energy_desnz/lsoa_energy_london.parquet")
    yr = a.year if (en["year"] == a.year).any() else en["year"].max()
    e = en[en["year"] == yr].pivot_table(index="lsoa", columns="fuel", values="mean_kwh")
    dep = pd.read_parquet(DATA / "london/deprivation/imd2025_lsoa_london.parquet").set_index("lsoa")[["income_decile"]]
    t = agg[["dwellings", "pred_sap_all"]].join(cert, how="inner").join(e, how="inner").join(dep, how="left")
    t["cert_minus_pred"] = t["sap_mean"] - t["pred_sap_all"]
    rows = []
    for fuel in ("gas", "electricity"):
        s = t.dropna(subset=[fuel])
        for name, col in (("certified mean SAP", "sap_mean"), ("predicted mean SAP, all dwellings", "pred_sap_all")):
            rows.append({"measure": name, "fuel": fuel, "energy_year": int(yr), "lsoas": len(s),
                         "spearman": stats.spearmanr(s[col], s[fuel])[0], "partial_given_floor_area": partial(s[col], s[fuel], s["floor_area"])})
    rows.append({"measure": "certified - predicted SAP vs income decile", "fuel": "", "energy_year": int(yr), "lsoas": int(t["income_decile"].notna().sum()),
                 "spearman": stats.spearmanr(t["cert_minus_pred"], t["income_decile"], nan_policy="omit")[0]})
    out = pd.DataFrame(rows)
    d = DATA / a.area / "analysis"
    out.round(4).to_csv(keep(d / "stock_validation.csv"), index=False)
    t.reset_index().rename(columns={"index": "lsoa"}).to_parquet(keep(d / "stock_validation_lsoa.parquet"), index=False)
    print(out.round(3).to_string(index=False))
    print(f"mean certified - predicted SAP per LSOA: {t['cert_minus_pred'].mean():.2f} (median {t['cert_minus_pred'].median():.2f})")


if __name__ == "__main__":
    main()
