# -*- coding: utf-8 -*-
"""
Check multi-year UPRNs inside Belfast footprints.
Outputs:
  - *_in_footprints_multi_year_uprns.csv     (one row per multi-year UPRN)
  - *_in_footprints_multi_year_full_rows.csv (all EPC rows for those UPRNs)
"""

import pandas as pd, re
from pathlib import Path

# ====== CONFIG ======
IN_CSV = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-epc\NI_Domestic_Master_to_01_2025_with_XY_v2_in_footprints.csv"
OUT_MULTI_UPRN = Path(IN_CSV).with_name("NI_Domestic_Master_to_01_2025_with_XY_v2_in_footprints_multi_year_uprns.csv")
OUT_MULTI_ROWS = Path(IN_CSV).with_name("NI_Domestic_Master_to_01_2025_with_XY_v2_in_footprints_multi_year_full_rows.csv")
FORCE_DATE_COL = None  # e.g. "LODGEMENT_DATE" to force a specific column
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
    try: return str(int(s))  # drops leading zeros
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
    print("Date column parse rates:")
    for k,v in sorted(scores.items(), key=lambda kv: -kv[1]):
        print(f"  {k}: {v:.3f}")
    print(f"=> Using date column: {best}")
    return best

# ---- load ----
df = pd.read_csv(IN_CSV, dtype=str, low_memory=False)
total_rows = len(df)

# UPRN
uprn_col = next((c for c in df.columns if "uprn" in c.lower()), None)
if uprn_col is None:
    raise ValueError("No UPRN column found.")
df["UPRN_key"] = df[uprn_col].map(canonical_uprn)
df = df[df["UPRN_key"].notna()].copy()
valid_uprn_rows = len(df)

# Date → year
date_col = FORCE_DATE_COL or detect_best_date_column(df)
df["_dt"]   = pd.to_datetime(df[date_col], errors="coerce", infer_datetime_format=True, dayfirst=True)
df["_year"] = df["_dt"].dt.year
df_valid = df.dropna(subset=["_dt"]).copy()
valid_uprn_and_date = len(df_valid)

# Multi-year detection
years_per = df_valid.groupby("UPRN_key")["_year"].nunique()
multi_keys = years_per[years_per > 1].index
multi_up = (
    pd.DataFrame({
        "UPRN_key": multi_keys,
        "years_count": years_per.loc[multi_keys].values
    })
    .assign(
        years_list=lambda t: t["UPRN_key"].map(
            df_valid.groupby("UPRN_key")["_year"].apply(lambda s: ",".join(map(str, sorted(set(s)))))
        ),
        min_year=lambda t: t["years_list"].str.split(",").apply(lambda xs: int(xs[0])),
        max_year=lambda t: t["years_list"].str.split(",").apply(lambda xs: int(xs[-1]))
    )
    .sort_values(["years_count","UPRN_key"], ascending=[False, True])
)

# Save outputs
multi_up.to_csv(OUT_MULTI_UPRN, index=False, encoding="utf-8")
multi_rows = df_valid[df_valid["UPRN_key"].isin(multi_keys)].drop(columns=["_dt"])
multi_rows.to_csv(OUT_MULTI_ROWS, index=False, encoding="utf-8")

# Stats
unique_with_year = df_valid["UPRN_key"].nunique()
multi_n = len(multi_up)

print("\n========= UPRN multi-year check (XY v2 IN footprints) =========")
print(f"Rows (input):                              {total_rows:,}")
print(f"Rows with valid UPRN:                      {valid_uprn_rows:,}")
print(f"Rows with valid UPRN + parsed date:        {valid_uprn_and_date:,}")
print(f"Unique UPRNs with at least one year:       {unique_with_year:,}")
print(f"UPRNs spanning multiple years:             {multi_n:,}")
if unique_with_year:
    print(f"Share of UPRNs that are multi-year:        {multi_n/unique_with_year:.2%}")
print(f"Results (UPRN summary):                    {OUT_MULTI_UPRN}")
print(f"Results (full rows for multi-year UPRNs):  {OUT_MULTI_ROWS}")
