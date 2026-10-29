"""Does the whole-stock fossil-heating prediction (models/hem_stock.py) agree with the Census 2021 count of all households?

    python hem_census_check.py --area london|belfast [--year 2024]

Census: TS046 type of central heating by LSOA (England and Wales); MS-E11 central heating by ward (Northern Ireland,
OSNI 2012 wards as used by the census). The model is trained only on fossil vs electric, biomass or renewable heating
(heat networks and unknown fuel left out), so the census share is taken on the same basis: fossil (mains gas, oil,
tank or bottled gas, solid fuel) over fossil + electric + renewable + wood, single-type households only; two or more
types, other and no central heating are left out and their share is reported. Census heating is not a model input
(feature set eo_morph), so the check is independent.
Per area unit: dwelling-weighted mean p_fossil of all dwelling buildings (representative point in the unit) against the
census share. Reports Spearman and Pearson correlation, mean bias and mean absolute error, weighted by households,
for all units and for units with at least 50 predicted dwellings.
Outputs in data/<area>/analysis/: hem_census_check.csv (summary) and hem_census_check_units.parquet
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
import geopandas as gpd
from scipy import stats
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"
FOSSIL = ["gas", "oil", "lpg", "solid"]
OTHER = ["electric", "renewable", "wood"]


def census_london():
    c = pd.read_csv(DATA / "london/census2021_ons/census2021-ts046-lsoa.csv")
    c.columns = [x.split(": ")[-1] for x in c.columns]
    m = {"gas": "Mains gas only", "lpg": "Tank or bottled gas only", "oil": "Oil only", "solid": "Solid fuel only",
         "electric": "Electric only", "renewable": "Renewable energy only", "wood": "Wood only",
         "network": "District or communal heat networks only", "total": "All households"}
    out = pd.DataFrame({k: c[v] for k, v in m.items()}); out["unit"] = c["geography code"]
    bounds = gpd.read_file(DATA / "london/boundaries_ons/lsoa21_bgc_v5_london.gpkg")[["LSOA21CD", "geometry"]]
    return out, bounds.rename(columns={"LSOA21CD": "unit"})


def census_belfast():
    x = pd.read_excel(DATA / "belfast/census2021_nisra/census-2021-ms-e11.xlsx", sheet_name="Ward", header=7)
    x = x[x["Geography code"].astype(str).str.match(r"^N08\d{6}$")].drop_duplicates("Geography code")  # counts table first
    m = {"gas": "Mains gas only", "lpg": "Tank or bottled gas only", "oil": "Oil only",
         "solid": "Solid fuel (for example coal) only", "electric": "Electric (for example storage heaters) only",
         "renewable": "Renewable heating system only", "wood": "Wood (for example logs or waste wood) only",
         "total": "All households"}
    out = pd.DataFrame({k: pd.to_numeric(x[v]) for k, v in m.items()}); out["network"] = 0; out["unit"] = x["Geography code"].values
    w = gpd.read_file(f"zip://{(DATA / 'belfast/boundaries_osni/osni_open_data_largescale_boundaries_wards_2012.zip').as_posix()}")
    return out, w[["WardCode", "geometry"]].rename(columns={"WardCode": "unit"})


def wstats(t, w):
    r = t["pred"] - t["census"]
    return {"units": len(t), "households": int(w.sum()),
            "spearman": stats.spearmanr(t["pred"], t["census"])[0], "pearson": stats.pearsonr(t["pred"], t["census"])[0],
            "census share (weighted)": np.average(t["census"], weights=w), "predicted share (weighted)": np.average(t["pred"], weights=w),
            "mean bias pred-census": np.average(r, weights=w), "mean abs error": np.average(r.abs(), weights=w)}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--area", required=True); ap.add_argument("--year", type=int, default=2024)
    a = ap.parse_args()
    cen, bounds = census_london() if a.area == "london" else census_belfast()
    single = cen[FOSSIL + OTHER].sum(axis=1)
    cen["census"] = cen[FOSSIL].sum(axis=1) / single
    cen["excluded_share"] = 1 - (single + cen["network"]) / cen["total"]
    cen["network_share"] = cen["network"] / cen["total"]
    pred = pd.read_parquet(DATA / a.area / "model/stock" / f"hem_stock_pred_{a.year}.parquet")
    fp = gpd.read_parquet(DATA / a.area / "epc/footprints.parquet", columns=["fp_id", "geometry"])
    fp["fp_id"] = fp["fp_id"].astype(str)
    fp = fp[fp["fp_id"].isin(set(pred["fp_id"]))]
    pts = gpd.GeoDataFrame(fp[["fp_id"]], geometry=fp.geometry.representative_point(), crs=fp.crs)
    j = gpd.sjoin(pts, bounds.to_crs(fp.crs), how="inner", predicate="within")[["fp_id", "unit"]]
    p = pred.merge(j, on="fp_id").assign(wp=lambda d: d.p_fossil * d.n_uprn)
    agg = p.groupby("unit").agg(dwellings=("n_uprn", "sum"), wp=("wp", "sum")).reset_index()
    agg["pred"] = agg.wp / agg.dwellings
    t = agg.drop(columns="wp").merge(cen, on="unit").dropna(subset=["census", "pred"])
    t.to_parquet(keep(DATA / a.area / "analysis/hem_census_check_units.parquet"), index=False)
    rows = []
    for label, s in (("all units", t), ("units with >= 50 predicted dwellings", t[t.dwellings >= 50])):
        rows += [{"subset": label, "measure": k, "value": v} for k, v in wstats(s, s["total"]).items()]
    rows += [{"subset": "all units", "measure": "households left out (two or more types, other, none)",
              "value": np.average(t.excluded_share, weights=t.total)},
             {"subset": "all units", "measure": "heat network share", "value": np.average(t.network_share, weights=t.total)}]
    s = pd.DataFrame(rows)
    s.round(4).to_csv(keep(DATA / a.area / "analysis/hem_census_check.csv"), index=False)
    print(s.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
