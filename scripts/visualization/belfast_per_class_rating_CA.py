# -*- coding: utf-8 -*-
"""
belfast_explore_epc.py — EPC class distribution + join audit (Belfast)

What it does:
- Loads GEE features (2 files) and merges on `uid`
- Scans all ratings CSVs in LABELS_DIR for CURRENT_ENERGY_RATING (or synonyms)
- For each ratings CSV: tries key joins (uid → UPRN → EPC) and counts A–G
- Picks the best join (max matched rows) and prints which class has <2
- Saves:
    - audit per ratings file: ratings_join_audit.csv
    - chosen join class counts: chosen_join_class_counts.csv
    - example UIDs for rare classes: rare_class_uids.csv
"""

import os, re, glob, json
from pathlib import Path
import numpy as np
import pandas as pd

# --- Paths (edit if needed) ---------------------------------------------
GEE_DIR      = r"D:\OneDrive - Ulster University\PhD\data\belfast\gee"
FEATURE_FILES = [
    os.path.join(GEE_DIR, "Belfast_2024_point_samples.csv"),
    os.path.join(GEE_DIR, "Belfast_2024_point_samples_uid_rich_v3.csv"),
]
LABELS_DIR   = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-epc"
OUTROOT      = r"D:\OneDrive - Ulster University\PhD\Outputs\belfast_ml_full\explore"
EPC_ORDER    = list("ABCDEFG")

# --- Helpers -------------------------------------------------------------
def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")

def read_any(path: str) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)

def merge_on_uid(dfs):
    base = dfs[0].copy()
    if "uid" not in base.columns:
        raise RuntimeError("`uid` not found in first features file.")
    for df in dfs[1:]:
        if "uid" not in df.columns:
            raise RuntimeError("`uid` missing in one of the feature files.")
        right = df[[c for c in df.columns if c not in set(base.columns) or c == "uid"]]
        base = base.merge(right, on="uid", how="inner")
    return base

TARGET_KEYS_EXACT = [
    "current_energy_rating", "epc_rating", "energy_rating", "efficiency_class"
]

def pick_target_column(df: pd.DataFrame) -> str | None:
    norms = {normalize_name(c): c for c in df.columns}
    for k in TARGET_KEYS_EXACT:
        if k in norms:
            return norms[k]
    return None

UID_CANDS  = ["uid"]
UPRN_CANDS = ["uprn"]
EPC_CANDS  = ["epcw","epc_rrn","rrn","lmk_key","lmkkey","certificate_number","epc_id","rrn_key","lmk_key_rrn"]

def find_key_col(df: pd.DataFrame, cands: list[str]) -> str | None:
    low = {c.lower(): c for c in df.columns}
    for c in cands:
        if c.lower() in low: return low[c.lower()]
    return None

def normalize_epc_id(s: pd.Series) -> pd.Series:
    return (s.astype(str)
             .str.upper()
             .str.replace(r"[^A-Z0-9]", "", regex=True)
             .replace({"": np.nan}))

def clean_epc_A2G(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip().str.upper().str[0]
    return s.where(s.isin(EPC_ORDER))

def class_counts_A2G(s: pd.Series) -> pd.Series:
    return clean_epc_A2G(s).value_counts().reindex(EPC_ORDER, fill_value=0).astype(int)

def list_ratings_csvs() -> list[str]:
    if not os.path.isdir(LABELS_DIR): return []
    return sorted(glob.glob(os.path.join(LABELS_DIR, "*.csv")))

# --- Load features -------------------------------------------------------
os.makedirs(OUTROOT, exist_ok=True)

feat_dfs = []
for p in FEATURE_FILES:
    if not os.path.exists(p):
        raise FileNotFoundError(f"Missing feature file: {p}")
    df = read_any(p)
    feat_dfs.append(df)
    print(f"[LOAD] features: {p} -> {df.shape}")

features = merge_on_uid(feat_dfs)
print(f"[INFO] merged features on uid: {features.shape}")

f_uid  = find_key_col(features, UID_CANDS)
f_uprn = find_key_col(features, UPRN_CANDS)
f_epc  = find_key_col(features, EPC_CANDS)

print(f"[KEYS] features: uid={f_uid}, uprn={f_uprn}, epc={f_epc}")

# --- Scan ratings files & audit joins -----------------------------------
audit_rows = []
best_join = None
best_info = None

for rp in list_ratings_csvs():
    try:
        r = read_any(rp)
    except Exception:
        print(f"[SKIP] cannot read {rp}")
        continue

    tgt = pick_target_column(r)
    if tgt is None:
        # skip files without EPC target (avoids AIRCON_KW_RATING, etc.)
        print(f"[SKIP] {Path(rp).name}: no EPC target")
        continue

    r_uid  = find_key_col(r, UID_CANDS)
    r_uprn = find_key_col(r, UPRN_CANDS)
    r_epc  = find_key_col(r, EPC_CANDS)

    # overall distribution in ratings file (for reference)
    overall_counts = class_counts_A2G(r[tgt])

    # try joins
    joined_uid = joined_uprn = joined_epc = None
    n_uid = n_uprn = n_epc = 0

    if f_uid and r_uid:
        joined_uid = features.merge(r[[r_uid, tgt]], left_on=f_uid, right_on=r_uid, how="inner")
        n_uid = len(joined_uid)

    if f_uprn and r_uprn:
        joined_uprn = features.merge(r[[r_uprn, tgt]], left_on=f_uprn, right_on=r_uprn, how="inner")
        n_uprn = len(joined_uprn)

    if f_epc and r_epc:
        F = features.copy(); R = r.copy()
        F["_epc_key_norm"] = normalize_epc_id(F[f_epc])
        R["_epc_key_norm"] = normalize_epc_id(R[r_epc])
        joined_epc = F.merge(R[["_epc_key_norm", tgt]], on="_epc_key_norm", how="inner")
        n_epc = len(joined_epc)

    # pick the best for this file
    n_list = [("uid", n_uid, joined_uid, (f_uid, r_uid)),
              ("uprn", n_uprn, joined_uprn, (f_uprn, r_uprn)),
              ("epc", n_epc, joined_epc, (f_epc, r_epc))]
    n_list.sort(key=lambda x: x[1], reverse=True)
    best_for_file = n_list[0]
    method, n_matched, joined_df, keys = best_for_file

    # class counts for joined (if any)
    joined_counts = pd.Series(0, index=EPC_ORDER, dtype=int)
    if joined_df is not None and n_matched > 0:
        joined_counts = class_counts_A2G(joined_df[tgt])

    audit_rows.append({
        "ratings_file": Path(rp).name,
        "rows_in_ratings": len(r),
        "target_col": tgt,
        "has_uid": bool(r_uid), "has_uprn": bool(r_uprn), "has_epc": bool(r_epc),
        "match_uid": n_uid, "match_uprn": n_uprn, "match_epc": n_epc,
        "chosen_method": method,
        "chosen_keys": f"{keys[0]}↔{keys[1]}",
        "chosen_matched": n_matched,
        **{f"ratings_overall_{k}": int(overall_counts.get(k, 0)) for k in EPC_ORDER},
        **{f"joined_{k}": int(joined_counts.get(k, 0)) for k in EPC_ORDER},
    })

    # update global best
    if (best_join is None) or (n_matched > len(best_join)):
        best_join = joined_df if joined_df is not None else None
        best_info = {
            "ratings_path": rp,
            "tgt": tgt,
            "method": method,
            "keys": keys,
            "matched": n_matched
        }

# write audit
audit_df = pd.DataFrame(audit_rows)
audit_csv = Path(OUTROOT) / "ratings_join_audit.csv"
audit_df.to_csv(audit_csv, index=False)
print(f"\n[SAVED] {audit_csv}")

# --- Report the best join in detail -------------------------------------
if best_join is None or best_info is None or best_info["matched"] == 0:
    raise RuntimeError("No successful key-based join found. See ratings_join_audit.csv for details.")

rp   = best_info["ratings_path"]
tgt  = best_info["tgt"]
meth = best_info["method"]
keys = best_info["keys"]
nmat = best_info["matched"]

print("\n[CHOICE] Best ratings file:", rp)
print(f"[CHOICE] Join: {meth} via {keys}  |  matched rows: {nmat:,}")

# EPC distribution in chosen join
joined_counts = class_counts_A2G(best_join[tgt])
print("\n[EPC] Class counts in CHOSEN JOIN:")
print(joined_counts.to_string())

chosen_counts_csv = Path(OUTROOT) / "chosen_join_class_counts.csv"
joined_counts.to_csv(chosen_counts_csv, header=["count"])
print(f"[SAVED] {chosen_counts_csv}")

# Flag classes with <2 rows and show example UIDs
rare = joined_counts[joined_counts < 2]
if len(rare) == 0:
    print("\n[OK] All EPC classes have >=2 rows in the joined data.")
else:
    print("\n[WARN] Rare EPC classes (<2 rows):")
    for k, v in rare.items():
        print(f"  - {k}: {v} row(s)")
    # show example UIDs for rare classes (if uid exists)
    uid_col = "uid" if "uid" in best_join.columns else None
    rare_rows = []
    if uid_col:
        j_clean = best_join.copy()
        j_clean["_EPC_CLEAN"] = clean_epc_A2G(j_clean[tgt])
        for grade in rare.index:
            sample = j_clean.loc[j_clean["_EPC_CLEAN"] == grade, [uid_col]].head(20)
            for u in sample[uid_col].tolist():
                rare_rows.append({"class": grade, "uid": u})
        rare_csv = Path(OUTROOT) / "rare_class_uids.csv"
        pd.DataFrame(rare_rows).to_csv(rare_csv, index=False)
        print(f"[SAVED] {rare_csv}  (example UIDs per rare class)")

print("\nDone.")
