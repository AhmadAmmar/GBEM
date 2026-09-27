# -*- coding: utf-8 -*-
"""
Join NI EPC CSV to union UPRN-with-XY CSV using a canonical UPRN key
(digits-only, no leading zeros). Writes EPC rows with matched XY only.

Output: NI_Domestic_Master_to_01_2025_with_XY.csv
"""

import pandas as pd
import re
from pathlib import Path

# =============== CONFIG ===============
EPC_CSV = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-epc\NI_Domestic_Master_to 01_2025.csv"
UNION_XY_CSV = r"D:\OneDrive - Ulster University\PhD\data\belfast\uprn\BELFS_20250829_F\uprn_union_with_xy.csv"

OUT_MATCHED = Path(EPC_CSV).with_name("NI_Domestic_Master_to_01_2025_with_XY.csv")
OUT_UNMATCHED_SAMPLE = Path(EPC_CSV).with_name("NI_Domestic_Master_to_01_2025_no_XY_sample.csv")

CHUNK = 200_000
CANDIDATE_ENCODINGS = ("utf-8", "utf-8-sig", "cp1252", "latin1")
# =====================================

def sniff_encoding(path: str) -> str:
    for enc in CANDIDATE_ENCODINGS:
        try:
            pd.read_csv(path, nrows=1, encoding=enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin1"

def find_uprn_col(path: str, encoding: str) -> str:
    cols = pd.read_csv(path, nrows=0, encoding=encoding).columns
    for c in cols:
        if "uprn" in c.lower():
            return c
    raise ValueError(f"No UPRN-like column found in {path}\nColumns: {list(cols)}")

def canonical_uprn(val):
    """
    Canonical UPRN key for joining across sources:
    - strip 'UPRN-' and any non-digits
    - drop leading zeros (e.g., '000185003143' -> '185003143')
    Returns None if empty after cleaning.
    """
    if pd.isna(val):
        return None
    s = str(val).strip()
    # remove common label and any non-digits
    s = s.replace("UPRN-", "").replace("uprn-", "")
    s = re.sub(r"\D", "", s)
    if not s:
        return None
    # drop leading zeros by round-tripping through int
    # (safe: Python int is unbounded)
    try:
        return str(int(s))
    except ValueError:
        return None

# --- Load union of UPRNs with XY (dedupe to be safe) ---
union_enc = sniff_encoding(UNION_XY_CSV)
union = pd.read_csv(UNION_XY_CSV, dtype=str, low_memory=False, encoding=union_enc)

# Detect columns
# Prefer existing normalized column, but still rebuild our canonical key
uprn_union_col = next((c for c in union.columns if c.lower() == "uprn_norm"), None)
if uprn_union_col is None:
    uprn_union_col = next((c for c in union.columns if "uprn" in c.lower()), None)
    if uprn_union_col is None:
        raise ValueError("No UPRN column in union XY file.")

xcol = "X_COR" if "X_COR" in union.columns else next((c for c in union.columns if c.upper().startswith("X")), None)
ycol = "Y_COR" if "Y_COR" in union.columns else next((c for c in union.columns if c.upper().startswith("Y")), None)
if not xcol or not ycol:
    raise ValueError("Could not find X/Y columns in union XY file.")

# Build canonical key and keep rows with both coords
union["UPRN_key"] = union[uprn_union_col].map(canonical_uprn)
union = union.dropna(subset=["UPRN_key", xcol, ycol]).copy()
union = union.drop_duplicates(subset=["UPRN_key"])

keep_cols = ["UPRN_key", xcol, ycol] + (["xy_source"] if "xy_source" in union.columns else [])
union = union[keep_cols]
union = union.rename(columns={xcol: "X_COR", ycol: "Y_COR"})

print(f"Union UPRNs with XY: {len(union):,}")

# --- Stream EPC in chunks, match by canonical UPRN, write matched rows ---
epc_enc = sniff_encoding(EPC_CSV)
epc_uprn_col = find_uprn_col(EPC_CSV, epc_enc)

first_write = True
unmatched_samples = []
matched_rows = 0
total_rows = 0

for chunk in pd.read_csv(EPC_CSV, dtype=str, chunksize=CHUNK, low_memory=False, encoding=epc_enc):
    total_rows += len(chunk)

    # Canonical key on EPC UPRN (handles 'UPRN-000...123')
    chunk["UPRN_key"] = chunk[epc_uprn_col].map(canonical_uprn)

    # Inner join to union on canonical key
    merged = chunk.merge(union, on="UPRN_key", how="inner")

    # Optional: keep the canonical key for debugging; or drop it:
    merged = merged  # keep
    # merged = merged.drop(columns=["UPRN_key"], errors="ignore")  # or drop

    if not merged.empty:
        matched_rows += len(merged)
        merged.to_csv(OUT_MATCHED, index=False, mode="w" if first_write else "a",
                      header=first_write, encoding="utf-8")
        first_write = False

    # QA sample of unmatched
    if len(unmatched_samples) < 5000:
        um = chunk[chunk["UPRN_key"].isna() | ~chunk["UPRN_key"].isin(union["UPRN_key"])]
        take = 5000 - sum(len(x) for x in unmatched_samples)
        if take > 0 and not um.empty:
            unmatched_samples.append(um.head(take).drop(columns=["UPRN_key"]))

# Save unmatched QA sample
if unmatched_samples:
    pd.concat(unmatched_samples, ignore_index=True).to_csv(OUT_UNMATCHED_SAMPLE, index=False, encoding="utf-8")

print(f"Total EPC rows read:       {total_rows:,}")
print(f"Matched & written rows:    {matched_rows:,}")
print(f"Output (matched only):     {OUT_MATCHED}")
if Path(OUT_UNMATCHED_SAMPLE).exists():
    print(f"Unmatched sample (QA):     {OUT_UNMATCHED_SAMPLE}")
