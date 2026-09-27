# -*- coding: utf-8 -*-
r"""
Combine Paul's 'uprn_union_with_xy.csv' with Saad's 'uprn_saad_clean.csv'
into a single, clean union with deduped UPRNs and consistent XY.

Priority: keep Paul's XY when the same UPRN appears in both.
Write overlaps with >1 m XY difference to 'uprn_overlap_conflicts.csv'.
"""

import pandas as pd, re, numpy as np
from pathlib import Path

# --------- CONFIG ---------
PAUL_CSV = r"D:\OneDrive - Ulster University\PhD\data\belfast\uprn\BELFS_20250829_F\uprn_union_with_xy.csv"
SAAD_CSV = r"D:\OneDrive - Ulster University\PhD\data\belfast\uprn\uprn_saad_clean.csv"

OUT_UNION = Path(PAUL_CSV).with_name("uprn_union_with_xy_v2.csv")
OUT_CONFLICTS = Path(PAUL_CSV).with_name("uprn_overlap_conflicts.csv")

# meters; rows with distance > TOL go to conflicts file
CONFLICT_TOL_M = 1.0

ENC = ("utf-8","utf-8-sig","cp1252","latin1")
X_CANDS = ["X_COR","X_COORD","XCOORD","X","EASTING","X_COORDINATE","XCORD","LON","LONGITUDE"]
Y_CANDS = ["Y_COR","Y_COORD","YCOORD","Y","NORTHING","Y_COORDINATE","YCORD","LAT","LATITUDE"]
# -------------------------

def sniff(p):
    for e in ENC:
        try: pd.read_csv(p, nrows=1, encoding=e); return e
        except UnicodeDecodeError: pass
    return "latin1"

def find_col(cols, needles):
    lut = {c.lower(): c for c in cols}
    for n in needles:
        if n.lower() in lut: return lut[n.lower()]
    for c in cols:
        if any(n.lower() in c.lower() for n in needles): return c
    return None

def find_uprn_col(path, enc):
    cols = pd.read_csv(path, nrows=0, encoding=enc).columns
    for c in cols:
        if "uprn" in c.lower(): return c
    raise ValueError(f"No UPRN-like column in {path}")

def canonical_key(val):
    """digits-only, drop leading zeros (for joining)."""
    if pd.isna(val): return None
    s = re.sub(r"\D","", str(val))
    if not s: return None
    try: return str(int(s))
    except ValueError: return None

def to_num(s): return pd.to_numeric(s, errors="coerce")

# ----- Load Paul -----
enc_p = sniff(PAUL_CSV)
paul = pd.read_csv(PAUL_CSV, dtype=str, low_memory=False, encoding=enc_p)

uprn_p = "UPRN_norm" if "UPRN_norm" in paul.columns else find_uprn_col(PAUL_CSV, enc_p)
x_p = "X_COR" if "X_COR" in paul.columns else find_col(paul.columns, X_CANDS)
y_p = "Y_COR" if "Y_COR" in paul.columns else find_col(paul.columns, Y_CANDS)
if not (uprn_p and x_p and y_p):
    raise ValueError("Paul CSV missing UPRN or X/Y columns.")

paul["UPRN_key"] = paul[uprn_p].map(canonical_key)
paul["X_COR"] = to_num(paul[x_p]); paul["Y_COR"] = to_num(paul[y_p])
paul = paul.dropna(subset=["UPRN_key","X_COR","Y_COR"]).copy()
paul = paul.drop_duplicates(subset=["UPRN_key"], keep="first")
paul["xy_source"] = "paul"
paul = paul[["UPRN_key","X_COR","Y_COR","xy_source"]]

# ----- Load Saad clean -----
enc_s = sniff(SAAD_CSV)
saad = pd.read_csv(SAAD_CSV, dtype=str, low_memory=False, encoding=enc_s)

# Saad clean already has UPRN_key/X_COR/Y_COR; verify
uprn_s = "UPRN_key" if "UPRN_key" in saad.columns else find_uprn_col(SAAD_CSV, enc_s)
if uprn_s != "UPRN_key":
    saad["UPRN_key"] = saad[uprn_s].map(canonical_key)
x_s = "X_COR" if "X_COR" in saad.columns else find_col(saad.columns, X_CANDS)
y_s = "Y_COR" if "Y_COR" in saad.columns else find_col(saad.columns, Y_CANDS)
saad["X_COR"] = to_num(saad[x_s]); saad["Y_COR"] = to_num(saad[y_s])
saad = saad.dropna(subset=["UPRN_key","X_COR","Y_COR"]).copy()
saad = saad.drop_duplicates(subset=["UPRN_key"], keep="first")
saad["xy_source"] = "saad"
saad = saad[["UPRN_key","X_COR","Y_COR","xy_source"]]

# ----- Overlap analysis (for QA) -----
overlap = paul.merge(saad, on="UPRN_key", suffixes=("_paul","_saad"), how="inner")
if not overlap.empty:
    overlap["dist_m"] = np.sqrt((overlap["X_COR_paul"]-overlap["X_COR_saad"])**2 +
                                (overlap["Y_COR_paul"]-overlap["Y_COR_saad"])**2)
    conflicts = overlap[overlap["dist_m"] > CONFLICT_TOL_M].copy()
    if not conflicts.empty:
        conflicts.to_csv(OUT_CONFLICTS, index=False, encoding="utf-8")
        print(f"[QA] Conflicts (> {CONFLICT_TOL_M} m): {len(conflicts):,} -> {OUT_CONFLICTS}")
else:
    print("[QA] No overlap between Paul and Saad keys.")

# ----- Build union: keep Paul where overlap; append Saad-only -----
keys_paul = set(paul["UPRN_key"])
saad_only = saad[~saad["UPRN_key"].isin(keys_paul)].copy()

union = pd.concat([paul, saad_only], ignore_index=True)

# Optional: a 'sources' column noting if an ID appears in both
sources_map = {k:"paul" for k in keys_paul}
for k in saad["UPRN_key"]:
    sources_map[k] = "paul;saad" if (k in keys_paul) else "saad"
union["sources"] = union["UPRN_key"].map(sources_map)

# Also publish a user-facing UPRN string (no leading zeros)
union = union.rename(columns={"UPRN_key":"UPRN_norm"})[["UPRN_norm","X_COR","Y_COR","xy_source","sources"]]

# ----- Save -----
union.to_csv(OUT_UNION, index=False, encoding="utf-8")

print("\n=== Summary ===")
print(f"Paul uniques:      {len(keys_paul):,}")
print(f"Saad uniques:      {saad['UPRN_norm'].nunique() if 'UPRN_norm' in saad.columns else len(saad)}")
print(f"Overlap keys:      {len(overlap):,}")
print(f"Saad-only appended:{len(saad_only):,}")
print(f"Union total:       {len(union):,}")
print(f"Output union:      {OUT_UNION}")
