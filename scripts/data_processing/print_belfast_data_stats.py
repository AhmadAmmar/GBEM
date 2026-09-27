# -*- coding: utf-8 -*-
"""
EPC ↔ UPRN stats report (Belfast / NI)

Prints:
- Total EPC rows in the original EPC CSV
- EPC rows with valid UPRNs (row-level)
- Unique valid UPRNs in EPC
- For each of the 3 original UPRN files:
    * total rows
    * rows with non-empty/valid UPRN
    * unique valid UPRNs
- Combined rows (sum) across the 3 UPRN files with non-empty UPRN
- Unique UPRNs across the union of the 3 files
- Intersection with EPC (unique UPRN-level)
- EPC rows (row-level) with valid UPRN that matched the union
- EPC rows (row-level) with valid UPRN that did NOT match the union
- Unique UPRNs in the union that did NOT appear in EPC valid UPRNs
- Pairwise & three-way overlaps (unique UPRNs)
- (Extras) Duplicate-rate in EPC; UPRN-length distribution (quick QA)
"""

import pandas as pd
import re
from pathlib import Path
from itertools import combinations
from collections import Counter

# ============== CONFIG ==============
EPC_CSV = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-epc\NI_Domestic_Master_to 01_2025.csv"

UPRN_FOLDER = Path(r"D:\OneDrive - Ulster University\PhD\data\belfast\uprn\BELFS_20250829_F")
UPRN_FILES = [
    "BELFS_20250829_F.csv",
    "BELFS_20250829_EXT_F.csv",
    "BELFS_20250829_REJ_F.csv",
]

CHUNK = 200_000
CANDIDATE_ENCODINGS = ("utf-8", "utf-8-sig", "cp1252", "latin1")
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
    """
    Canonical UPRN key (for joins / comparisons):
    - strip 'UPRN-' and any non-digits
    - drop leading zeros (e.g., '000185003143' -> '185003143')
    Returns None if empty after cleaning.
    """
    if pd.isna(val):
        return None
    s = str(val).strip()
    s = s.replace("UPRN-", "").replace("uprn-", "")
    s = re.sub(r"\D", "", s)
    if not s:
        return None
    try:
        return str(int(s))
    except ValueError:
        return None

def pretty(n): return f"{n:,}"

# ---------- EPC: row-level & unique ----------
epc_enc = sniff_encoding(EPC_CSV)
epc_uprn_col = find_uprn_col(EPC_CSV, epc_enc)

epc_total_rows = 0
epc_valid_rows = 0
epc_valid_uprn_set = set()
epc_valid_rows_matched_union = 0  # will compute after union set is ready
uprn_length_counter = Counter()

# We'll load UPRN files first to create the union set.
# ---------- UPRN files: per-file sets & counts ----------
union_set = set()
per_file_sets = {}
per_file_rows_total = {}
per_file_rows_with_uprn = {}
per_file_unique = {}

for fname in UPRN_FILES:
    path = str(UPRN_FOLDER / fname)
    enc = sniff_encoding(path)
    col = find_uprn_col(path, enc)

    S = set()
    rows_total = 0
    rows_with_uprn = 0

    for chunk in pd.read_csv(path, usecols=[col], dtype=str,
                             chunksize=CHUNK, low_memory=False, encoding=enc):
        rows_total += len(chunk)
        n = chunk[col].map(canonical_uprn)
        rows_with_uprn += n.notna().sum()
        S.update(n.dropna().unique())

    per_file_sets[fname] = S
    per_file_rows_total[fname] = rows_total
    per_file_rows_with_uprn[fname] = rows_with_uprn
    per_file_unique[fname] = len(S)
    union_set |= S

# Now scan EPC and compute row-level + unique + row-level matches vs union
for chunk in pd.read_csv(EPC_CSV, dtype=str, chunksize=CHUNK, low_memory=False, encoding=epc_enc):
    epc_total_rows += len(chunk)
    k = chunk[epc_uprn_col].map(canonical_uprn)
    valid_mask = k.notna()
    epc_valid_rows += int(valid_mask.sum())
    # accumulate unique UPRNs
    epc_valid_uprn_set.update(k[valid_mask].unique())

    # row-level matches (EPC rows whose canonical UPRN is in the union)
    # Note: keep only valid UPRNs then test membership
    if union_set:
        epc_valid_rows_matched_union += int(k[valid_mask].isin(union_set).sum())

    # QA: track length distribution of canonical UPRNs (optional)
    uprn_length_counter.update([len(s) for s in k.dropna()])

# ---------- Stats ----------
print("\n========== EPC (original) ==========")
print(f"Total EPC rows:                                  {pretty(epc_total_rows)}")
print(f"EPC rows with valid UPRN (row-level):            {pretty(epc_valid_rows)}")
print(f"Unique valid UPRNs in EPC:                       {pretty(len(epc_valid_uprn_set))}")

print("\n========== UPRN files (original 3) ==========")
for fname in UPRN_FILES:
    print(f"{fname:28s}  rows={pretty(per_file_rows_total[fname])}  "
          f"with-UPRN={pretty(per_file_rows_with_uprn[fname])}  "
          f"unique-UPRN={pretty(per_file_unique[fname])}")

combined_rows_with_uprn = sum(per_file_rows_with_uprn.values())
print(f"\nCombined with-UPRN rows across 3 files:          {pretty(combined_rows_with_uprn)}")
print(f"Unique UPRNs across union of 3 files:            {pretty(len(union_set))}")

# Unique-level intersection
unique_match_count = len(epc_valid_uprn_set & union_set)
print("\n========== Cross-match ==========")
print(f"Unique UPRNs (EPC ∩ UPRN-union):                 {pretty(unique_match_count)}")
print(f"EPC rows with valid UPRN that matched (rows):    {pretty(epc_valid_rows_matched_union)}")

# EPC rows with valid UPRN that did NOT find a UPRN in union (row-level)
epc_rows_valid_not_matched = epc_valid_rows - epc_valid_rows_matched_union
print(f"EPC rows with valid UPRN NOT matched (rows):     {pretty(epc_rows_valid_not_matched)}")

# Unique UPRNs in union not present in EPC
union_unique_not_in_epc = len(union_set - epc_valid_uprn_set)
print(f"Unique UPRNs in union NOT in EPC:                {pretty(union_unique_not_in_epc)}")

# Coverage percentages
if epc_valid_rows:
    print(f"\nRow-level match rate (valid EPC rows):           {epc_valid_rows_matched_union/epc_valid_rows:.2%}")
if epc_valid_uprn_set:
    print(f"Unique-level match rate (EPC uniques):           {unique_match_count/len(epc_valid_uprn_set):.2%}")

# Pairwise & 3-way overlaps (unique UPRNs)
print("\n========== Overlaps (unique UPRNs) ==========")
for (a, b) in combinations(UPRN_FILES, 2):
    inter = len(per_file_sets[a] & per_file_sets[b])
    print(f"{a} ∩ {b}: {pretty(inter)}")
if len(UPRN_FILES) >= 3:
    inter3 = len(set.intersection(*[per_file_sets[f] for f in UPRN_FILES]))
    print(f"3-way intersection:                              {pretty(inter3)}")

# Extras: EPC duplicate rate (valid rows vs unique UPRNs) & length distribution
if epc_valid_rows and epc_valid_uprn_set:
    dup_rate = 1 - (len(epc_valid_uprn_set) / epc_valid_rows)
    print("\n========== EPC QA ==========")
    print(f"Duplicate rate among EPC rows with valid UPRN:   {dup_rate:.2%}")
    # length distribution (handy sanity check)
    top_lengths = sorted(uprn_length_counter.items())
    print("Canonical UPRN length distribution (EPC):")
    for L, cnt in top_lengths:
        print(f"  length {L}: {pretty(cnt)}")

print("\nDone.")
