# -*- coding: utf-8 -*-
r"""
Create: NI_Domestic_Master_to_01_2025_with_XY_v2.csv
EPC rows joined to uprn_union_with_xy_v2.csv on a canonical UPRN key.
Keeps ONLY rows with coordinates.
"""

import pandas as pd, re
from pathlib import Path

# ============ CONFIG ============
EPC_CSV       = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-epc\NI_Domestic_Master_to 01_2025.csv"
UNION_V2_CSV  = r"D:\OneDrive - Ulster University\PhD\data\belfast\uprn\BELFS_20250829_F\uprn_union_with_xy_v2.csv"

OUT_MATCHED   = Path(EPC_CSV).with_name("NI_Domestic_Master_to_01_2025_with_XY_v2.csv")
OUT_UNMATCHED = Path(EPC_CSV).with_name("NI_Domestic_Master_to_01_2025_no_XY_sample_v2.csv")

CHUNK = 200_000
CANDIDATE_ENCODINGS = ("utf-8","utf-8-sig","cp1252","latin1")
# ===============================

def sniff_encoding(path: str) -> str:
    for enc in CANDIDATE_ENCODINGS:
        try:
            pd.read_csv(path, nrows=1, encoding=enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin1"

def find_uprn_col(path: str, enc: str) -> str:
    cols = pd.read_csv(path, nrows=0, encoding=enc).columns
    for c in cols:
        if "uprn" in c.lower():
            return c
    raise ValueError(f"No UPRN-like column in {path}\nColumns: {list(cols)}")

def canonical_uprn(val):
    """digits-only, drop leading zeros; handles 'UPRN-000123' etc."""
    if pd.isna(val): return None
    s = str(val).strip().replace("UPRN-","").replace("uprn-","")
    s = re.sub(r"\D","", s)
    if not s: return None
    try:
        return str(int(s))
    except ValueError:
        return None

# --- Load union v2 and prep join table ---
union_enc = sniff_encoding(UNION_V2_CSV)
union = pd.read_csv(UNION_V2_CSV, dtype=str, low_memory=False, encoding=union_enc)

# Build join key from UPRN_key (or any UPRN-like column)
uprn_union_col = "UPRN_key" if "UPRN_key" in union.columns else find_uprn_col(UNION_V2_CSV, union_enc)
union["UPRN_key"] = union[uprn_union_col].map(canonical_uprn)

# Keep only rows with both coords & a key
need_cols = ["UPRN_key", "X_COR", "Y_COR"]
missing = [c for c in need_cols if c not in union.columns]
if missing:
    raise ValueError(f"Missing columns in union v2: {missing}")

union = union.dropna(subset=["UPRN_key","X_COR","Y_COR"]).drop_duplicates(subset=["UPRN_key"])

keep_cols = ["UPRN_key","X_COR","Y_COR"]
# carry provenance if present
for extra in ("xy_source","sources"):
    if extra in union.columns:
        keep_cols.append(extra)

union = union[keep_cols]
print(f"Union v2 keys with XY: {len(union):,}")

# --- Stream EPC, join, and write NEW file ---
epc_enc = sniff_encoding(EPC_CSV)
epc_uprn_col = find_uprn_col(EPC_CSV, epc_enc)

first_write = True
total_rows = 0
matched_rows = 0
matched_unique_keys = set()
unmatched_samples = []

for chunk in pd.read_csv(EPC_CSV, dtype=str, chunksize=CHUNK, low_memory=False, encoding=epc_enc):
    total_rows += len(chunk)
    chunk["UPRN_key"] = chunk[epc_uprn_col].map(canonical_uprn)

    merged = chunk.merge(union, on="UPRN_key", how="inner")

    if not merged.empty:
        matched_rows += len(merged)
        matched_unique_keys.update(merged["UPRN_key"].dropna().unique())
        merged.to_csv(OUT_MATCHED, index=False, mode="w" if first_write else "a",
                      header=first_write, encoding="utf-8")
        first_write = False

    # Save a small sample of unmatched for QA
    if len(unmatched_samples) < 5000:
        um = chunk[chunk["UPRN_key"].isna() | ~chunk["UPRN_key"].isin(union["UPRN_key"])]
        take = 5000 - sum(len(x) for x in unmatched_samples)
        if take > 0 and not um.empty:
            unmatched_samples.append(um.head(take).drop(columns=["UPRN_key"]))

if unmatched_samples:
    pd.concat(unmatched_samples, ignore_index=True).to_csv(OUT_UNMATCHED, index=False, encoding="utf-8")

print("\n=== Done ===")
print(f"Total EPC rows read:         {total_rows:,}")
print(f"Matched EPC rows written:    {matched_rows:,}")
print(f"Matched unique UPRNs (keys): {len(matched_unique_keys):,}")
print(f"Output (matched only):       {OUT_MATCHED}")
if OUT_UNMATCHED.exists():
    print(f"Unmatched sample (QA):       {OUT_UNMATCHED}")
