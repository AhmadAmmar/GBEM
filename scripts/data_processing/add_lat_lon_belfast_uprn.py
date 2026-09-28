# -*- coding: utf-8 -*-
"""
Add X/Y coordinates to uprn_union_list.csv by matching UPRNs
from BELFS_20250829_F / _EXT_F / _REJ_F (in that priority).

- Keeps UPRN_key as the join key (digits-only).
- Fills only where BOTH X and Y are available.
- Writes: uprn_union_with_xy.csv and uprn_union_missing_xy.csv (QA).

Adjust FOLDER / filenames if needed.
"""

import pandas as pd
import re
from pathlib import Path
from typing import Tuple, Optional

# ------------ CONFIG ------------
FOLDER = Path(r"D:\OneDrive - Ulster University\PhD\data\belfast\uprn\BELFS_20250829_F")

UNION_FILE = FOLDER / "uprn_union_list.csv"  # produced earlier (has UPRN_key)

FILE_PRIORITY = [
    "BELFS_20250829_F.csv",
    "BELFS_20250829_EXT_F.csv",
    "BELFS_20250829_REJ_F.csv",
]

# If different files/columns, add aliases here:
X_CANDIDATES = ["X_COR", "X_COORD", "XCOORD", "X", "EASTING", "X_COORDINATE", "XCORD"]
Y_CANDIDATES = ["Y_COR", "Y_COORD", "YCOORD", "Y", "NORTHING", "Y_COORDINATE", "YCORD"]

CANDIDATE_ENCODINGS = ("utf-8", "utf-8-sig", "cp1252", "latin1")
# --------------------------------

def sniff_encoding(path: Path) -> str:
    for enc in CANDIDATE_ENCODINGS:
        try:
            pd.read_csv(path, nrows=1, encoding=enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin1"

def find_col(cols, candidates):
    # case-insensitive lookup; returns the first match in candidates present in cols
    lut = {c.lower(): c for c in cols}
    for name in candidates:
        if name.lower() in lut:
            return lut[name.lower()]
    # fallback: try contains
    lower = {c.lower(): c for c in cols}
    for c in cols:
        for name in candidates:
            if name.lower() in c.lower():
                return c
    return None

def find_uprn_col(path: Path, encoding: str) -> str:
    cols = pd.read_csv(path, nrows=0, encoding=encoding).columns
    for c in cols:
        if "uprn" in c.lower():
            return c
    raise ValueError(f"No UPRN-like column found in {path}\nColumns: {list(cols)}")

def find_xy_cols(path: Path, encoding: str) -> Tuple[Optional[str], Optional[str]]:
    cols = pd.read_csv(path, nrows=0, encoding=encoding).columns
    x = find_col(cols, X_CANDIDATES)
    y = find_col(cols, Y_CANDIDATES)
    return x, y

def norm_uprn(val):
    """digits-only string; strips 'UPRN-' and '.0' artifacts; preserves leading zeros."""
    if pd.isna(val):
        return None
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]
    s = s.replace("UPRN-", "").replace("uprn-", "")
    s = re.sub(r"\D", "", s)
    return s or None

def to_numeric_safe(s):
    try:
        return pd.to_numeric(s, errors="coerce")
    except Exception:
        return pd.Series([pd.NA] * len(s))

# ---------- Load union list ----------
union = pd.read_csv(UNION_FILE, dtype=str, low_memory=False)
if "UPRN_key" not in union.columns:
    raise ValueError(f"'UPRN_key' not found in {UNION_FILE}. Recreate the union list first.")

# Prepare output columns
union["X_COR"] = pd.NA
union["Y_COR"] = pd.NA
union["xy_source"] = pd.NA

# ---------- Fill from sources in priority order ----------
for fname in FILE_PRIORITY:
    path = FOLDER / fname
    if not path.exists():
        print(f"[warn] Missing file skipped: {path}")
        continue
    enc = sniff_encoding(path)
    uprn_col = find_uprn_col(path, enc)
    x_col, y_col = find_xy_cols(path, enc)

    if not x_col or not y_col:
        print(f"[warn] {fname}: could not find both X and Y columns; skipping.")
        continue

    usecols = [uprn_col, x_col, y_col]
    df = pd.read_csv(path, usecols=usecols, dtype=str, low_memory=False, encoding=enc)

    # Normalize UPRN and clean XY
    df["UPRN_key"] = df[uprn_col].map(norm_uprn)
    df = df.dropna(subset=["UPRN_key"]).copy()

    # Coerce to numeric (keeps projected units as-is; no reprojection here)
    df["X_temp"] = to_numeric_safe(df[x_col])
    df["Y_temp"] = to_numeric_safe(df[y_col])

    # Keep rows where both X and Y are present
    df = df[df["X_temp"].notna() & df["Y_temp"].notna()].copy()

    # If duplicates: keep the first occurrence
    df = df.drop_duplicates(subset=["UPRN_key"], keep="first")

    # Map to union where still missing
    x_map = df.set_index("UPRN_key")["X_temp"]
    y_map = df.set_index("UPRN_key")["Y_temp"]

    missing_mask = union["X_COR"].isna() & union["Y_COR"].isna()
    if missing_mask.any():
        # candidates from this source
        x_new = union.loc[missing_mask, "UPRN_key"].map(x_map)
        y_new = union.loc[missing_mask, "UPRN_key"].map(y_map)
        fill_mask = x_new.notna() & y_new.notna()

        union.loc[missing_mask & fill_mask, "X_COR"] = x_new[fill_mask].values
        union.loc[missing_mask & fill_mask, "Y_COR"] = y_new[fill_mask].values
        union.loc[missing_mask & fill_mask, "xy_source"] = fname

        got = int(fill_mask.sum())
        print(f"{fname}: filled {got:,} UPRNs with X/Y.")

# ---------- Save outputs + QA ----------
out_all = FOLDER / "uprn_union_with_xy.csv"
union.to_csv(out_all, index=False, encoding="utf-8")
filled = union["X_COR"].notna() & union["Y_COR"].notna()
print(f"\nSaved: {out_all}")
print(f"Total UPRNs: {len(union):,} | with XY: {int(filled.sum()):,} | missing XY: {int((~filled).sum()):,}")

# Optional: export missing list for follow-up (e.g., geocoding)
missing_df = union.loc[~filled, ["UPRN_key"]].copy()
if not missing_df.empty:
    out_missing = FOLDER / "uprn_union_missing_xy.csv"
    missing_df.to_csv(out_missing, index=False, encoding="utf-8")
    print(f"Missing XY list: {out_missing} (n={len(missing_df):,})")
