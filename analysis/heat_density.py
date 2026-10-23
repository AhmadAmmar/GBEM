"""Heat demand density for heat-network zoning, estimated from buildings and checked against metered gas (London).

    python heat_density.py --area belfast|london

Estimate per 250 m cell: space-heating demand (MWh/yr) = sum over the dwelling buildings in the cell of gross floor
area (epc/physics.py: footprint area x storeys) x the median physics demand per m2 of the certified homes of the cell
(analysis/physics_check.py, U-values from the certificates, degree-days of the home); cells with fewer than 5
certified homes use the median of the neighbourhood. Density = demand / 0.0625 km2 (MWh/km2/yr).
Check (London): the same estimate summed by LSOA against metered domestic gas (DESNZ 2024, total kWh / LSOA area):
Spearman correlation and the ratio of the totals. Gas also covers hot water and cooking, so the levels differ;
the ranking is what zoning needs.
Outputs in data/<area>/analysis/: heat_density_cells.parquet (cell, cx, cy, demand_mwh, density_mwh_km2, homes_cert),
heat_density_check.csv (London)
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
import geopandas as gpd
from scipy import stats
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"
CELL = 250


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True)
    a = ap.parse_args()
    out = DATA / a.area / "analysis"
    e = DATA / a.area / "epc"
    # certified demand per m2 by cell and neighbourhood
    ph = pd.read_parquet(out / "physics_cert.parquet", columns=["cert_id", "q_as_described_kwh_m2"])
    cur = pd.read_parquet(out / "stock_current.parquet", columns=["cert_id", "cell", "nbhd"])
    q = cur.merge(ph, on="cert_id").dropna()
    q = q[q["q_as_described_kwh_m2"].between(5, 1000)]
    qc = q.groupby("cell")["q_as_described_kwh_m2"].agg(["median", "size"])
    qn = q.groupby("nbhd")["q_as_described_kwh_m2"].median()
    # all dwelling buildings: floor area and cell
    phys = pd.read_parquet(e / "physics_fp.parquet", columns=["fp_id", "phys_floor_m2"])
    dw = pd.read_parquet(e / "dwellings_fp.parquet", columns=["fp_id", "n_uprn"])
    fp = gpd.read_parquet(e / "footprints.parquet", columns=["fp_id", "geometry"])
    b = fp.merge(dw[dw["n_uprn"] >= 1], on="fp_id").merge(phys, on="fp_id")
    c = b.geometry.representative_point()
    b["x"], b["y"] = c.x.to_numpy(), c.y.to_numpy()
    b["cell"] = (np.floor(b["x"] / CELL).astype(int)).astype(str) + "_" + (np.floor(b["y"] / CELL).astype(int)).astype(str)
    # neighbourhood of each building, for cells with few certificates
    cn = cur.dropna(subset=["cell", "nbhd"]).groupby("cell")["nbhd"].agg(lambda s: s.mode().iat[0])
    b["nbhd"] = b["cell"].map(cn)
    b["q"] = b["cell"].map(qc["median"].where(qc["size"] >= 5)).fillna(b["nbhd"].map(qn))
    b["demand_mwh"] = b["phys_floor_m2"] * b["q"] / 1000
    cells = b.groupby("cell").agg(demand_mwh=("demand_mwh", "sum"), buildings=("fp_id", "size"), floor_m2=("phys_floor_m2", "sum"))
    cells["homes_cert"] = qc["size"].reindex(cells.index).fillna(0).astype(int)
    ij = cells.index.to_series().str.split("_", expand=True).astype(int)
    cells["cx"], cells["cy"] = (ij[0] + 0.5) * CELL, (ij[1] + 0.5) * CELL
    cells["density_mwh_km2"] = cells["demand_mwh"] / (CELL * CELL / 1e6)
    cells = cells[cells["demand_mwh"] > 0]
    cells.round(2).reset_index().to_parquet(keep(out / "heat_density_cells.parquet"), index=False)
    print(f"{a.area}: {len(cells):,} cells; estimated space-heating demand {cells['demand_mwh'].sum() / 1e3:,.0f} GWh/yr; "
          f"cells above 3,000 MWh/km2: {(cells['density_mwh_km2'] > 3000).mean():.1%}", flush=True)
    if a.area == "london":
        lsoa = gpd.read_file(DATA / "london/boundaries_ons/lsoa21_bgc_v5_london.gpkg").to_crs(27700)[["LSOA21CD", "geometry"]]
        pts = gpd.GeoDataFrame(b[["demand_mwh"]], geometry=gpd.points_from_xy(b["x"], b["y"]), crs=27700)
        j = gpd.sjoin(pts, lsoa, predicate="within")
        est = j.groupby("LSOA21CD")["demand_mwh"].sum()
        en = pd.read_parquet(DATA / "london/energy_desnz/lsoa_energy_london.parquet")
        gas = en[(en["fuel"] == "gas") & (en["year"] == 2024)].set_index("lsoa")["total_kwh"] / 1000
        area_km2 = lsoa.set_index("LSOA21CD").area / 1e6
        t = pd.DataFrame({"est": est, "gas": gas, "km2": area_km2}).dropna()
        t = t[t["est"] > 0]
        rows = [{"measure": "demand per LSOA", "lsoas": len(t), "spearman": stats.spearmanr(t["est"], t["gas"])[0],
                 "ratio_totals_est_to_gas": t["est"].sum() / t["gas"].sum()},
                {"measure": "density per km2", "lsoas": len(t), "spearman": stats.spearmanr(t["est"] / t["km2"], t["gas"] / t["km2"])[0],
                 "ratio_totals_est_to_gas": np.nan}]
        chk = pd.DataFrame(rows)
        chk.round(4).to_csv(keep(out / "heat_density_check.csv"), index=False)
        print(chk.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
