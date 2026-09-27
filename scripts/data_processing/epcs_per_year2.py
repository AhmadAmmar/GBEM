# -*- coding: utf-8 -*-
"""
Counts records per year (and unique UPRNs per year) in the original NI EPC file,
USING ONLY the INSPECTION_DATE column.

Output:
  NI_Domestic_Master_to_01_2025_year_counts_INSPECTION_DATE.csv
"""

import pandas as pd
import re
from pathlib import Path

# ====== CONFIG ======
EPC_CSV = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-epc\NI_Domestic_Master_to 01_2025.csv"
DATE_COL = "INSPECTION_DATE"  # force this date column
OUT_SUMMARY = Path(EPC_CSV).with_name("NI_Domestic_Master_to_01_2025_year_counts_INSPECTION_DATE.csv")
CANDIDATE_ENCODINGS = ("utf-8", "utf-8-sig", "cp1252", "latin1")
# ====================

def sniff_encoding(path: str) -> str:
    for enc in CANDIDATE_ENCODINGS:
        try:
            pd.read_csv(path, nrows=1, encoding=enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin1"

def canonical_uprn(val):
    """Digits-only UPRN, drop leading zeros; handles 'UPRN-000...123'."""
    if pd.isna(val): return None
    s = str(val).strip().replace("UPRN-","").replace("uprn-","")
    s = re.sub(r"\D","", s)
    if not s: return None
    try:
        return str(int(s))
    except ValueError:
        return None

# ---- load ----
enc = sniff_encoding(EPC_CSV)
df = pd.read_csv(EPC_CSV, dtype=str, low_memory=False, encoding=enc)

if DATE_COL not in df.columns:
    raise ValueError(f"Column '{DATE_COL}' not found in file. Available columns: {list(df.columns)}")

uprn_col = next((c for c in df.columns if "uprn" in c.lower()), None)
if uprn_col is None:
    raise ValueError("No UPRN column found (expected something containing 'UPRN').")

total_rows = len(df)

# UPRN key + parse INSPECTION_DATE
df["UPRN_key"] = df[uprn_col].map(canonical_uprn)
df["_dt"] = pd.to_datetime(df[DATE_COL], errors="coerce", infer_datetime_format=True, dayfirst=True)
df["_year"] = df["_dt"].dt.year

# keep rows with parsed date
df_valid = df.dropna(subset=["_dt"]).copy()
valid_rows = len(df_valid)

# per-year counts
rows_per_year = df_valid.groupby("_year").size().rename("rows")
unique_uprn_per_year = df_valid.groupby("_year")["UPRN_key"].nunique().rename("unique_uprns")

summary = pd.concat([rows_per_year, unique_uprn_per_year], axis=1).reset_index().rename(columns={"_year":"year"})
summary = summary.sort_values("year")

# save & print
summary.to_csv(OUT_SUMMARY, index=False, encoding="utf-8")

print("\n=== Records by year (original EPC, INSPECTION_DATE) ===")
print(f"Total rows in file:                 {total_rows:,}")
print(f"Rows with parsed INSPECTION_DATE:   {valid_rows:,}")
if not summary.empty:
    y0, y1 = int(summary['year'].min()), int(summary['year'].max())
    print(f"Year span (parsed):                 {y0}–{y1}")
    print("\nYear  |  Rows  |  Unique UPRNs")
    for _, r in summary.iterrows():
        print(f"{int(r['year']):4d}  | {int(r['rows']):6d} | {int(r['unique_uprns']):12d}")

print(f"\nSummary saved → {OUT_SUMMARY}")
