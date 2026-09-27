# -*- coding: utf-8 -*-
r"""
belfast_CA.py — key-first ML pipeline + one-page A4 report for Belfast

- Features: reads & merges BOTH GEE files on `uid`.
- Ratings: scans all CSVs in LABELS_DIR, finds those with CURRENT_ENERGY_RATING (or synonyms),
  tries key-based joins: uid → UPRN → EPC certificate (epcw/lmk_key/rrn).
  Picks the join that yields the MOST matches; prints details.
- Adds lon/lat from the coord WGS84 file by uid (key-only).
- Spatial nearest-neighbour is DISABLED by default (enable via ALLOW_NEAREST_FALLBACK).

Outputs:
  D:\OneDrive - Ulster University\PhD\Outputs\belfast_ml_full\run_YYYYMMDD_HHMM\
    - belfast_full_report_A4.pdf / .png
    - metrics.json, classification_report.csv, confusion_matrix_counts.csv
    - shap_global_importance.csv (+ _with_sign)
    - features_used.txt
"""

import os, re, glob, json, math, datetime, warnings
from pathlib import Path
from typing import List, Tuple, Optional

import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")

try:
    import geopandas as gpd
except Exception:
    gpd = None

import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.gridspec import GridSpec

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, balanced_accuracy_score, f1_score,
    confusion_matrix, classification_report, cohen_kappa_score
)
from sklearn.calibration import CalibratedClassifierCV

import shap

# ── Paths ───────────────────────────────────────────────────────────────
GEE_DIR      = r"D:\OneDrive - Ulster University\PhD\data\belfast\gee"
FEATURE_FILES = [
    os.path.join(GEE_DIR, "Belfast_2024_point_samples.csv"),
    os.path.join(GEE_DIR, "Belfast_2024_point_samples_uid_rich_v3.csv"),
]
LABELS_DIR   = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-epc"

# Preferred WGS84 coord file (usually: uid + lon + lat)
PREFERRED_COORD_FILE = os.path.join(
    LABELS_DIR, "gee_epc_2024_points_uid_wgs84_MIN.csv"
)

OUTROOT      = r"D:\OneDrive - Ulster University\PhD\Outputs\belfast_ml_full"

# ── ML / Pipeline config ────────────────────────────────────────────────
USE_TARGET   = "multiclass"          # "multiclass" (A–G) or "binary" (A–C vs D–G)
SPLIT_TR_VA_TE = (0.60, 0.20, 0.20)  # train/val/test
RANDOM_SEED  = 42
N_TREES      = 400
CALIBRATION  = "isotonic"            # "none" | "sigmoid" | "isotonic"
SAMPLE_FRAC  = 1.0                   # set <1.0 for dev
SHAP_MAX     = 800

# Joins: spatial fallback is OFF unless you enable it
ALLOW_NEAREST_FALLBACK = False
MAX_NEAREST_DIST_M = 150.0           # used only if fallback is enabled

# ── Figure & housekeeping ───────────────────────────────────────────────
A4_W, A4_H, DPI = 8.27, 11.69, 300
EPC_ORDER = list("ABCDEFG")
EFFICIENT_SET = set(list("ABC"))
BLACKLIST_SUBSTR = ("address","postcode","geometry","geom","wkt","system:index")
BLACKLIST_EXACT = {"uid",".geo","lat","lon","x","y"}
NUMERIC_EXCLUDE_LIKE = ("uprn", "uprn_", "gid")

def now_tag() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M")

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def read_any_table(path: str) -> pd.DataFrame:
    ext = Path(path).suffix.lower()
    if ext in (".geojson", ".json", ".shp") and gpd is not None:
        return gpd.read_file(path)
    return pd.read_csv(path, low_memory=False)

def merge_on_uid(dfs: List[pd.DataFrame]) -> pd.DataFrame:
    base = dfs[0].copy()
    if "uid" not in base.columns:
        raise RuntimeError("`uid` column not found in first dataframe.")
    for df in dfs[1:]:
        if "uid" not in df.columns:
            raise RuntimeError("`uid` column missing in one of the input files.")
        right = df[[c for c in df.columns if c not in set(base.columns) or c == "uid"]]
        base = base.merge(right, on="uid", how="inner")
    return base

def harmonize_era5(df: pd.DataFrame) -> pd.DataFrame:
    if "era5_t2m_C" not in df.columns and "era5_t2m_K" in df.columns:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                df["era5_t2m_C"] = pd.to_numeric(df["era5_t2m_K"], errors="coerce") - 273.15
            except Exception:
                pass
    return df

# ── Key/target helpers ──────────────────────────────────────────────────
def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")

def normalize_id_value(s: pd.Series) -> pd.Series:
    """Uppercase & keep only [A-Z0-9]. Good for RRN/LMK_KEY/‘epcw’ with punctuation/hyphens."""
    return (s.astype(str)
              .str.upper()
              .str.replace(r"[^A-Z0-9]", "", regex=True)
              .replace({"": np.nan}))

UID_CANDS   = ["uid"]
UPRN_CANDS  = ["uprn"]
EPC_CANDS   = ["epcw","epc_rrn","rrn","lmk_key","lmkkey","certificate_number","epc_id","rrn_key","lmk_key_rrn"]

def find_key_col(df: pd.DataFrame, candidates: list[str], label: str) -> Optional[str]:
    cols_lower = {c.lower(): c for c in df.columns}
    tried = []
    for c in candidates:
        if c.lower() in cols_lower:
            col = cols_lower[c.lower()]
            print(f"[KEY] {label}: using '{col}'")
            return col
        tried.append(c)
    print(f"[KEY] {label}: none of {tried} found.")
    return None

def pick_uid(df: pd.DataFrame, label: str) -> Optional[str]:
    return find_key_col(df, UID_CANDS, label)

def pick_uprn(df: pd.DataFrame, label: str) -> Optional[str]:
    return find_key_col(df, UPRN_CANDS, label)

def pick_epc_key(df: pd.DataFrame, label: str) -> Optional[str]:
    return find_key_col(df, EPC_CANDS, label)

def pick_target_column(df: pd.DataFrame) -> Optional[str]:
    norms = {normalize_name(c): c for c in df.columns}
    for key in ["current_energy_rating","epc_rating","energy_rating","efficiency_class"]:
        if key in norms:
            print(f"[TARGET] Found '{norms[key]}'")
            return norms[key]
    # fallback: any '*rating*'
    for c in df.columns:
        if "rating" in c.lower():
            print(f"[TARGET] Fallback using '{c}'")
            return c
    return None

def clean_epc_multiclass(series: pd.Series) -> pd.Series:
    """Coerce to EPC A–G (uppercase first letter) and drop anything else."""
    s = series.astype(str).str.strip().str.upper().str[0]
    s = s.where(s.isin(EPC_ORDER))
    return s

# ── Coord detection for the coord file (name-based only) ────────────────
CANDIDATE_PAIRS = [
    ("lon","lat"), ("longitude","latitude"),
    ("x","y"),
    ("east","north"), ("easting","northing"), ("eastings","northings"),
    ("x_coor","y_coor"), ("x_coord","y_coord"), ("xcoordinate","ycoordinate"),
]

def find_coordinate_pair(df: pd.DataFrame, label: str) -> tuple[Optional[str], Optional[str], str]:
    """Return (xcol, ycol, kind) via name patterns only (no numeric scan)."""
    print(f"[COORD] Scanning coordinate columns in: {label}")
    lower2orig = {c.lower(): c for c in df.columns}
    tried = []
    for a, b in CANDIDATE_PAIRS:
        if a in lower2orig and b in lower2orig:
            tried.append((lower2orig[a], lower2orig[b]))
    if tried:
        print("        Candidates found (x,y):", tried)
    else:
        print("        No obvious candidates by name.")
        return None, None, "unknown"

    # Prefer lon/lat if present
    for A, B in tried:
        if A.lower() in ("lon","longitude") and B.lower() in ("lat","latitude"):
            print(f"        -> choosing ({A}, {B}) as LON/LAT")
            return A, B, "lonlat"

    # Otherwise take first and infer
    A, B = tried[0]
    kind = "lonlat" if ("lon" in A.lower() or "lat" in B.lower() or "longitude" in A.lower()) else "projected"
    print(f"        -> choosing ({A}, {B}) as {kind.upper()}")
    return A, B, kind

# ── Ratings discovery (scan all CSVs) ───────────────────────────────────
def list_rating_files() -> List[str]:
    if not os.path.isdir(LABELS_DIR):
        return []
    paths = sorted(glob.glob(os.path.join(LABELS_DIR, "*.csv")))
    keep = []
    for p in paths:
        try:
            head = pd.read_csv(p, nrows=250, low_memory=False)
        except Exception:
            continue
        tgt = pick_target_column(head)
        if tgt is not None:
            keep.append(p)
    return keep

# ── Feature selection & encoding ────────────────────────────────────────
def select_features(df: pd.DataFrame, target_col: str) -> List[str]:
    feats = []
    for c in df.columns:
        cl = c.lower()
        if c == target_col or c == "uid": continue
        if c in BLACKLIST_EXACT: continue
        if any(b in cl for b in BLACKLIST_SUBSTR): continue
        if any(b in cl for b in NUMERIC_EXCLUDE_LIKE): continue
        if pd.api.types.is_numeric_dtype(df[c]):
            feats.append(c)
    if len(feats) < 5:
        raise RuntimeError("Too few numeric features after filtering.")
    return feats

# ── Main ────────────────────────────────────────────────────────────────
def main():
    run_dir = Path(OUTROOT) / f"run_{now_tag()}"
    ensure_dir(run_dir)

    # Load & merge features
    dfs = []
    for p in FEATURE_FILES:
        if not os.path.exists(p):
            raise FileNotFoundError(f"Missing feature file: {p}")
        dfp = read_any_table(p)
        dfs.append(dfp)
        print(f"[LOAD] {p}  ->  {dfp.shape}")
    feats_df = merge_on_uid(dfs)
    feats_df = harmonize_era5(feats_df)
    print(f"[INFO] Merged features on uid: {feats_df.shape}")

    # Keys present in features
    f_uid  = pick_uid(feats_df,  "features")
    f_uprn = pick_uprn(feats_df, "features")
    f_epc  = pick_epc_key(feats_df, "features")

    # Load coord file (for lon/lat via uid)
    if not os.path.exists(PREFERRED_COORD_FILE):
        raise RuntimeError(f"Preferred coord labels file not found: {PREFERRED_COORD_FILE}")
    coord_df = pd.read_csv(PREFERRED_COORD_FILE, low_memory=False)
    print(f"[LOAD] coord labels: {PREFERRED_COORD_FILE}  ->  {coord_df.shape}")
    c_uid = pick_uid(coord_df, "coords")
    cx, cy, ckind = find_coordinate_pair(coord_df, "coords")
    if c_uid and cx and cy:
        print(f"[COORD] Will add coords later via uid '{c_uid}' -> using ({cx}, {cy}) [{ckind}]")
    else:
        print("[COORD] No uid and/or coord columns in coord file — skipping lon/lat enrichment.")

    # Discover ratings files & attempt key-based joins
    rating_paths = list_rating_files()
    if not rating_paths:
        raise RuntimeError("No ratings CSVs found in LABELS_DIR containing an EPC rating column.")
    print(f"[RATINGS] Candidates: {len(rating_paths)} files")

    best_join = None
    best_info = None
    for rp in rating_paths:
        try:
            rating_df = pd.read_csv(rp, low_memory=False)
        except Exception:
            continue
        print(f"[LOAD] ratings: {rp}  ->  {rating_df.shape}")

        tgt = pick_target_column(rating_df)
        if tgt is None:
            continue

        # coerce to EPC A–G (handle lower-case a..g in Belfast)
        rating_df["_TARGET_CLEAN"] = clean_epc_multiclass(rating_df[tgt])

        r_uid  = pick_uid(rating_df,  "ratings")
        r_uprn = pick_uprn(rating_df, "ratings")
        r_epc  = pick_epc_key(rating_df, "ratings")

        joined = None
        join_used = None

        # 1) uid
        if f_uid and r_uid and feats_df[f_uid].notna().any() and rating_df[r_uid].notna().any():
            joined = feats_df.merge(rating_df[[r_uid, "_TARGET_CLEAN"]], left_on=f_uid, right_on=r_uid, how="inner")
            join_used = f"uid ({f_uid}↔{r_uid})"
        # 2) UPRN
        elif f_uprn and r_uprn:
            joined = feats_df.merge(rating_df[[r_uprn, "_TARGET_CLEAN"]], left_on=f_uprn, right_on=r_uprn, how="inner")
            join_used = f"UPRN ({f_uprn}↔{r_uprn})"
        # 3) EPC certificate (normalize)
        elif f_epc and r_epc:
            print("[KEY] Normalizing EPC IDs for features & ratings...")
            F = feats_df.copy()
            R = rating_df.copy()
            F["_epc_key_norm"] = normalize_id_value(F[f_epc])
            R["_epc_key_norm"] = normalize_id_value(R[r_epc])
            joined = F.merge(R[["_epc_key_norm", "_TARGET_CLEAN"]], on="_epc_key_norm", how="inner").drop(columns=["_epc_key_norm"])
            join_used = f"EPC ({f_epc}↔{r_epc})"
        else:
            if ALLOW_NEAREST_FALLBACK:
                print("[JOIN] No shared key; spatial fallback is allowed but disabled in ratings scan (prefer keys).")
            joined = None

        if joined is None or "_TARGET_CLEAN" not in joined.columns:
            print(f"[JOIN] {Path(rp).name}: could not join by keys.")
            continue

        n_match = len(joined)
        print(f"[JOIN] {Path(rp).name}: joined via {join_used} -> {n_match:,} rows")
        if best_join is None or n_match > len(best_join):
            best_join = joined
            best_info = {"ratings_csv": rp, "tgt": "_TARGET_CLEAN", "join_used": join_used}

    if best_join is None:
        msg = [
            "Could not join features to ANY ratings file by keys.",
            f"Features keys present: uid={bool(f_uid)}, uprn={bool(f_uprn)}, epc={bool(f_epc)}",
            "Consider adding/aligning one of these keys in a ratings CSV (uid/UPRN/epc).",
            "You can enable ALLOW_NEAREST_FALLBACK=True, but keys are preferred."
        ]
        raise RuntimeError("\n".join(msg))

    joined = best_join
    ratings_csv = best_info["ratings_csv"]
    tcol = best_info["tgt"]
    join_used = best_info["join_used"]
    print(f"[BEST] Using ratings file: {ratings_csv}")
    print(f"[BEST] Join used: {join_used}; matched rows: {len(joined):,}")

    # Add lon/lat by uid from coord file (if possible)
    if c_uid and cx and cy and (f_uid is not None) and (f_uid in joined.columns):
        print("[COORD] Enriching with lon/lat via uid from coord file")
        joined = joined.merge(coord_df[[c_uid, cx, cy]], left_on=f_uid, right_on=c_uid, how="left")
        if "lon" not in joined.columns and "lat" not in joined.columns:
            if "lon" != cx or "lat" != cy:
                joined.rename(columns={cx:"lon", cy:"lat"}, inplace=True)

    # Prepare ML target
    if USE_TARGET == "multiclass":
        y_labels = clean_epc_multiclass(joined[tcol])
        mask = y_labels.notna()
        joined = joined.loc[mask].reset_index(drop=True)
        y = pd.Categorical(y_labels[mask], categories=EPC_ORDER).codes
        y_cat = pd.Categorical.from_codes(y, categories=EPC_ORDER)
    else:
        y_labels = clean_epc_multiclass(joined[tcol])
        mask = y_labels.notna()
        joined = joined.loc[mask].reset_index(drop=True)
        y = y_labels.isin(EFFICIENT_SET).astype(int).values
        y_cat = None

    # Feature set
    feat_cols = select_features(joined, tcol)
    X = joined[feat_cols].astype(float)
    print(f"[INFO] Features selected: {len(feat_cols)}")

    # Optional subsample
    if 0 < SAMPLE_FRAC < 1.0:
        if USE_TARGET == "multiclass":
            parts = []
            cats = pd.Categorical.from_codes(y, categories=EPC_ORDER)
            for cls, sub_idx in pd.Series(range(len(y)), index=cats).groupby(cats):
                idxs = list(sub_idx.index)
                n = len(idxs); take = max(1, int(math.ceil(SAMPLE_FRAC*n)))
                take = min(take, n)
                keep = np.random.RandomState(RANDOM_SEED).choice(idxs, size=take, replace=False)
                parts.append(joined.iloc[keep])
            joined = pd.concat(parts, axis=0).sample(frac=1.0, random_state=RANDOM_SEED).reset_index(drop=True)
            y_labels = clean_epc_multiclass(joined[tcol])
            y = pd.Categorical(y_labels, categories=EPC_ORDER).codes
            X = joined[feat_cols].astype(float)
        else:
            # binary: simple frac
            joined = joined.sample(frac=SAMPLE_FRAC, random_state=RANDOM_SEED)
            y_labels = clean_epc_multiclass(joined[tcol])
            y = y_labels.isin(EFFICIENT_SET).astype(int).values
            X = joined[feat_cols].astype(float)

    # Split
    tr, va, te = SPLIT_TR_VA_TE
    X_tr, X_tmp, y_tr, y_tmp = train_test_split(
        X, y, test_size=(1.0 - tr), stratify=y, random_state=RANDOM_SEED
    )
    va_ratio = va / (va + te) if (va+te)>0 else 0.5
    X_va, X_te, y_va, y_te = train_test_split(
        X_tmp, y_tmp, test_size=(1.0 - va_ratio), stratify=y_tmp, random_state=RANDOM_SEED
    )

    # Train RF
    rf = RandomForestClassifier(
        n_estimators=N_TREES, max_depth=None, max_features="sqrt",
        random_state=RANDOM_SEED, n_jobs=-1
    ).fit(X_tr, y_tr)

    # Predict + calibration
    yhat_te = rf.predict(X_te)
    prob_te = rf.predict_proba(X_te) if hasattr(rf, "predict_proba") else None

    yhat_te_cal = prob_te_cal = None
    if CALIBRATION != "none" and prob_te is not None:
        calib = CalibratedClassifierCV(base_estimator=rf, method=CALIBRATION, cv="prefit")
        calib.fit(X_va, y_va)
        yhat_te_cal = calib.predict(X_te)
        prob_te_cal = calib.predict_proba(X_te)

    # Metrics helpers
    def summarize_scores(y_true, y_pred):
        acc = accuracy_score(y_true, y_pred)
        bacc = balanced_accuracy_score(y_true, y_pred)
        f1w = f1_score(y_true, y_pred, average=("weighted" if USE_TARGET=="multiclass" else "binary"))
        f1m = f1_score(y_true, y_pred, average="macro")
        kappa = cohen_kappa_score(y_true, y_pred)
        return acc, bacc, f1w, f1m, kappa

    acc, bacc, f1w, f1m, kappa = summarize_scores(y_te, yhat_te)
    if yhat_te_cal is not None:
        acc_c, bacc_c, f1w_c, f1m_c, kappa_c = summarize_scores(y_te, yhat_te_cal)
    else:
        acc_c = bacc_c = f1w_c = f1m_c = kappa_c = None

    # Off-by (ordinal for multiclass)
    off_by = {}; off_by_cal = {}
    if USE_TARGET == "multiclass":
        def ob(y_true, y_pred):
            d = np.abs(np.array(y_true) - np.array(y_pred))
            return {
                "exact": float(np.mean(d==0)),
                "off_by_1": float(np.mean(d==1)),
                "off_by_2_plus": float(np.mean(d>=2)),
                "ordinal_mae": float(np.mean(d)),
                "ordinal_rmse": float(np.sqrt(np.mean(d**2))),
            }
        off_by = ob(y_te, yhat_te)
        if yhat_te_cal is not None:
            off_by_cal = ob(y_te, yhat_te_cal)

    # Confusion matrix
    if USE_TARGET == "multiclass":
        labels = list(range(len(EPC_ORDER)))
        cm_counts = confusion_matrix(y_te, yhat_te, labels=labels)
        cm_df = pd.DataFrame(cm_counts, index=EPC_ORDER, columns=EPC_ORDER)
        cm_path = Path(run_dir) / "confusion_matrix_counts.csv"
        cm_df.to_csv(cm_path, index=True)
    else:
        cm_counts = confusion_matrix(y_te, yhat_te, labels=[0,1])
        cm_df = pd.DataFrame(cm_counts, index=["Actual_0","Actual_1"], columns=["Pred_0","Pred_1"])
        cm_path = Path(run_dir) / "confusion_matrix_counts_binary.csv"
        cm_df.to_csv(cm_path, index=True)

    # Classification report
    rep = classification_report(y_te, yhat_te, output_dict=True, zero_division=0)
    pd.DataFrame(rep).to_csv(Path(run_dir) / "classification_report.csv")

    # Calibration curve/ECE
    calib_bins = {}
    def reliability_curve(y_true, prob, n_bins=10):
        top_conf = prob.max(axis=1)
        top_pred = prob.argmax(axis=1)
        correct = (top_pred == y_true).astype(int)
        bins = np.linspace(0.0, 1.0, n_bins+1)
        idx = np.digitize(top_conf, bins) - 1
        acc = np.zeros(n_bins); conf = np.zeros(n_bins); cnt = np.zeros(n_bins)
        for b in range(n_bins):
            mask = (idx == b)
            if mask.any():
                acc[b] = correct[mask].mean()
                conf[b] = top_conf[mask].mean()
                cnt[b] = mask.sum()
            else:
                acc[b] = np.nan; conf[b] = np.nan; cnt[b] = 0
        centers = 0.5*(bins[:-1] + bins[1:])
        return centers, acc, conf, cnt

    def expected_calibration_error(acc, conf, cnt) -> float:
        n = cnt.sum()
        if n <= 0: return np.nan
        ece = 0.0
        for a,c,k in zip(acc, conf, cnt):
            if not np.isnan(a) and not np.isnan(c) and k>0:
                ece += (k/n)*abs(a - c)
        return float(ece)

    ece = ece_cal = None
    if prob_te is not None:
        centers, acc_b, conf_b, cnt_b = reliability_curve(y_te, prob_te, n_bins=10)
        ece = expected_calibration_error(acc_b, conf_b, cnt_b)
        calib_bins["raw"] = {"centers":centers.tolist(), "acc":acc_b.tolist(), "conf":conf_b.tolist(), "cnt":cnt_b.tolist(), "ece":ece}
    if prob_te_cal is not None:
        centers_c, acc_cB, conf_cB, cnt_cB = reliability_curve(y_te, prob_te_cal, n_bins=10)
        ece_cal = expected_calibration_error(acc_cB, conf_cB, cnt_cB)
        calib_bins["calibrated"] = {"centers":centers_c.tolist(), "acc":acc_cB.tolist(), "conf":conf_cB.tolist(), "cnt":cnt_cB.tolist(), "ece":ece_cal}
    with open(Path(run_dir) / "calibration_bins.json", "w", encoding="utf-8") as f:
        json.dump(calib_bins, f, indent=2)

    # SHAP (global + beeswarm)
    expl = shap.TreeExplainer(rf)
    shap_slice = min(SHAP_MAX, len(X_te))
    X_plot = X_te.iloc[:shap_slice]
    raw_shap = expl.shap_values(X_plot)

    def aggregate_multiclass_mean_abs(raw):
        if isinstance(raw, list):
            mats = [np.asarray(m) for m in raw]
        else:
            arr = np.asarray(raw)
            if arr.ndim == 3:
                if arr.shape[0] in (2,3,7) and arr.shape[1] == X_plot.shape[0]:
                    mats = [arr[i, :, :] for i in range(arr.shape[0])]
                elif arr.shape[-1] in (2,3,7) and arr.shape[0] == X_plot.shape[0]:
                    mats = [arr[:, :, i] for i in range(arr.shape[-1])]
                else:
                    raise ValueError(f"Unexpected SHAP shape: {arr.shape}")
            elif arr.ndim == 2:
                mats = [arr]
            else:
                raise ValueError(f"Unexpected SHAP ndim: {arr.ndim}")
        return np.mean([np.abs(m) for m in mats], axis=0)

    shap_mat = aggregate_multiclass_mean_abs(raw_shap) if USE_TARGET=="multiclass" else \
               (np.asarray(raw_shap[1]) if isinstance(raw_shap, list) and len(raw_shap)>1 else np.asarray(raw_shap))

    feat_names = list(X_te.columns)
    global_imp = pd.Series(np.abs(shap_mat).mean(axis=0), index=feat_names).sort_values(ascending=False)
    gi_df = global_imp.reset_index(); gi_df.columns = ["feature","mean_abs_shap"]
    gi_df.to_csv(Path(run_dir) / "shap_global_importance.csv", index=False)

    corrs = []
    for i, col in enumerate(feat_names):
        try:
            corrs.append(np.corrcoef(X_plot[col].values, shap_mat[:, i])[0, 1])
        except Exception:
            corrs.append(np.nan)
    gi_df["corr_feat_shap"] = corrs
    gi_df.to_csv(Path(run_dir) / "shap_global_importance_with_sign.csv", index=False)

    # Save metrics bundle
    metrics = {
        "feature_files": FEATURE_FILES,
        "labels_coord_file": PREFERRED_COORD_FILE,
        "chosen_ratings_file": ratings_csv,
        "join_used": join_used,
        "use_target": USE_TARGET,
        "target_col": tcol,
        "n_features": len(feat_cols),
        "split": {"train":len(X_tr), "val":len(X_va), "test":len(X_te)},
        "rf_trees": N_TREES,
        "scores_raw": {"accuracy":acc, "balanced_accuracy":bacc, "f1_weighted":f1w, "f1_macro":f1m, "kappa":kappa},
        "scores_calibrated": {"accuracy":acc_c, "balanced_accuracy":bacc_c, "f1_weighted":f1w_c, "f1_macro":f1m_c, "kappa":kappa_c},
        "off_by_raw": off_by,
        "off_by_calibrated": off_by_cal,
        "ece_raw": ece,
        "ece_calibrated": ece_cal,
        "random_seed": RANDOM_SEED
    }
    with open(Path(run_dir) / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    Path(run_dir, "features_used.txt").write_text("\n".join(feat_cols), encoding="utf-8")

    # ── One-page A4 Figure Sheet ────────────────────────────────────────
    plt.rcParams["pdf.fonttype"] = 42
    plt.rcParams["ps.fonttype"] = 42

    fig = plt.figure(figsize=(A4_W, A4_H), dpi=DPI)
    gs = GridSpec(6, 2,
                  height_ratios=[0.25, 1.2, 1.1, 1.2, 1.5, 0.35],
                  width_ratios=[1.05, 1.15],
                  hspace=0.38, wspace=0.32)

    fig.suptitle(f"Belfast ML • {USE_TARGET.upper()} • {now_tag()}", fontsize=13, y=0.989)

    # Header (left): context
    ax0 = fig.add_subplot(gs[0,0]); ax0.axis("off")
    lines = [
        f"Files: {', '.join([Path(p).name for p in FEATURE_FILES])}",
        f"Join source: {Path(ratings_csv).name} via {join_used}",
        f"Rows (train/val/test): {len(X_tr):,} / {len(X_va):,} / {len(X_te):,}",
        f"Features: {len(feat_cols)}   RF trees: {N_TREES}   Seed: {RANDOM_SEED}",
        f"RAW: Acc {acc:.3f} | BalAcc {bacc:.3f} | F1w {f1w:.3f} | F1m {f1m:.3f} | κ {kappa:.3f}",
    ]
    ytxt = 0.95
    for ln in lines:
        ax0.text(0.02, ytxt, ln, fontsize=9, va="top"); ytxt -= 0.36

    # Header (right): calibration summary
    ax01 = fig.add_subplot(gs[0,1]); ax01.axis("off")
    ax01.text(0.02, 0.95, "Calibration", fontsize=9, weight="bold")
    cal_lines = []
    if ece is not None: cal_lines.append(f"ECE (raw): {ece:.3f}")
    if ece_cal is not None:
        cal_lines.append(f"ECE (calib-{CALIBRATION}): {ece_cal:.3f}")
        cal_lines.append(f"Acc (calib): {acc_c:.3f} | BalAcc {bacc_c:.3f} | F1w {f1w_c:.3f} | F1m {f1m_c:.3f} | κ {kappa_c:.3f}")
    ytxt = 0.55
    for ln in cal_lines:
        ax01.text(0.02, ytxt, ln, fontsize=9, va="top"); ytxt -= 0.36

    # Confusion matrix (counts)
    ax1 = fig.add_subplot(gs[1,0])
    if USE_TARGET == "multiclass":
        n = len(EPC_ORDER)
        dist = np.fromfunction(lambda i,j: np.minimum(np.abs(i-j),2), (n,n))
        ax1.imshow(dist, vmin=0, vmax=2, cmap=plt.cm.get_cmap('RdYlGn_r', 3), alpha=0.55, zorder=0)
        ax1.set_xticks(np.arange(-.5,n,1), minor=True); ax1.set_yticks(np.arange(-.5,n,1), minor=True)
        ax1.grid(which="minor", color="#333333", linewidth=0.7)
        ax1.set_xticks(range(n)); ax1.set_yticks(range(n))
        ax1.set_xticklabels(EPC_ORDER, fontsize=8); ax1.set_yticklabels(EPC_ORDER, fontsize=8)
        ax1.set_xlabel("Predicted", fontsize=9); ax1.set_ylabel("Actual", fontsize=9)
        for i in range(n):
            for j in range(n):
                v = int(cm_df.iloc[i, j])
                ax1.text(j, i, f"{v}", ha="center", va="center", fontsize=8,
                         path_effects=[pe.withStroke(linewidth=2.2, foreground="white")])
        ax1.set_xlim(-0.5,n-0.5); ax1.set_ylim(n-0.5,-0.5); ax1.set_aspect('equal','box')
        ax1.set_title("Confusion Matrix (counts)", fontsize=10, pad=6)
    else:
        ax1.axis("off")

    # Off-by distances
    ax2 = fig.add_subplot(gs[1,1])
    if USE_TARGET == "multiclass" and off_by:
        cats = ["exact","off_by_1","off_by_2_plus"]
        vals = [off_by[k]*100 for k in cats]
        ax2.bar(cats, vals); ax2.set_ylim(0,100)
        ax2.set_title("Off-by Distance (test)", fontsize=10); ax2.set_ylabel("% of predictions")
        for i,v in enumerate(vals):
            ax2.text(i, v+1, f"{v:.1f}%", ha="center", va="bottom", fontsize=8)
    else:
        ax2.axis("off")

    # Reliability curve
    ax3 = fig.add_subplot(gs[2,0])
    ax3.set_title("Reliability Curve (Top-1)", fontsize=10)
    ax3.set_xlabel("Confidence"); ax3.set_ylabel("Accuracy")
    ax3.plot([0,1],[0,1], linestyle="--", linewidth=1)
    if "raw" in calib_bins:
        cb = calib_bins["raw"]; ax3.plot(cb["centers"], cb["acc"], marker="o", label=f"raw (ECE={cb['ece']:.3f})")
    if "calibrated" in calib_bins:
        cc = calib_bins["calibrated"]; ax3.plot(cc["centers"], cc["acc"], marker="o", label=f"calib-{CALIBRATION} (ECE={cc['ece']:.3f})")
    ax3.legend(fontsize=8, loc="lower right")

    # Per-class F1 (raw)
    ax31 = fig.add_subplot(gs[2,1]); ax31.axis("off")
    ax31.set_title("Per-class F1 (raw)", fontsize=10, pad=4)
    rep_df = pd.DataFrame(rep).T
    lines = []
    for ch in EPC_ORDER:
        if ch in rep_df.index:
            f1v = rep_df.loc[ch, "f1-score"] if "f1-score" in rep_df.columns else np.nan
            sup = rep_df.loc[ch, "support"] if "support" in rep_df.columns else np.nan
            lines.append(f"{ch}: F1 {f1v:.2f}  (n={int(sup)})")
    ytxt = 0.9
    for ln in lines[:7]:
        ax31.text(0.02, ytxt, ln, fontsize=9, va="top"); ytxt -= 0.14

    # SHAP bar (top 15)
    ax4 = fig.add_subplot(gs[3,0])
    topk = min(15, len(global_imp))
    gi = global_imp.iloc[:topk][::-1]
    ax4.barh(gi.index, gi.values)
    ax4.set_title("SHAP Global Feature Importance (mean |SHAP|)", fontsize=10)
    ax4.set_xlabel("mean |SHAP|")
    ax4.tick_params(axis='y', labelsize=7); ax4.tick_params(axis='x', labelsize=8)

    # SHAP beeswarm
    ax5 = fig.add_subplot(gs[3,1]); plt.sca(ax5)
    shap.summary_plot(shap_mat, X_plot, show=False)
    ax5.set_title("SHAP Beeswarm (test slice)", fontsize=10)

    # Footer
    axf = fig.add_subplot(gs[5,:]); axf.axis("off")
    footer = (f"Outputs: {Path(run_dir).name} • CM CSV: {Path(cm_path).name} • SHAP: shap_global_importance.csv "
              f"• Calib: calibration_bins.json • Features: features_used.txt")
    axf.text(0.01, 0.5, footer, fontsize=8, va="center")

    out_pdf = Path(run_dir) / "belfast_full_report_A4.pdf"
    out_png = Path(run_dir) / "belfast_full_report_A4.png"
    fig.savefig(out_pdf, dpi=DPI, bbox_inches="tight")
    fig.savefig(out_png, dpi=DPI, bbox_inches="tight")
    print(f"[SAVED] {out_pdf}")
    print(f"[SAVED] {out_png}")
    print("[DONE]")

if __name__ == "__main__":
    # For reproducibility
    np.random.seed(RANDOM_SEED)
    main()
