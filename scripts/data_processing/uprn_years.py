# -*- coding: utf-8 -*-
"""
Find UPRNs that occur in multiple years in the NI EPC file.
Outputs a CSV listing those UPRNs and prints stats.
"""

import pandas as pd
import re
from pathlib import Path
from collections import defaultdict, Counter

# ============== CONFIG ==============
EPC_CSV = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-epc\NI_Domestic_Master_to 01_2025.csv"
OUT_MULTI = Path(EPC_CSV).with_name("NI_Domestic_Master_to_01_2025_multi_year_uprns.csv")

CHUNK = 200_000
CANDIDATE_ENCODINGS = ("utf-8", "utf-8-sig", "cp1252", "latin1")

# Known EPC date-ish field names to prefer if ties
PREFERRED_DATE_COLUMNS = [
    "LODGEMENT_DATE", "INSPECTION_DATE", "REGISTRATION_DATE",
    "DATE_REGISTERED", "DATE_OF_ASSESSMENT", "DATE"
]
# ===================================

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
    """Digits-only UPRN key (drops leading zeros)."""
    if pd.isna(val):
        return None
    s = str(val).strip().replace("UPRN-","").replace("uprn-","")
    s = re.sub(r"\D","", s)
    if not s:
        return None
    try:
        return str(int(s))
    except ValueError:
        return None

def detect_best_date_column(path: str, encoding: str, uprn_col: str) -> str:
    # Find candidates from header
    cols = pd.read_csv(path, nrows=0, encoding=encoding).columns
    candidates = [c for c in cols if "date" in c.lower()]
    # also include preferred ones even if they don't contain 'date' exactly
    for p in PREFERRED_DATE_COLUMNS:
        if p in cols and p not in candidates:
            candidates.append(p)
    if not candidates:
        raise ValueError("No date-like columns found (none containing 'date').")

    # Sample a chunk to score candidates by parse success rate
    sample = pd.read_csv(path, nrows=100_000, dtype=str, low_memory=False, encoding=encoding, usecols=[uprn_col] + candidates)
    scores = {}
    for c in candidates:
        ser = pd.to_datetime(sample[c], errors="coerce", infer_datetime_format=True, dayfirst=True)
        n_nonnull = sample[c].notna().sum()
        n_parsed = ser.notna().sum()
        scores[c] = (n_parsed / n_nonnull) if n_nonnull else 0.0

    # Choose best by score; tie-break by preferred list order, then by name
    best = max(scores, key=lambda k: (scores[k], -PREFERRED_DATE_COLUMNS.index(k) if k in PREFERRED_DATE_COLUMNS else -9999, k))
    print("Date column candidate parse rates:")
    for k, v in sorted(scores.items(), key=lambda kv: -kv[1]):
        print(f"  {k}: {v:.3f}")
    print(f"=> Using date column: {best}")
    return best

# ---------- Main ----------
enc = sniff_encoding(EPC_CSV)
uprn_col = find_uprn_col(EPC_CSV, enc)
date_col = detect_best_date_column(EPC_CSV, enc, uprn_col)

# Accumulators
years_by_uprn = defaultdict(set)
first_date = {}
last_date = {}
row_counts = Counter()

total_rows = 0
valid_uprn_rows = 0
valid_uprn_and_year_rows = 0

for chunk in pd.read_csv(EPC_CSV, dtype=str, chunksize=CHUNK, low_memory=False, encoding=enc, usecols=[uprn_col, date_col]):
    total_rows += len(chunk)
    # Normalize UPRN
    chunk["UPRN_key"] = chunk[uprn_col].map(canonical_uprn)

    # Parse date → year
    dt = pd.to_datetime(chunk[date_col], errors="coerce", infer_datetime_format=True, dayfirst=True)
    chunk["year"] = dt.dt.year

    # Update counts
    valid_mask = chunk["UPRN_key"].notna()
    valid_uprn_rows += int(valid_mask.sum())

    both_mask = valid_mask & chunk["year"].notna()
    valid_uprn_and_year_rows += int(both_mask.sum())

    # Aggregate
    sub = chunk.loc[both_mask, ["UPRN_key", "year"]]
    for k, y in zip(sub["UPRN_key"], sub["year"]):
        years_by_uprn[k].add(int(y))
        row_counts[k] += 1

    # Track first/last date for each UPRN (based on parsed dt)
    sub_dt = chunk.loc[valid_mask & dt.notna(), ["UPRN_key"]].copy()
    sub_dt["dt"] = dt[valid_mask & dt.notna()].values
    for k, d in zip(sub_dt["UPRN_key"], sub_dt["dt"]):
        if (k not in first_date) or (d < first_date[k]):
            first_date[k] = d
        if (k not in last_date) or (d > last_date[k]):
            last_date[k] = d

# Build output DataFrame for UPRNs with >1 year
multi = []
for k, yrs in years_by_uprn.items():
    if len(yrs) > 1:
        ys = sorted(yrs)
        multi.append({
            "UPRN_key": k,
            "years_count": len(ys),
            "years_list": ",".join(str(x) for x in ys),
            "min_year": ys[0],
            "max_year": ys[-1],
            "first_date": first_date.get(k),
            "last_date": last_date.get(k),
            "row_count": row_counts.get(k, 0)
        })

multi_df = pd.DataFrame(multi).sort_values(["years_count","row_count","UPRN_key"], ascending=[False, False, True])

# Save
multi_df.to_csv(OUT_MULTI, index=False, encoding="utf-8")

# Stats
unique_uprns_with_year = sum(1 for k, s in years_by_uprn.items() if len(s) >= 1)
multi_uprns = len(multi_df)
single_uprn = unique_uprns_with_year - multi_uprns

print("\n========= UPRN multi-year check =========")
print(f"EPC total rows:                           {total_rows:,}")
print(f"Rows with valid UPRN:                     {valid_uprn_rows:,}")
print(f"Rows with valid UPRN + parsed date:       {valid_uprn_and_year_rows:,}")
print(f"Unique UPRNs with at least one year:      {unique_uprns_with_year:,}")
print(f"UPRNs spanning multiple years:            {multi_uprns:,}")
if unique_uprns_with_year:
    print(f"Share of UPRNs that are multi-year:       {multi_uprns/unique_uprns_with_year:.2%}")
print(f"Single-year UPRNs:                        {single_uprn:,}")
print(f"Results (multi-year UPRNs):               {OUT_MULTI}")
