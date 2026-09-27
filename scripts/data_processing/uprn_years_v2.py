# -*- coding: utf-8 -*-
"""
Count UPRNs that occur in multiple years in the EPC-with-XY v2 file.
Outputs a small CSV listing those UPRNs and prints stats.
"""

import pandas as pd, re
from pathlib import Path
from collections import defaultdict, Counter

# ========= CONFIG =========
EPC_XY_V2 = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-epc\NI_Domestic_Master_to_01_2025_with_XY_v2.csv"
OUT_MULTI = Path(EPC_XY_V2).with_name("NI_Domestic_Master_to_01_2025_with_XY_v2_multi_year_uprns.csv")
CHUNK = 200_000
CANDIDATE_ENCODINGS = ("utf-8","utf-8-sig","cp1252","latin1")
PREFERRED_DATE_COLUMNS = [
    "LODGEMENT_DATE","INSPECTION_DATE","REGISTRATION_DATE",
    "DATE_REGISTERED","DATE_OF_ASSESSMENT","DATE"
]
FORCE_DATE_COL = None  # e.g. "LODGEMENT_DATE" if you want to force it
# =========================

def sniff_encoding(path: str) -> str:
    for enc in CANDIDATE_ENCODINGS:
        try:
            pd.read_csv(path, nrows=1, encoding=enc); return enc
        except UnicodeDecodeError: pass
    return "latin1"

def find_uprn_col(path: str, enc: str) -> str:
    cols = pd.read_csv(path, nrows=0, encoding=enc).columns
    for c in cols:
        if "uprn" in c.lower(): return c
    raise ValueError(f"No UPRN-like column found in {path}")

def canonical_uprn(val):
    if pd.isna(val): return None
    s = str(val).strip().replace("UPRN-","").replace("uprn-","")
    s = re.sub(r"\D","", s)
    if not s: return None
    try: return str(int(s))  # drop leading zeros
    except ValueError: return None

def detect_best_date_column(path: str, enc: str, uprn_col: str) -> str:
    cols = pd.read_csv(path, nrows=0, encoding=enc).columns
    candidates = [c for c in cols if "date" in c.lower()]
    for p in PREFERRED_DATE_COLUMNS:
        if p in cols and p not in candidates:
            candidates.append(p)
    if not candidates:
        raise ValueError("No date-like columns found.")
    sample = pd.read_csv(path, nrows=100_000, dtype=str, low_memory=False, encoding=enc, usecols=[uprn_col]+candidates)
    scores = {}
    for c in candidates:
        ser = pd.to_datetime(sample[c], errors="coerce", infer_datetime_format=True, dayfirst=True)
        n_nonnull = sample[c].notna().sum()
        n_parsed  = ser.notna().sum()
        scores[c] = (n_parsed/n_nonnull) if n_nonnull else 0.0
    best = max(scores, key=lambda k: (scores[k], -PREFERRED_DATE_COLUMNS.index(k) if k in PREFERRED_DATE_COLUMNS else -9999, k))
    print("Date column parse rates (sample):")
    for k,v in sorted(scores.items(), key=lambda kv: -kv[1]):
        print(f"  {k}: {v:.3f}")
    print(f"=> Using date column: {best}")
    return best

# ---- main ----
enc = sniff_encoding(EPC_XY_V2)
uprn_col = find_uprn_col(EPC_XY_V2, enc)
date_col = FORCE_DATE_COL or detect_best_date_column(EPC_XY_V2, enc, uprn_col)

years_by_uprn = defaultdict(set)
row_counts = Counter()
first_date, last_date = {}, {}

total_rows = 0
valid_uprn_rows = 0
valid_uprn_and_year_rows = 0

for chunk in pd.read_csv(EPC_XY_V2, dtype=str, chunksize=CHUNK, low_memory=False, encoding=enc, usecols=[uprn_col, date_col]):
    total_rows += len(chunk)
    chunk["UPRN_key"] = chunk[uprn_col].map(canonical_uprn)

    dt = pd.to_datetime(chunk[date_col], errors="coerce", infer_datetime_format=True, dayfirst=True)
    chunk["year"] = dt.dt.year

    valid_mask = chunk["UPRN_key"].notna()
    valid_uprn_rows += int(valid_mask.sum())

    both_mask = valid_mask & chunk["year"].notna()
    valid_uprn_and_year_rows += int(both_mask.sum())

    sub = chunk.loc[both_mask, ["UPRN_key","year"]]
    for k,y in zip(sub["UPRN_key"], sub["year"]):
        years_by_uprn[k].add(int(y)); row_counts[k] += 1

    sub_dt = chunk.loc[valid_mask & dt.notna(), ["UPRN_key"]].copy()
    sub_dt["dt"] = dt[valid_mask & dt.notna()].values
    for k,d in zip(sub_dt["UPRN_key"], sub_dt["dt"]):
        if (k not in first_date) or (d < first_date[k]): first_date[k] = d
        if (k not in last_date)  or (d > last_date[k]):  last_date[k]  = d

# build output table (UPRNs with >1 distinct year)
rows = []
for k, yrs in years_by_uprn.items():
    if len(yrs) > 1:
        ys = sorted(yrs)
        rows.append({
            "UPRN_key": k,
            "years_count": len(ys),
            "years_list": ",".join(map(str, ys)),
            "min_year": ys[0],
            "max_year": ys[-1],
            "first_date": first_date.get(k),
            "last_date":  last_date.get(k),
            "row_count":  row_counts.get(k, 0)
        })
multi_df = pd.DataFrame(rows).sort_values(["years_count","row_count","UPRN_key"], ascending=[False,False,True])
multi_df.to_csv(OUT_MULTI, index=False, encoding="utf-8")

unique_with_year = sum(1 for s in years_by_uprn.values() if len(s) >= 1)
multi_n = len(multi_df)

print("\n========= UPRN multi-year check (XY v2) =========")
print(f"EPC (XY v2) total rows:                    {total_rows:,}")
print(f"Rows with valid UPRN:                      {valid_uprn_rows:,}")
print(f"Rows with valid UPRN + parsed date:        {valid_uprn_and_year_rows:,}")
print(f"Unique UPRNs with at least one year:       {unique_with_year:,}")
print(f"UPRNs spanning multiple years:             {multi_n:,}")
if unique_with_year:
    print(f"Share of UPRNs that are multi-year:        {multi_n/unique_with_year:.2%}")
print(f"Results CSV (multi-year UPRNs):            {OUT_MULTI}")
