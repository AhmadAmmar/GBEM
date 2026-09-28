# -*- coding: utf-8 -*-
"""
Compare Saad UPRN CSV vs Paul's union UPRN-with-XY CSV.

Outputs (next to Saad file):
  - saad_only_uprns.csv
  - paul_only_uprns.csv
  - uprn_overlap_xy.csv
  - uprn_overlap_no_xy.csv
Prints headline stats (rows, uniques, overlaps, XY coverage, distance summary).

Run: python compare_uprn_datasets.py
"""

import pandas as pd
import numpy as np
import re
from pathlib import Path
from math import radians, sin, cos, sqrt, atan2

# ------------- CONFIG -------------
SAAD_CSV = r"D:\OneDrive - Ulster University\PhD\data\belfast\uprn\uprn.csv"
PAUL_UNION_CSV = r"D:\OneDrive - Ulster University\PhD\data\belfast\uprn\BELFS_20250829_F\uprn_union_with_xy.csv"

CANDIDATE_ENCODINGS = ("utf-8", "utf-8-sig", "cp1252", "latin1")
X_CANDIDATES = ["X_COR","X_COORD","XCOORD","X","EASTING","X_COORDINATE","XCORD","LON","LONGITUDE"]
Y_CANDIDATES = ["Y_COR","Y_COORD","YCOORD","Y","NORTHING","Y_COORDINATE","YCORD","LAT","LATITUDE"]
# ----------------------------------

def sniff_encoding(path: str) -> str:
    for enc in CANDIDATE_ENCODINGS:
        try:
            pd.read_csv(path, nrows=1, encoding=enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin1"

def canonical_uprn(val):
    """digits-only, drop leading zeros (handles 'UPRN-000123' -> '123')."""
    if pd.isna(val):
        return None
    s = str(val).strip()
    s = s.replace("UPRN-","").replace("uprn-","")
    s = re.sub(r"\D","", s)
    if not s:
        return None
    try:
        return str(int(s))
    except ValueError:
        return None

def find_col(cols, candidates):
    lut = {c.lower(): c for c in cols}
    for name in candidates:
        if name.lower() in lut:
            return lut[name.lower()]
    # fallback: substring match
    for c in cols:
        if any(name.lower() in c.lower() for name in candidates):
            return c
    return None

def find_uprn_col(path, enc):
    cols = pd.read_csv(path, nrows=0, encoding=enc).columns
    for c in cols:
        if "uprn" in c.lower():
            return c
    raise ValueError(f"No UPRN-like column found in {path}\nColumns: {list(cols)}")

def find_xy_cols(path, enc):
    cols = pd.read_csv(path, nrows=0, encoding=enc).columns
    x = find_col(cols, X_CANDIDATES)
    y = find_col(cols, Y_CANDIDATES)
    return x, y

def to_num(s):
    return pd.to_numeric(s, errors="coerce")

def looks_like_lonlat(x, y, sample=2000):
    # Heuristic: values mostly within lon/lat bounds
    df = pd.DataFrame({"x": x, "y": y}).dropna().head(sample)
    if df.empty: return False
    frac_ll = ((df["x"].abs() <= 180) & (df["y"].abs() <= 90)).mean()
    return frac_ll > 0.9

def haversine_m(lon1, lat1, lon2, lat2):
    # lon/lat degrees -> meters
    R = 6371000.0
    lon1, lat1, lon2, lat2 = map(np.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    return R * c

# --------- Load Saad ----------
enc_saad = sniff_encoding(SAAD_CSV)
uprn_col_saad = find_uprn_col(SAAD_CSV, enc_saad)
xcol_saad, ycol_saad = find_xy_cols(SAAD_CSV, enc_saad)

saad = pd.read_csv(SAAD_CSV, dtype=str, low_memory=False, encoding=enc_saad)
saad["UPRN_key"] = saad[uprn_col_saad].map(canonical_uprn)
saad_valid = saad.dropna(subset=["UPRN_key"]).copy()

if xcol_saad and ycol_saad:
    saad["X_SAAD"] = to_num(saad[xcol_saad])
    saad["Y_SAAD"] = to_num(saad[ycol_saad])
else:
    saad["X_SAAD"] = np.nan
    saad["Y_SAAD"] = np.nan

# --------- Load Paul union ----------
enc_paul = sniff_encoding(PAUL_UNION_CSV)
union = pd.read_csv(PAUL_UNION_CSV, dtype=str, low_memory=False, encoding=enc_paul)

# figure UPRN column
uprn_col_union = "UPRN_key" if "UPRN_key" in union.columns else find_uprn_col(PAUL_UNION_CSV, enc_paul)
union["UPRN_key"] = union[uprn_col_union].map(canonical_uprn)

# figure XY columns
xcol_union = "X_COR" if "X_COR" in union.columns else find_col(union.columns, X_CANDIDATES)
ycol_union = "Y_COR" if "Y_COR" in union.columns else find_col(union.columns, Y_CANDIDATES)

if xcol_union and ycol_union:
    union["X_PAUL"] = to_num(union[xcol_union])
    union["Y_PAUL"] = to_num(union[ycol_union])
else:
    union["X_PAUL"] = np.nan
    union["Y_PAUL"] = np.nan

union_valid = union.dropna(subset=["UPRN_key"]).copy()

# --------- Headline sets ----------
S = set(saad_valid["UPRN_key"].unique())
P = set(union_valid["UPRN_key"].unique())

only_saad = sorted(S - P)
only_paul = sorted(P - S)
both = S & P

# --------- Print stats ----------
print("\n=== COUNTS ===")
print(f"Saad rows total:                     {len(saad):,}")
print(f"Saad rows with valid UPRN:           {len(saad_valid):,}")
print(f"Saad unique valid UPRNs:             {len(S):,}")

print(f"Paul-union rows total:                {len(union):,}")
print(f"Paul-union rows with valid UPRN:      {len(union_valid):,}")
print(f"Paul-union unique valid UPRNs:        {len(P):,}")

print("\n=== Overlap (unique UPRNs) ===")
print(f"Intersection (Saad ∩ Paul):           {len(both):,}")
print(f"Only in Saad:                         {len(only_saad):,}")
print(f"Only in Paul:                         {len(only_paul):,}")
if len(S):
    print(f"Coverage of Saad by Paul:             {len(both)/len(S):.2%}")
if len(P):
    print(f"Coverage of Paul by Saad:             {len(both)/len(P):.2%}")

# --------- XY comparison on overlap ----------
saad_xy = saad_valid[["UPRN_key","X_SAAD","Y_SAAD"]].drop_duplicates("UPRN_key")
paul_xy = union_valid[["UPRN_key","X_PAUL","Y_PAUL"]].drop_duplicates("UPRN_key")
overlap_xy = saad_xy.merge(paul_xy, on="UPRN_key", how="inner")

both_have_xy = overlap_xy.dropna(subset=["X_SAAD","Y_SAAD","X_PAUL","Y_PAUL"]).copy()
missing_xy = overlap_xy[~overlap_xy.index.isin(both_have_xy.index)].copy()

print("\n=== XY coverage on overlap ===")
print(f"Overlap UPRNs (unique):               {len(overlap_xy):,}")
print(f"…with XY on BOTH sides:               {len(both_have_xy):,}")
print(f"…missing XY on at least one side:     {len(missing_xy):,}")

# distance
dist_method = None
if not both_have_xy.empty:
    # detect if BOTH sets look like lon/lat
    saad_ll = looks_like_lonlat(both_have_xy["X_SAAD"], both_have_xy["Y_SAAD"])
    paul_ll = looks_like_lonlat(both_have_xy["X_PAUL"], both_have_xy["Y_PAUL"])
    if saad_ll and paul_ll:
        dist_method = "haversine"
        both_have_xy["dist_m"] = haversine_m(
            both_have_xy["X_SAAD"].values, both_have_xy["Y_SAAD"].values,
            both_have_xy["X_PAUL"].values, both_have_xy["Y_PAUL"].values
        )
    else:
        dist_method = "euclidean"
        dx = both_have_xy["X_SAAD"] - both_have_xy["X_PAUL"]
        dy = both_have_xy["Y_SAAD"] - both_have_xy["Y_PAUL"]
        both_have_xy["dist_m"] = np.sqrt(dx*dx + dy*dy)

    print(f"\n=== XY distance stats ({dist_method}) ===")
    q = both_have_xy["dist_m"].quantile([0.5, 0.9, 0.95, 0.99]).to_dict()
    print(f"count: {len(both_have_xy):,}")
    print(f"median: {q[0.5]:,.2f} m | p90: {q[0.9]:,.2f} m | p95: {q[0.95]:,.2f} m | p99: {q[0.99]:,.2f} m")
    print(f"<= 1 m: {(both_have_xy['dist_m'] <= 1).mean():.2%} | <= 5 m: {(both_have_xy['dist_m'] <= 5).mean():.2%} | <= 10 m: {(both_have_xy['dist_m'] <= 10).mean():.2%}")

# --------- Write QA files ----------
out_dir = Path(SAAD_CSV).parent
pd.DataFrame({"UPRN_key": only_saad}).to_csv(out_dir / "saad_only_uprns.csv", index=False, encoding="utf-8")
pd.DataFrame({"UPRN_key": only_paul}).to_csv(out_dir / "paul_only_uprns.csv", index=False, encoding="utf-8")

if not both_have_xy.empty:
    both_have_xy.to_csv(out_dir / "uprn_overlap_xy.csv", index=False, encoding="utf-8")
if not missing_xy.empty:
    missing_xy.to_csv(out_dir / "uprn_overlap_no_xy.csv", index=False, encoding="utf-8")

print(f"\nSaved:")
print(f"  {out_dir/'saad_only_uprns.csv'}")
print(f"  {out_dir/'paul_only_uprns.csv'}")
if not both_have_xy.empty:
    print(f"  {out_dir/'uprn_overlap_xy.csv'}")
if not missing_xy.empty:
    print(f"  {out_dir/'uprn_overlap_no_xy.csv'}")
