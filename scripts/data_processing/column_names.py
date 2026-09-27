# -*- coding: utf-8 -*-
"""
Quick schema peek:
- Reads the original NI EPC CSV and the original Belfast building footprints SHP
- Prints row counts, CRS (for polygons), geometry types, and FULL column lists
"""

import pandas as pd
import geopandas as gpd
from pathlib import Path

# ---------- CONFIG: update only if paths change ----------
EPC_CSV = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-epc\NI_Domestic_Master_to 01_2025.csv"
FOOTPRINTS_SHP = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-buildings\Belfast_Building_Footprints.shp"
# --------------------------------------------------------

CANDIDATE_ENCODINGS = ("utf-8", "utf-8-sig", "cp1252", "latin1")

def sniff_encoding(path: str) -> str:
    for enc in CANDIDATE_ENCODINGS:
        try:
            pd.read_csv(path, nrows=1, encoding=enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin1"

def print_section(title: str):
    print("\n" + "="*len(title))
    print(title)
    print("="*len(title))

def main():
    # ---------- EPC CSV ----------
    print_section("ORIGINAL EPC CSV")
    if not Path(EPC_CSV).exists():
        raise FileNotFoundError(f"EPC file not found: {EPC_CSV}")

    enc = sniff_encoding(EPC_CSV)
    epc_head = pd.read_csv(EPC_CSV, nrows=5, dtype=str, low_memory=False, encoding=enc)
    epc_cols = list(epc_head.columns)

    # if the file is very large, just read header to get column names
    print(f"Path: {EPC_CSV}")
    print(f"Detected encoding: {enc}")
    # Optional: try get total rows fast (without loading full) -> read in chunks and sum
    total_rows = 0
    for chunk in pd.read_csv(EPC_CSV, chunksize=250_000, dtype=str, low_memory=False, encoding=enc, usecols=[epc_cols[0]]):
        total_rows += len(chunk)
    print(f"Rows (approx): {total_rows:,}")
    print(f"Columns ({len(epc_cols)}):")
    for i, c in enumerate(epc_cols, start=1):
        print(f"  {i:>3}. {c}")

    # Try to highlight UPRN/date-ish columns
    uprn_like = [c for c in epc_cols if "uprn" in c.lower()]
    date_like = [c for c in epc_cols if "date" in c.lower()]
    if uprn_like:
        print(f"\nUPRN-like columns: {uprn_like}")
    if date_like:
        print(f"Date-like columns: {date_like}")

    # ---------- BUILDING FOOTPRINTS SHP ----------
    print_section("ORIGINAL BUILDING FOOTPRINTS SHP")
    if not Path(FOOTPRINTS_SHP).exists():
        raise FileNotFoundError(f"Footprints shapefile not found: {FOOTPRINTS_SHP}")

    foot = gpd.read_file(FOOTPRINTS_SHP)
    print(f"Path: {FOOTPRINTS_SHP}")
    print(f"Features: {len(foot):,}")
    print(f"CRS: {foot.crs}")
    if "geometry" in foot:
        try:
            geom_types = foot.geom_type.value_counts()
            print("Geometry types:")
            for gt, n in geom_types.items():
                print(f"  {gt}: {n:,}")
        except Exception:
            pass

    foot_cols = [c for c in foot.columns if c != "geometry"]
    print(f"Attribute columns ({len(foot_cols)}):")
    for i, c in enumerate(foot_cols, start=1):
        print(f"  {i:>3}. {c}")

    # Common polygon ID candidates
    id_cands = ["poly_id", "POLY_ID", "OBJECTID", "OBJECTID_1", "FID", "ID", "id"]
    present_ids = [c for c in id_cands if c in foot_cols]
    if present_ids:
        print(f"\nPossible polygon ID columns found: {present_ids}")
    else:
        print("\nNo common polygon ID field found — consider adding a stable ID before exports.")

if __name__ == "__main__":
    main()
