"""Rooftop solar: potential from LiDAR roofs against existing PV uptake, by deprivation.

    python solar.py --area belfast|london [--usable 0.6] [--kwp-per-m2 0.18]

Potential per dwelling building: south-facing roof area (footprint area x share of the roof facing 135-225 degrees
with a slope of at least 15 degrees / cos(slope), from epc/lidar_*.py) plus flat roof area (footprint area x flat share,
panels tilted), times a usable share (--usable, for obstructions, edges and access) and a module density
(--kwp-per-m2, kWp per m2 of panel); per dwelling = building potential / addresses in the footprint. Assumptions are
arguments and are written into the output.
Uptake: homes of the current stock whose certificate records photovoltaic supply (analysis/stock.py).
By neighbourhood and income-deprivation decile (analysis/vulnerability.py units): houses and bungalows only for the
per-dwelling potential (flats share a roof).
Outputs in data/<area>/analysis/: solar_units_nbhd.parquet, solar_by_decile.csv
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--usable", type=float, default=0.6); ap.add_argument("--kwp-per-m2", type=float, default=0.18)
    a = ap.parse_args()
    e, out = DATA / a.area / "epc", DATA / a.area / "analysis"
    m = pd.read_parquet(e / "morphology.parquet", columns=["fp_id", "area_m2"])
    l = pd.read_parquet(e / "lidar_fp.parquet", columns=["fp_id", "lidar_roof_south_share", "lidar_roof_flat_share", "lidar_roof_slope_med_deg", "lidar_valid_share"])
    dw = pd.read_parquet(e / "dwellings_fp.parquet", columns=["fp_id", "n_uprn"])
    b = m.merge(l, on="fp_id").merge(dw, on="fp_id")
    b = b[(b["lidar_valid_share"] >= 0.5) & (b["n_uprn"] >= 1)]
    slope = np.radians(b["lidar_roof_slope_med_deg"].clip(0, 70))
    roof = b["area_m2"] * (b["lidar_roof_south_share"] / np.cos(slope) + b["lidar_roof_flat_share"])
    b["kwp_building"] = roof * a.usable * a.kwp_per_m2
    b["kwp_per_dwelling"] = b["kwp_building"] / b["n_uprn"]
    cur = pd.read_parquet(out / "stock_current.parquet", columns=["cert_id", "fp_id", "nbhd", "property_type", "pv"])
    d = cur.merge(b[["fp_id", "kwp_per_dwelling"]], on="fp_id", how="left")
    house = d["property_type"].isin(["House", "Bungalow"])
    dep = pd.read_parquet(out / "units_dep.parquet")[["unit", "income_decile"]]
    if a.area == "london":
        d["unit"] = d["nbhd"]
    else:
        ad = pd.read_parquet(out / "stock_current.parquet", columns=["cert_id", "x", "y"])
        import geopandas as gpd
        g = gpd.read_file(DATA / "belfast/deprivation/nimdm2017_sa.gpkg")
        g = (g.set_crs(29902) if g.crs is None else g).to_crs(29902)
        pts = gpd.GeoDataFrame(ad[["cert_id"]], geometry=gpd.points_from_xy(ad["x"], ad["y"]), crs=29902)
        j = gpd.sjoin(pts, g[["SA2011", "geometry"]], predicate="within").drop_duplicates("cert_id")
        d = d.merge(j[["cert_id", "SA2011"]].rename(columns={"SA2011": "unit"}), on="cert_id", how="left")
    d = d.merge(dep, on="unit", how="left")
    by = d.assign(house=house).groupby("income_decile").agg(homes=("cert_id", "size"), pv_share=("pv", "mean"),
                                                          pv_share_houses=("pv", lambda s: s[house.loc[s.index]].mean()),
                                                          kwp_median_houses=("kwp_per_dwelling", lambda s: s[house.loc[s.index]].median()))
    by["assumptions"] = f"usable {a.usable}, {a.kwp_per_m2} kWp/m2"
    by.round(4).to_csv(keep(out / "solar_by_decile.csv"))
    print(by.round(3).to_string())
    u = d.assign(house=house).groupby("nbhd").agg(homes=("cert_id", "size"), pv_share=("pv", "mean"),
                                                  kwp_median_houses=("kwp_per_dwelling", lambda s: s[house.loc[s.index]].median()),
                                                  kwp_total=("kwp_per_dwelling", "sum"))
    u[u["homes"] >= 10].round(3).reset_index().to_parquet(keep(out / "solar_units_nbhd.parquet"), index=False)
    print(f"{a.area}: {len(b):,} dwelling buildings with LiDAR roofs; median potential per house "
          f"{d.loc[house, 'kwp_per_dwelling'].median():.1f} kWp; PV on {d['pv'].mean():.1%} of the current stock")


if __name__ == "__main__":
    main()
