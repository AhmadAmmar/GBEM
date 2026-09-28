# -*- coding: utf-8 -*-
"""
UPRN audit & union for three CSVs, with robust encoding handling.

Outputs (written into the same folder as inputs):
  - uprn_union_list.csv
  - <stem>_ONLY.csv for each input file
  - uprn_union_rows_commoncols.csv  (deduped on UPRN_key across common columns)
"""

import pandas as pd
import re
from itertools import combinations
from pathlib import Path
from typing import Tuple, Dict, Set

# ------------- CONFIG -------------
FOLDER = Path(r"D:\OneDrive - Ulster University\PhD\data\belfast\uprn\BELFS_20250829_F")
FILES = [
    "BELFS_20250829_EXT_F.csv",
    "BELFS_20250829_F.csv",
    "BELFS_20250829_REJ_F.csv",
]
# dedupe priority when keeping a single row per UPRN in the "full rows" export
FILE_PRIORITY = [
    "BELFS_20250829_F.csv",
    "BELFS_20250829_EXT_F.csv",
    "BELFS_20250829_REJ_F.csv",
]
CHUNK = 250_000
CANDIDATE_ENCODINGS = ("utf-8", "utf-8-sig", "cp1252", "latin1")
# ----------------------------------

def sniff_encoding(path: Path) -> str:
    for enc in CANDIDATE_ENCODINGS:
        try:
            pd.read_csv(path, nrows=1, encoding=enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin1"

def find_uprn_col(path: Path, encoding: str) -> str:
    cols = pd.read_csv(path, nrows=0, encoding=encoding).columns
    for c in cols:
        if "uprn" in c.lower():
            return c
    raise ValueError(f"No UPRN-like column found in {path}\nColumns: {list(cols)}")

def norm_uprn(val):
    """Return digits-only UPRN string; strips prefixes and '.0' artifacts; preserves leading zeros."""
    if pd.isna(val):
        return None
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]
    s = s.replace("UPRN-", "").replace("uprn-", "")
    s = re.sub(r"\D", "", s)
    return s or None

def pretty(n: int) -> str:
    return f"{n:,}"

# ---------- 1) Per-file UPRN sets & stats ----------
file_enc: Dict[str, str] = {}
uprn_col_name: Dict[str, str] = {}
sets: Dict[str, Set[str]] = {}
row_counts: Dict[str, int] = {}
nonempty_counts: Dict[str, int] = {}

for fname in FILES:
    path = FOLDER / fname
    enc = sniff_encoding(path)
    file_enc[fname] = enc
    col = find_uprn_col(path, enc)
    uprn_col_name[fname] = col

    S: Set[str] = set()
    total_rows = 0
    nonempty = 0

    for chunk in pd.read_csv(path, usecols=[col], dtype=str,
                             chunksize=CHUNK, low_memory=False, encoding=enc):
        total_rows += len(chunk)
        n = chunk[col].map(norm_uprn)
        nonempty += n.notna().sum()
        S.update(n.dropna().unique())

    sets[fname] = S
    row_counts[fname] = total_rows
    nonempty_counts[fname] = nonempty

print("\n=== Unique UPRNs per file ===")
for fname in FILES:
    print(f"{fname:30s} rows={pretty(row_counts[fname])}  "
          f"UPRNs(non-empty)={pretty(nonempty_counts[fname])}  "
          f"unique={pretty(len(sets[fname]))}")

print("\n=== Pairwise overlaps (unique UPRNs) ===")
for (a, b) in combinations(FILES, 2):
    inter = len(sets[a] & sets[b])
    print(f"{a} ∩ {b}: {pretty(inter)}")

if len(FILES) >= 3:
    inter3 = len(set.intersection(*[sets[f] for f in FILES]))
    print(f"\nThree-way intersection: {pretty(inter3)}")

# ---------- 2) Union list ----------
union_uprn = set().union(*[sets[f] for f in FILES])
union_df = pd.DataFrame({"UPRN_key": sorted(union_uprn)})
out_union = FOLDER / "uprn_union_list.csv"
union_df.to_csv(out_union, index=False, encoding="utf-8")
print(f"\nSaved union of unique UPRNs: {out_union} (n={pretty(len(union_df))})")

# ---------- 3) ONLY sets ----------
for fname in FILES:
    only = sets[fname] - set().union(*[sets[f] for f in FILES if f != fname])
    out_only = FOLDER / f"{Path(fname).stem}_ONLY.csv"
    pd.DataFrame({"UPRN_key": sorted(only)}).to_csv(out_only, index=False, encoding="utf-8")
    print(f"{fname}: ONLY set saved ({pretty(len(only))}) -> {out_only}")

# ---------- 4) Union of FULL ROWS (common columns; chunked; priority) ----------
# Build list of common columns across files (based on headers only)
common_cols = None
headers = {}
for fname in FILES:
    path = FOLDER / fname
    enc = file_enc[fname]
    cols = list(pd.read_csv(path, nrows=0, encoding=enc).columns)
    headers[fname] = cols
    common_cols = set(cols) if common_cols is None else (common_cols & set(cols))

if not common_cols:
    print("\n[Note] No common columns across files; skipping 'union of full rows'.")
else:
    common_cols = list(common_cols)  # stable order
    # ensure each file's UPRN column is included so we can normalise -> UPRN_key
    # we'll replace the original per-file UPRN column with a single UPRN_key field
    pri_rank = {f: i for i, f in enumerate(FILE_PRIORITY)}
    store: Dict[str, dict] = {}         # UPRN_key -> row dict (common cols only)
    srcset: Dict[str, Set[str]] = {}    # UPRN_key -> set of source filenames
    primary: Dict[str, str] = {}        # UPRN_key -> chosen primary source

    for fname in FILES:
        path = FOLDER / fname
        enc = file_enc[fname]
        col = uprn_col_name[fname]
        usecols = list(set(common_cols) | {col})  # add file's UPRN col

        for chunk in pd.read_csv(path, usecols=usecols, dtype=str,
                                 chunksize=CHUNK, low_memory=False, encoding=enc):
            chunk["UPRN_key"] = chunk[col].map(norm_uprn)
            # limit to rows that actually have a UPRN
            chunk = chunk.dropna(subset=["UPRN_key"]).copy()

            # Prepare rows dict (common columns only)
            # Keep a copy with only common_cols (drop the file-specific UPRN col if present)
            drop_cols = [c for c in [col] if c in chunk.columns]
            data = chunk.drop(columns=drop_cols, errors="ignore")

            for _, row in data.iterrows():
                k = row["UPRN_key"]
                if not k:
                    continue
                if k not in store:
                    store[k] = row[["UPRN_key"] + [c for c in common_cols if c != col]].to_dict()
                    srcset[k] = {fname}
                    primary[k] = fname
                else:
                    # update sources
                    srcset[k].add(fname)
                    # decide if we should replace the stored row based on FILE_PRIORITY
                    if pri_rank.get(fname, 9999) < pri_rank.get(primary[k], 9999):
                        store[k] = row[["UPRN_key"] + [c for c in common_cols if c != col]].to_dict()
                        primary[k] = fname

    # Build DataFrame from dicts
    records = []
    for k, rowdict in store.items():
        rec = dict(rowdict)
        rec["primary_source"] = primary[k]
        rec["source_files"] = ",".join(sorted(srcset[k]))
        records.append(rec)

    df_rows = pd.DataFrame.from_records(records)
    # Put columns in a nice order
    front = ["UPRN_key", "primary_source", "source_files"]
    others = [c for c in df_rows.columns if c not in front]
    df_rows = df_rows[front + others]

    out_rows = FOLDER / "uprn_union_rows_commoncols.csv"
    df_rows.to_csv(out_rows, index=False, encoding="utf-8")
    print(f"\nSaved union of FULL ROWS (common columns): {out_rows} (n={pretty(len(df_rows))})")

print("\nDone.")
