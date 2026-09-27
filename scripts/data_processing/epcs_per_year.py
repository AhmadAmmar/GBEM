# -*- coding: utf-8 -*-
"""
Counts records per year (and unique UPRNs per year) in the IN-FOOTPRINTS EPC file.
Saves a summary CSV and prints stats.
"""

import pandas as pd, re
from pathlib import Path

# ====== CONFIG ======
IN_CSV = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-epc\NI_Domestic_Master_to_01_2025_with_XY_v2_in_footprints.csv"
OUT_SUMMARY = Path(IN_CSV).with_name("NI_Domestic_Master_to_01_2025_with_XY_v2_in_footprints_year_counts.csv")
FORCE_DATE_COL = None  # e.g. "LODGEMENT_DATE" if you want to force a particular date column
PREFERRED_DATE_COLUMNS = [
    "LODGEMENT_DATE","INSPECTION_DATE","REGISTRATION_DATE",
    "DATE_REGISTERED","DATE_OF_ASSESSMENT","DATE"
]
# ====================

def canonical_uprn(val):
    if pd.isna(val): return None
    s = str(val).strip().replace("UPRN-","").replace("uprn-","")
    s = re.sub(r"\D","", s)
    if not s: return None
    try: return str(int(s))
    except ValueError: return None

def detect_best_date_column(df: pd.DataFrame) -> str:
    cands = [c for c in df.columns if "date" in c.lower()]
    for p in PREFERRED_DATE_COLUMNS:
        if p in df.columns and p not in cands:
            cands.append(p)
    if not cands:
        raise ValueError("No date-like columns found.")
    scores = {}
    for c in cands:
        ser = pd.to_datetime(df[c], errors="coerce", infer_datetime_format=True, dayfirst=True)
        n_nonnull = df[c].notna().sum()
        n_parsed  = ser.notna().sum()
        scores[c] = (n_parsed/n_nonnull) if n_nonnull else 0.0
    best = max(scores, key=lambda k: (scores[k],
                                      -PREFERRED_DATE_COLUMNS.index(k) if k in PREFERRED_DATE_COLUMNS else -9999,
                                      k))
    print("Date column parse rates (sample on full file):")
    for k,v in sorted(scores.items(), key=lambda kv: -kv[1]):
        print(f"  {k}: {v:.3f}")
    print(f"=> Using date column: {best}")
    return best

# ---- load ----
df = pd.read_csv(IN_CSV, dtype=str, low_memory=False)
total_rows = len(df)

# UPRN key
uprn_col = next((c for c in df.columns if "uprn" in c.lower()), None)
if uprn_col is None:
    raise ValueError("UPRN column not found.")
df["UPRN_key"] = df[uprn_col].map(canonical_uprn)

# Date → year
date_col = FORCE_DATE_COL or detect_best_date_column(df)
df["_dt"]   = pd.to_datetime(df[date_col], errors="coerce", infer_datetime_format=True, dayfirst=True)
df["_year"] = df["_dt"].dt.year

df_valid = df.dropna(subset=["_dt"]).copy()
valid_rows = len(df_valid)

# Counts
rows_per_year = df_valid.groupby("_year").size().rename("rows")
unique_uprn_per_year = df_valid.groupby("_year")["UPRN_key"].nunique().rename("unique_uprns")

summary = pd.concat([rows_per_year, unique_uprn_per_year], axis=1).reset_index().rename(columns={"_year":"year"})
summary = summary.sort_values("year")

# Save
summary.to_csv(OUT_SUMMARY, index=False, encoding="utf-8")

# Print
print("\n=== Records by year (in-footprints) ===")
print(f"Total rows in file:                 {total_rows:,}")
print(f"Rows with parsed date:              {valid_rows:,}")
if not summary.empty:
    y0, y1 = int(summary['year'].min()), int(summary['year'].max())
    print(f"Year span (parsed):                 {y0}–{y1}")
print("\nYear  |  Rows  |  Unique UPRNs")
for _, r in summary.iterrows():
    print(f"{int(r['year']):4d}  | {int(r['rows']):6d} | {int(r['unique_uprns']):12d}")

print(f"\nSummary saved → {OUT_SUMMARY}")
