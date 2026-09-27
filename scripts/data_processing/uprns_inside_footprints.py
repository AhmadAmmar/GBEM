# -*- coding: utf-8 -*-
"""
Filter EPC points to those inside/on Belfast building footprints.
Paths are hard-coded to your confirmed locations.
"""

import pandas as pd
import geopandas as gpd
from pathlib import Path

# --------- HARD-CODED PATHS ----------
EPC_CSV = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-epc\NI_Domestic_Master_to_01_2025_with_XY_v2.csv"
FOOTPRINTS_SHP = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-buildings\Belfast_Building_Footprints.shp"
OUT_CSV = Path(EPC_CSV).with_name("NI_Domestic_Master_to_01_2025_with_XY_v2_in_footprints.csv")
# -------------------------------------

# Likely EPC CRS candidates for NI Pointer coordinates
EPC_CRS_CANDIDATES = ["EPSG:29902", "EPSG:27700", "EPSG:2157"]
SAMPLE_N = 20000  # for quick CRS detection

# 1) Load footprints and get CRS/bounds
foot = gpd.read_file(FOOTPRINTS_SHP)
if foot.crs is None:
    raise ValueError("Footprints layer has no CRS defined. Define it in GIS first.")
fp_crs = foot.crs
minx, miny, maxx, maxy = foot.total_bounds

# 2) Load EPC, coerce XY to numeric, keep valid rows
epc = pd.read_csv(EPC_CSV, dtype=str, low_memory=False)
total_rows = len(epc)
epc["_X"] = pd.to_numeric(epc["X_COR"], errors="coerce")
epc["_Y"] = pd.to_numeric(epc["Y_COR"], errors="coerce")
epc_valid = epc.dropna(subset=["_X","_Y"]).copy()
valid_xy_rows = len(epc_valid)
if valid_xy_rows == 0:
    raise RuntimeError("No valid X_COR/Y_COR in the EPC CSV.")

# 3) Auto-detect EPC CRS by testing how many sample points land in the footprints bbox
sample = epc_valid.sample(n=min(SAMPLE_N, valid_xy_rows), random_state=42)
scores = {}
for crs in EPC_CRS_CANDIDATES:
    g = gpd.GeoDataFrame(sample.copy(),
                         geometry=gpd.points_from_xy(sample["_X"], sample["_Y"]),
                         crs=crs).to_crs(fp_crs)
    inside_bbox = ((g.geometry.x >= minx) & (g.geometry.x <= maxx) &
                   (g.geometry.y >= miny) & (g.geometry.y <= maxy)).mean()
    scores[crs] = float(inside_bbox)

best_crs = max(scores, key=scores.get)
print("CRS detection (share of sample within footprints extent):")
for k, v in scores.items():
    print(f"  {k}: {v:.3f}")
print(f"=> Selected EPC CRS: {best_crs}")

# 4) Build all EPC points in best_crs and reproject to footprints CRS
epc_pts = gpd.GeoDataFrame(
    epc_valid.copy(),
    geometry=gpd.points_from_xy(epc_valid["_X"], epc_valid["_Y"]),
    crs=best_crs
).to_crs(fp_crs)

# 5) Spatial join (include boundary): point intersects polygon
matched = gpd.sjoin(epc_pts, foot[["geometry"]], how="inner", predicate="intersects")

# 6) Save only EPC columns (drop helpers)
drop_cols = [c for c in ["_X","_Y","index_right"] if c in matched.columns]
out_df = pd.DataFrame(matched.drop(columns=drop_cols))
out_df.to_csv(OUT_CSV, index=False, encoding="utf-8")

# 7) Stats
inside_total = len(out_df)
pct_inside = inside_total / len(epc_pts) if len(epc_pts) else 0.0

print("\n=== EPC ↦ Belfast footprints (intersects) ===")
print(f"Footprints CRS:                           {fp_crs}")
print(f"EPC rows (input):                          {total_rows:,}")
print(f"EPC rows with valid XY:                    {valid_xy_rows:,}")
print(f"EPC points inside/on footprints:           {inside_total:,}  ({pct_inside:.2%})")
print(f"Output written: {OUT_CSV}")
