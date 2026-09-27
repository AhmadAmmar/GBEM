# -*- coding: utf-8 -*-
"""
EPC vs RF — Print-Ready Map (v3.2, overlap-proof, cached)

Changes in v3.2 (requested):
- Removed the Coverage block from the Metrics card (no coverage text drawn).
- Moved the "Per-class Acc (recall)" block up and further right.
- Confusion matrix now uses class-distance colors (Correct / Off-by-1 / Off-by-2+) with
  crisp grid lines and white-stroked counts for readability.

Other highlights kept from v3.1:
- Fingerprinted cache per input set + cross-run reuse of common artifacts.
- CLI (boundary/buildings/predictions/city) for portability.
- Saves env + run report + manifest; exports to "latest/".
- Quadratic Weighted Kappa (QWK) added.
- Figure shows Macro F1 (not Macro P/R/F1).
- Small scalebar from {1,2,3,4,5} km (or --scalebar_km).
- Robust text wrapping/two-column cards → no text collisions on A4 @ 400 DPI.
"""

from __future__ import annotations
import os, sys, math, json, textwrap, warnings, hashlib, shutil, platform, glob
from datetime import datetime, timezone
from typing import List, Optional, Dict, Tuple
import argparse

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import Rectangle
from matplotlib.colors import ListedColormap
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, balanced_accuracy_score, f1_score, cohen_kappa_score
)

warnings.filterwarnings("ignore")

# ───────────────────────── Defaults (overridable by CLI) ─────────────────────────
BASE_DEFAULT     = r"D:/OneDrive - Ulster University/PhD"
OUTROOT_DEFAULT  = os.path.join(BASE_DEFAULT, "Maps", "confirm_report", "london_epc_rf_maps")
BOUNDARY_DEF     = r"D:/OneDrive - Ulster University/PhD/data/london/SHP/london.shp"
BUILDINGS_DEF    = r"D:/OneDrive - Ulster University/PhD/data/london/london_2024_epc_predictions.geojson"
PRED_DEF         = None              # if predictions live outside BUILDINGS_DEF
JOIN_BUILD_DEF   = "UPRN"
JOIN_PRED_DEF    = "UPRN"
CITY_TITLE_DEF   = "Greater London"

# Column candidates
ACTUAL_RATING_CANDS = ["CURRENT_ENERGY_RATING","EPC_RATING","epc_actual","label_true","actual_label"]
PRED_RATING_CANDS   = ["predicted_rating","PRED_EPC","pred_epc","epc_pred","label_pred","predicted_label","PRED_EPC_RATING"]
PRED_CONF_CANDS     = ["pred_conf","pred_proba_max","max_prob"]
SPLIT_CANDS         = ["split","dataset","data_split","set","phase","subset","partition","fold","cv_split"]
SPLIT_BOOL_HINTS    = ["train","valid","val","test"]

# Rendering
DPI        = 400
FIGSIZE    = (11.69, 8.27)   # A4 landscape
TARGET_CRS = 27700
RENDER_STYLE = "points"      # "points" or "polygons"

# Dot sizing
SIZE_MODE   = "auto"
TARGET_FILL = 0.010
MIN_PT      = 0.9
MAX_PT      = 1.6
DOT_PT      = 1.4
POINT_ALPHA = 0.98
POINT_MARKER = "o"

# Fonts (compact, overlap-proof)
TITLE_FS, SUBTITLE_FS, PARA_FS, PARA_SP, SMALL_FS = 10.0, 9.2, 8.4, 1.16, 8.0

# Features for quick RF importances (only if not provided)
FEATURE_CANDIDATES = [
    'B2','B3','B4','B5','B6','B7','B8','B8A','B11','B12',
    'VV','VH','L8B10','NDVI','NDBI','UI','IBI','EVI','NDWI','GNDVI',
    'VV_VH_Sum','VV_VH_Difference','VV_VH_Product','VV_VH_Normalized_Difference',
    'VH_Proportion','VV_Proportion','Advanced_Polarization_Index',
    'Moisture_Index','LSWI','BUI','Brightness_Index','SWIR_NDWI','SAVI','RE_NDVI','Albedo_Proxy'
]
MAX_IMPORTANCE_SAMPLE = 50000

# ───────────────────────── Constants ─────────────────────────
EPC_ORDER   = list("ABCDEFG")
EPC_TO_IDX  = {c:i for i,c in enumerate(EPC_ORDER)}
EPC_COLORS_DEFAULT = {"A":"#1a9850","B":"#66bd63","C":"#a6d96a","D":"#f4d166","E":"#f28e2b","F":"#e15759","G":"#a50026","NA":"#cccccc"}
EPC_COLORS_CBLIND  = {"A":"#009E73","B":"#56B4E9","C":"#F0E442","D":"#E69F00","E":"#D55E00","F":"#CC79A7","G":"#000000","NA":"#bdbdbd"}
ERR_CLASSES = ["Correct","Off-by-1","Off-by-2+"]
ERR_COLORS  = {"Correct":"#4daf4a","Off-by-1":"#ffb74d","Off-by-2+":"#e41a1c"}

# ───────────────────────── Utilities ─────────────────────────
def log(path: str, label: str): print(f"[{label}] {os.path.abspath(path)}")
def now_stamp(): return datetime.now().strftime("%Y%m%d_%H%M")
def make_dirs(*paths): [os.makedirs(p, exist_ok=True) for p in paths]

def file_fingerprint(path: str) -> str:
    st = os.stat(path)
    s = f"{os.path.abspath(path)}|{st.st_size}|{int(st.st_mtime)}"
    return hashlib.md5(s.encode("utf-8")).hexdigest()

def composite_fingerprint(paths: List[str]) -> str:
    h = hashlib.md5()
    for p in paths:
        h.update(file_fingerprint(p).encode("utf-8"))
    return h.hexdigest()

def find_col(cols: List[str], cands: List[str]) -> Optional[str]:
    low = {c.lower(): c for c in cols}
    for k in cands:
        if k.lower() in low: return low[k.lower()]
    return None

def normalize_epc(x) -> Optional[str]:
    if pd.isna(x): return None
    s = str(x).strip().upper()
    if s in EPC_TO_IDX: return s
    if s.startswith("RATING ") and s[-1] in EPC_TO_IDX: return s[-1]
    return None

def load_boundary(path: str) -> gpd.GeoDataFrame:
    log(path, "LOAD boundary")
    gdf = gpd.read_file(path)
    if gdf.crs is None: raise ValueError("Boundary has no CRS.")
    return gdf.to_crs(TARGET_CRS)

def load_buildings(path: str, layer: Optional[str]) -> gpd.GeoDataFrame:
    log(path, "LOAD buildings")
    gdf = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
    if gdf.crs is None: raise ValueError("Buildings file has no CRS.")
    return gdf.to_crs(TARGET_CRS)

def load_predictions(path: str) -> pd.DataFrame:
    log(path, "LOAD predictions")
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv": return pd.read_csv(path)
    if ext in (".parq",".parquet"): return pd.read_parquet(path)
    raise ValueError(f"Unsupported predictions file type: {ext}")

def as_points(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.empty or gdf.geom_type.isin(["Point"]).all(): return gdf
    out = gdf.copy(); out["geometry"] = out.geometry.representative_point(); return out

def auto_markersize_pt2(ax, n_points, fig, target_fill=0.010, min_pt=1.0, max_pt=2.0):
    if n_points <= 0: return min_pt**2
    bb = ax.get_position()
    fw, fh = fig.get_size_inches()
    panel_area_in2 = (bb.width * fw) * (bb.height * fh)
    area_pt2 = (72.0**2) * panel_area_in2
    s = target_fill * area_pt2 / n_points
    r_pt = math.sqrt(max(s, 1e-4))
    r_pt = min(max(r_pt, min_pt), max_pt)
    return r_pt**2

def compute_confusion_and_metrics(df: pd.DataFrame, col_true: str, col_pred: str):
    cm = pd.crosstab(df[col_true], df[col_pred], dropna=False).reindex(index=EPC_ORDER, columns=EPC_ORDER, fill_value=0)
    y_true = pd.Categorical(df[col_true], categories=EPC_ORDER)
    y_pred = pd.Categorical(df[col_pred], categories=EPC_ORDER)
    yt, yp = y_true.codes, y_pred.codes
    mask = (yt >= 0) & (yp >= 0)
    yt, yp = yt[mask], yp[mask]
    n = int(yt.size)
    if n == 0:
        metrics = {k: np.nan for k in ["Overall_Acc","Balanced_Acc","Macro_F1","Weighted_F1","Cohen_Kappa","QWK","Exact","Within1","Off2plus","Exact_%","Within1_%"]}
        metrics["N"] = 0
        per_class = {c: 0.0 for c in EPC_ORDER}
        return cm.astype(int), metrics, per_class

    overall = accuracy_score(yt, yp)
    balacc  = balanced_accuracy_score(yt, yp)
    f1_mac  = f1_score(yt, yp, average="macro", zero_division=0)
    f1_wt   = f1_score(yt, yp, average="weighted", zero_division=0)
    kappa   = cohen_kappa_score(yt, yp)
    qwk     = cohen_kappa_score(yt, yp, weights="quadratic")
    diff    = np.abs(yt - yp)
    exact   = int((diff == 0).sum())
    within1 = int((diff <= 1).sum())
    off2    = int((diff >= 2).sum())
    per_class = (np.diag(cm.values) / cm.sum(axis=1).replace(0, np.nan)).fillna(0.0).to_dict()
    metrics = {
        "N": n, "Overall_Acc": overall, "Balanced_Acc": balacc,
        "Macro_F1": f1_mac, "Weighted_F1": f1_wt,
        "Cohen_Kappa": kappa, "QWK": qwk,
        "Exact": exact, "Within1": within1, "Off2plus": off2,
        "Exact_%": exact/n, "Within1_%": within1/n
    }
    return cm.astype(int), metrics, per_class

def compute_splits(df: pd.DataFrame, col_true="EPC_ACTUAL", col_pred="EPC_PRED") -> Optional[dict]:
    cols = df.columns.tolist()
    split_col = find_col(cols, SPLIT_CANDS)
    if split_col:
        s = df[split_col].map(lambda v: str(v).strip().lower())
        all_counts = s.value_counts(dropna=False).to_dict()
        eval_mask = df[col_true].notna() & df[col_pred].notna()
        eval_counts = s[eval_mask].value_counts(dropna=False).to_dict()
        return {"source": f"column '{split_col}'", "counts_all": all_counts, "counts_eval": eval_counts}
    present = {}
    for c in cols:
        lc = c.lower()
        for hint in SPLIT_BOOL_HINTS:
            if hint in lc:
                present[hint] = c
    if present:
        cats = pd.Series(index=df.index, dtype="object")
        for k, col in present.items():
            try: mask = df[col].astype(bool)
            except Exception: continue
            cats[mask] = {"train":"train","valid":"val","val":"val","test":"test"}.get(k, k)
        cats = cats.fillna("other")
        all_counts = cats.value_counts(dropna=False).to_dict()
        eval_mask = df[col_true].notna() & df[col_pred].notna()
        eval_counts = cats[eval_mask].value_counts(dropna=False).to_dict()
        return {"source": "boolean columns " + ", ".join(present.values()),
                "counts_all": all_counts, "counts_eval": eval_counts}
    return None

def fmt_pct(x):
    try: return f"{100.0*float(x):.1f}%"
    except Exception: return "NA"

def env_meta():
    import matplotlib
    return {
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": {
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "geopandas": gpd.__version__,
            "matplotlib": matplotlib.__version__,
        }
    }

# Text drawing (wrap + optional 2 columns)
def draw_paragraph(ax, lines: List[str], x=0.03, y=0.935, width=0.94, fs=PARA_FS, linesp=PARA_SP, two_cols=False):
    max_chars = max(18, int(58 * (width / 0.94)))
    wrapped: List[str] = []
    for s in lines:
        wrapped.extend(textwrap.wrap(s, width=max_chars, break_long_words=False, break_on_hyphens=False) or [""])
    if (len(wrapped) > 16 or two_cols) and width >= 0.9:
        half = int(np.ceil(len(wrapped)/2))
        ax.text(x, y, "\n".join(wrapped[:half]),  ha="left", va="top", fontsize=fs, linespacing=linesp)
        ax.text(x+0.48, y, "\n".join(wrapped[half:]), ha="left", va="top", fontsize=fs, linespacing=linesp)
    else:
        ax.text(x, y, "\n".join(wrapped), ha="left", va="top", fontsize=fs, linespacing=linesp)

def card(ax, title: str):
    ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis("off")
    ax.add_patch(Rectangle((0,0),1,1, facecolor="white", edgecolor="#dddddd",
                           transform=ax.transAxes, zorder=0))
    ax.set_title(title, fontsize=TITLE_FS, loc="left", pad=6)

# Colored confusion matrix (by class distance) with readable labels
def draw_confusion_matrix_colored(ax, cm: pd.DataFrame):
    n = len(EPC_ORDER)
    # Base heat by distance (0,1,>=2)
    dist = np.zeros((n,n), dtype=int)
    for i in range(n):
        for j in range(n):
            dist[i,j] = min(abs(i-j), 2)
    cmap = ListedColormap(["#bfe7bf", "#ffd89a", "#f6b0b0"])  # light green / orange / red
    ax.imshow(dist, cmap=cmap, vmin=0, vmax=2, alpha=0.55, zorder=0)

    # Grid lines
    ax.set_xticks(np.arange(-.5, n, 1), minor=True)
    ax.set_yticks(np.arange(-.5, n, 1), minor=True)
    ax.grid(which="minor", color="#333", linewidth=0.6)

    # Labels and ticks
    ax.set_xticks(range(n)); ax.set_yticks(range(n))
    ax.set_xticklabels(EPC_ORDER, fontsize=SMALL_FS)
    ax.set_yticklabels(EPC_ORDER, fontsize=SMALL_FS)
    ax.set_xlabel("Predicted", fontsize=SMALL_FS)
    ax.set_ylabel("Actual", fontsize=SMALL_FS)

    # Counts
    for i in range(n):
        for j in range(n):
            v = int(cm.iloc[i, j])
            ax.text(j, i, f"{v}", ha="center", va="center", fontsize=8,
                    color="black", zorder=2,
                    path_effects=[pe.withStroke(linewidth=2.4, foreground="white")])

    # Keep square cells and visible bounds
    ax.set_xlim(-0.5, n-0.5); ax.set_ylim(n-0.5, -0.5)
    ax.set_aspect('equal', adjustable='box')

# ───────────────────────── Main ─────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Print-ready EPC vs RF maps with caching & provenance.")
    ap.add_argument("--boundary", default=BOUNDARY_DEF)
    ap.add_argument("--buildings", default=BUILDINGS_DEF)
    ap.add_argument("--predictions", default=PRED_DEF)
    ap.add_argument("--join_build", default=JOIN_BUILD_DEF)
    ap.add_argument("--join_pred", default=JOIN_PRED_DEF)
    ap.add_argument("--city", default=CITY_TITLE_DEF)
    ap.add_argument("--outroot", default=OUTROOT_DEFAULT)
    ap.add_argument("--force", action="store_true", help="Force recomputation of cached items.")
    ap.add_argument("--colorblind", action="store_true", help="Use color-blind safe palette.")
    ap.add_argument("--scalebar_km", type=float, default=None, help="Force scalebar length in km (e.g., 2).")
    args = ap.parse_args()

    OUTROOT = args.outroot
    make_dirs(OUTROOT)

    # Fingerprint & cache dirs
    fp_inputs = [args.boundary, args.buildings] + ([args.predictions] if args.predictions else [])
    fp = composite_fingerprint(fp_inputs)
    cache_dir = os.path.join(OUTROOT, "cache", f"fp_{fp}")
    make_dirs(cache_dir)
    run_dir = os.path.join(OUTROOT, f"run_{now_stamp()}")
    make_dirs(run_dir)

    # Palette
    EPC_COLORS = EPC_COLORS_CBLIND if args.colorblind else EPC_COLORS_DEFAULT

    # Cache meta (for cross-run reuse)
    cache_meta = {
        "inputs": {
            "boundary": {"path": args.boundary, "fp": file_fingerprint(args.boundary)},
            "buildings": {"path": args.buildings, "fp": file_fingerprint(args.buildings)},
            "predictions": {"path": args.predictions, "fp": (file_fingerprint(args.predictions) if args.predictions else None)},
            "join_build": args.join_build, "join_pred": args.join_pred
        }
    }
    cache_meta_json = os.path.join(cache_dir, "cache_meta.json")
    if not os.path.exists(cache_meta_json):
        with open(cache_meta_json, "w", encoding="utf-8") as f: json.dump(cache_meta, f, indent=2)
        log(cache_meta_json, "SAVE")

    # Load boundary
    boundary = load_boundary(args.boundary)
    bounds_union = boundary.geometry.unary_union

    # Try to reuse panel from this cache; else build it (or rescue from prior caches)
    panel_parquet = os.path.join(cache_dir, "panel.parquet")
    panel_gpkg    = os.path.join(cache_dir, "panel.gpkg")

    if (not args.force) and os.path.exists(panel_parquet):
        log(panel_parquet, "USE cached panel")
        bld = gpd.read_parquet(panel_parquet)
    else:
        if not os.path.exists(panel_parquet):
            prior_meta_paths = glob.glob(os.path.join(OUTROOT, "cache", "fp_*", "cache_meta.json"))
            for mpath in sorted(prior_meta_paths, key=os.path.getmtime, reverse=True):
                try:
                    with open(mpath, "r", encoding="utf-8") as f: pmeta = json.load(f)
                    if pmeta.get("inputs", {}) == cache_meta["inputs"]:
                        src_panel = os.path.join(os.path.dirname(mpath), "panel.parquet")
                        if os.path.exists(src_panel):
                            shutil.copyfile(src_panel, panel_parquet)
                            log(panel_parquet, "COPIED from prior cache")
                except Exception:
                    pass
        if os.path.exists(panel_parquet) and (not args.force):
            log(panel_parquet, "USE rescued panel")
            bld = gpd.read_parquet(panel_parquet)
        else:
            bld = load_buildings(args.buildings, layer=None)
            pred_col_in_bld = find_col(bld.columns.tolist(), PRED_RATING_CANDS)
            if (pred_col_in_bld is None) and args.predictions:
                preds = load_predictions(args.predictions)
                if args.join_build not in bld.columns or args.join_pred not in preds.columns:
                    raise KeyError("JOIN keys not found in buildings or predictions.")
                bld[args.join_build] = bld[args.join_build].astype(str)
                preds[args.join_pred] = preds[args.join_pred].astype(str)
                pred_label_col = find_col(preds.columns.tolist(), PRED_RATING_CANDS)
                pred_conf_col  = find_col(preds.columns.tolist(), PRED_CONF_CANDS)
                if pred_label_col is None:
                    raise KeyError("Predicted EPC column not found in predictions table.")
                keep = [args.join_pred, pred_label_col] + ([pred_conf_col] if pred_conf_col else [])
                preds = preds[keep].drop_duplicates(args.join_pred)
                bld = bld.merge(preds, left_on=args.join_build, right_on=args.join_pred, how="left")
                bld.rename(columns={pred_label_col: "EPC_PRED"}, inplace=True)
                if pred_conf_col: bld.rename(columns={pred_conf_col: "PRED_CONF"}, inplace=True)
            elif pred_col_in_bld is not None:
                bld.rename(columns={pred_col_in_bld: "EPC_PRED"}, inplace=True)
            else:
                raise RuntimeError("No predictions. Provide --predictions or ensure they exist in buildings file.")

            act_col = find_col(bld.columns.tolist(), ACTUAL_RATING_CANDS)
            if act_col is None: raise KeyError("Actual EPC rating column not found.")
            if act_col != "EPC_ACTUAL": bld.rename(columns={act_col:"EPC_ACTUAL"}, inplace=True)
            bld["EPC_ACTUAL"] = bld["EPC_ACTUAL"].map(normalize_epc)
            bld["EPC_PRED"]   = bld["EPC_PRED"].map(normalize_epc)

            try:
                bld = gpd.clip(bld, bounds_union)
            except Exception:
                bld = bld[bld.intersects(bounds_union)].copy()

            idx_true = bld["EPC_ACTUAL"].map(EPC_TO_IDX)
            idx_pred = bld["EPC_PRED"].map(EPC_TO_IDX)
            diff_abs = (idx_true - idx_pred).abs()
            bld["ERR_CLASS"] = np.select([diff_abs.eq(0), diff_abs.eq(1), diff_abs.ge(2)],
                                         ERR_CLASSES, default=None)

            log(panel_parquet, "SAVE"); bld.to_parquet(panel_parquet, index=False)
            try:
                log(panel_gpkg, "SAVE"); bld.to_file(panel_gpkg, layer="panel", driver="GPKG")
            except Exception as e:
                print("[WARN] GeoPackage save failed:", e)

    # Dataset stats (kept for JSON; not all shown on the figure)
    total_rows = int(len(bld))
    valid_geom = int(bld.geometry.notna().sum())
    with_actual= int(bld["EPC_ACTUAL"].notna().sum())
    with_pred  = int(bld["EPC_PRED"].notna().sum())
    eval_rows  = int((bld["EPC_ACTUAL"].notna() & bld["EPC_PRED"].notna()).sum())
    coverage   = {
        "actual_label_coverage": with_actual/max(total_rows,1),
        "pred_label_coverage":   with_pred  /max(total_rows,1),
        "eval_coverage":         eval_rows  /max(total_rows,1)
    }

    split_info = compute_splits(bld, "EPC_ACTUAL", "EPC_PRED")

    dataset_stats = {
        "total_buildings_loaded": total_rows,
        "valid_footprints": valid_geom,
        "with_actual_epc": with_actual,
        "with_predicted_epc": with_pred,
        "evaluated_rows_both_labels": eval_rows,
        "coverage": coverage,
        "per_epc_actual_total": bld["EPC_ACTUAL"].value_counts().reindex(EPC_ORDER, fill_value=0).to_dict(),
        "per_epc_pred_total":   bld["EPC_PRED"].value_counts().reindex(EPC_ORDER, fill_value=0).to_dict(),
        "error_class_counts": bld["ERR_CLASS"].value_counts().to_dict()
    }
    dataset_stats_json = os.path.join(run_dir, "dataset_stats.json")
    with open(dataset_stats_json, "w", encoding="utf-8") as f: json.dump(dataset_stats, f, indent=2); log(dataset_stats_json, "SAVE")
    if split_info:
        split_json = os.path.join(run_dir, "split_counts.json")
        with open(split_json, "w", encoding="utf-8") as f: json.dump(split_info, f, indent=2); log(split_json, "SAVE")

    # Confusion & metrics
    eval_mask = bld["EPC_ACTUAL"].notna() & bld["EPC_PRED"].notna()
    cm, metrics, per_class_acc = compute_confusion_and_metrics(bld.loc[eval_mask, ["EPC_ACTUAL","EPC_PRED"]],
                                                               "EPC_ACTUAL","EPC_PRED")
    cm_csv = os.path.join(run_dir, "confusion_matrix_counts.csv"); cm.to_csv(cm_csv); log(cm_csv, "SAVE")
    metrics_out = dict(metrics); metrics_out["PerClassAcc"] = per_class_acc
    metrics_json = os.path.join(run_dir, "metrics.json")
    with open(metrics_json, "w", encoding="utf-8") as f: json.dump(metrics_out, f, indent=2); log(metrics_json, "SAVE")

    # Importances — reuse current cache, or borrow from older compatible caches
    importances_csv = os.path.join(cache_dir, "rf_feature_importances.csv")
    importances_meta = os.path.join(cache_dir, "importances_meta.json")

    def feature_signature(cols: List[str]) -> str:
        sig = ",".join(sorted(cols))
        return hashlib.md5(sig.encode("utf-8")).hexdigest()

    present_feats = [c for c in FEATURE_CANDIDATES if c in bld.columns]
    feat_sig = feature_signature(present_feats) if present_feats else None

    feat_series, rf_params = None, None
    if (not args.force) and os.path.exists(importances_csv):
        try:
            if os.path.exists(importances_meta):
                with open(importances_meta, "r", encoding="utf-8") as f: meta = json.load(f)
                if meta.get("feature_sig") == feat_sig:
                    log(importances_csv, "USE cached importances")
                    s = pd.read_csv(importances_csv).set_index("Feature")["Importance"].astype(float)
                    feat_series = (100.0 * s / s.sum()).sort_values(ascending=False)
        except Exception:
            pass

    if feat_series is None and feat_sig:
        for mpath in sorted(glob.glob(os.path.join(OUTROOT, "cache", "fp_*", "importances_meta.json")),
                            key=os.path.getmtime, reverse=True):
            try:
                with open(mpath, "r", encoding="utf-8") as f: meta = json.load(f)
                if meta.get("feature_sig") == feat_sig:
                    src_csv = os.path.join(os.path.dirname(mpath), "rf_feature_importances.csv")
                    if os.path.exists(src_csv):
                        shutil.copyfile(src_csv, importances_csv)
                        shutil.copyfile(mpath, importances_meta)
                        log(importances_csv, "BORROWED importances (matching feature set)")
                        s = pd.read_csv(importances_csv).set_index("Feature")["Importance"].astype(float)
                        feat_series = (100.0 * s / s.sum()).sort_values(ascending=False)
                        break
            except Exception:
                pass

    if feat_series is None and present_feats and eval_rows > 0:
        df_imp = bld[present_feats + ["EPC_ACTUAL"]].dropna().copy()
        if len(df_imp) > MAX_IMPORTANCE_SAMPLE:
            df_imp = df_imp.sample(n=MAX_IMPORTANCE_SAMPLE, random_state=42)
        y = pd.Categorical(df_imp["EPC_ACTUAL"], categories=EPC_ORDER).codes
        m = y >= 0
        y = y[m]; X = df_imp.loc[m, present_feats].astype(float)
        if len(np.unique(y)) >= 2 and len(X) >= 50:
            rf = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
            rf.fit(X, y)
            s = pd.Series(rf.feature_importances_, index=present_feats)
            feat_series = (100.0 * s / s.sum()).sort_values(ascending=False)
            df_out = feat_series.rename("Importance").reset_index().rename(columns={"index":"Feature"})
            log(importances_csv, "SAVE"); df_out.to_csv(importances_csv, index=False)
            rf_params = {
                "model":"RandomForestClassifier","n_estimators":200,"criterion":"gini",
                "max_depth":None,"max_features":"sqrt","random_state":42,
                "n_used_for_importances": int(len(X))
            }
            with open(importances_meta, "w", encoding="utf-8") as f:
                json.dump({"feature_sig": feat_sig, **rf_params}, f, indent=2)
            log(importances_meta, "SAVE")

    # Env & run report
    env_json = os.path.join(run_dir, "env_meta.json")
    with open(env_json, "w", encoding="utf-8") as f: json.dump(env_meta(), f, indent=2); log(env_json, "SAVE")
    report_txt = os.path.join(run_dir, "run_report.txt")
    with open(report_txt, "w", encoding="utf-8") as f:
        f.write(f"{args.city} — EPC vs RF (run {now_stamp()})\n")
        f.write(f"N(evaluated)={metrics['N']:,}, OverallAcc={metrics['Overall_Acc']:.3f}, "
                f"BalancedAcc={metrics['Balanced_Acc']:.3f}, QWK={metrics['QWK']:.3f}, "
                f"MacroF1={metrics['Macro_F1']:.3f}\n")
        f.write(f"Exact={metrics['Exact']:,} ({fmt_pct(metrics['Exact_%'])}), "
                f"Within±1={metrics['Within1']:,} ({fmt_pct(metrics['Within1_%'])}), "
                f"Off≥2={metrics['Off2plus']:,}\n")
    log(report_txt, "SAVE")

    # ── Figure (overlap-proof)
    plt.rcParams["pdf.fonttype"] = 42; plt.rcParams["ps.fonttype"] = 42
    fig = plt.figure(figsize=FIGSIZE, dpi=DPI, constrained_layout=True)

    # Three vertical bands: maps (top), CM (middle, enlarged), metrics/splits/features (bottom)
    # Keeping top (2.35) and bottom (1.95) similar to your original; add a middle band for CM.
    sf_top, sf_mid, sf_bottom = fig.subfigures(3, 1, height_ratios=[2.35, 1.60, 1.95])

    # Maps
    axA, axB, axC = sf_top.subplots(1, 3, gridspec_kw={"wspace": 0.02})
    for ax in (axA, axB, axC):
        boundary.plot(ax=ax, facecolor="none", edgecolor="#444444", linewidth=0.6)

    plot_gdf = as_points(bld) if RENDER_STYLE == "points" else bld
    dot_area = (auto_markersize_pt2(axA, len(plot_gdf), fig, TARGET_FILL, MIN_PT, MAX_PT)
                if SIZE_MODE == "auto" else DOT_PT**2)

    def color_series(gdf, col, pal, fb="NA"):
        return gdf[col].map(lambda v: pal.get(v, pal[fb]))

    axA.set_title("A) Actual EPC Rating (A–G)", fontsize=11, loc="left"); axA.set_axis_off()
    plot_gdf.plot(ax=axA, color=color_series(plot_gdf, "EPC_ACTUAL", EPC_COLORS),
                  markersize=dot_area, marker=POINT_MARKER, alpha=POINT_ALPHA, linewidth=0, rasterized=True)

    axB.set_title("B) RF Predicted EPC Rating (A–G)", fontsize=11, loc="left"); axB.set_axis_off()
    plot_gdf.plot(ax=axB, color=color_series(plot_gdf, "EPC_PRED", EPC_COLORS),
                  markersize=dot_area, marker=POINT_MARKER, alpha=POINT_ALPHA, linewidth=0, rasterized=True)

    axC.set_title("C) Prediction Error Class", fontsize=11, loc="left"); axC.set_axis_off()
    plot_gdf.plot(ax=axC, color=plot_gdf["ERR_CLASS"].map(lambda v: ERR_COLORS.get(v, "#cccccc")),
                  markersize=dot_area, marker=POINT_MARKER, alpha=POINT_ALPHA, linewidth=0, rasterized=True)

    x0,y0,x1,y1 = bounds_union.bounds
    for ax in (axA, axB, axC):
        ax.set_xlim(x0,x1); ax.set_ylim(y0,y1)

    # Small scalebar + N arrow (on map A)
    def add_small_scalebar(ax, force_km: Optional[float]=None, loc=(0.06,0.08), max_frac=0.20):
        X0,X1 = ax.get_xlim(); Y0,Y1 = ax.get_ylim()
        width_m = (X1 - X0)
        candidates = [1,2,3,4,5]  # km
        if force_km is not None:
            length_km = float(force_km)
        else:
            length_km = candidates[-1]
            for km in reversed(candidates):
                if (km*1000.0) <= max_frac * width_m:
                    length_km = km; break
        px = X0 + loc[0]*(X1-X0); py = Y0 + loc[1]*(Y1-Y0); length_m = length_km*1000.0
        ax.add_patch(Rectangle((px,py), length_m, (Y1-Y0)*0.005, facecolor="k", edgecolor="none"))
        ax.text(px+length_m/2, py+(Y1-Y0)*0.010, f"{int(length_km)} km", ha="center", va="bottom", fontsize=8,
                color="k", path_effects=[pe.withStroke(linewidth=3, foreground="white")])

    def add_north(ax, xy=(0.10,0.22), length_frac=0.11):
        x, y = xy
        ax.annotate("", xy=(x, y+length_frac), xytext=(x, y),
                    xycoords="axes fraction", textcoords="axes fraction",
                    arrowprops=dict(arrowstyle='-|>', linewidth=1.2, color="black"))
        ax.text(x, y+length_frac+0.03, "N", transform=ax.transAxes, ha="center", va="bottom",
                fontsize=9, color="black", path_effects=[pe.withStroke(linewidth=3, foreground="white")])

    add_small_scalebar(axA, force_km=args.scalebar_km)
    add_north(axA, xy=(0.11, 0.20), length_frac=0.11)

    # ── Middle band: Confusion matrix (enlarged, directly under maps)
    axCM, axLEG_RAT, axLEG_ERR = sf_mid.subplots(
        1, 3, gridspec_kw={"wspace": 0.24},
        # Make CM axis much wider; legends slightly narrower
        width_ratios=[4.2, 0.9, 0.8]
    )
    axCM.set_title("Confusion Matrix (counts)", fontsize=TITLE_FS, loc="left", pad=6)
    draw_confusion_matrix_colored(axCM, cm)

    # EPC rating legend
    card(axLEG_RAT, "EPC Ratings (A–G)")
    ncols = 7; left=0.03; width=0.94/ncols; y0b=0.50; h=0.28
    for i, c in enumerate(EPC_ORDER):
        axLEG_RAT.add_patch(Rectangle((left + i*width, y0b), width, h,
                                      facecolor=EPC_COLORS[c], edgecolor="none", transform=axLEG_RAT.transAxes))
        axLEG_RAT.text(left + (i+0.5)*width, y0b+h/2, c, ha="center", va="center", fontsize=SUBTITLE_FS,
                       color="black", transform=axLEG_RAT.transAxes)
    axLEG_RAT.text(0.03, 0.24, "Better  →  Worse", fontsize=SMALL_FS, ha="left", transform=axLEG_RAT.transAxes)

    # Error legend
    card(axLEG_ERR, "Error Classes")
    for i, cls in enumerate(ERR_CLASSES):
        axLEG_ERR.add_patch(Rectangle((0.06, 0.74 - 0.25*i), 0.22, 0.20,
                                      facecolor=ERR_COLORS[cls], edgecolor="none", transform=axLEG_ERR.transAxes))
        axLEG_ERR.text(0.32, 0.84 - 0.25*i, cls, ha="left", va="center", fontsize=PARA_FS,
                       transform=axLEG_ERR.transAxes)

    # ── Bottom band: Metrics | Splits & Model | Features (unchanged)
    row1, row2 = sf_bottom.subfigures(2, 1, height_ratios=[1.0, 1.0])
    axMET, axSPLITS, axFEAT = row1.subplots(1, 3, gridspec_kw={"wspace": 0.24})
    card(axMET, "Accuracy Metrics"); card(axSPLITS, "Data Splits & Model Details"); card(axFEAT, "Top RF Features (% importance)")

    # Metrics text — Coverage removed; Per-class moved up/right
    left_lines = [
        f"N = {metrics['N']:,}",
        f"Overall Acc = {fmt_pct(metrics['Overall_Acc'])}",
        f"Balanced Acc = {fmt_pct(metrics['Balanced_Acc'])}",
        f"Macro F1 = {fmt_pct(metrics['Macro_F1'])}",
        f"Weighted F1 = {fmt_pct(metrics['Weighted_F1'])}",
        (f"Cohen's κ = {metrics['Cohen_Kappa']:.3f}" if pd.notna(metrics['Cohen_Kappa']) else "Cohen's κ = NA"),
        (f"Quadratic κ = {metrics['QWK']:.3f}" if pd.notna(metrics['QWK']) else "Quadratic κ = NA"),
        f"Exact = {metrics['Exact']:,} ({fmt_pct(metrics['Exact_%'])})",
        f"Within ±1 = {metrics['Within1']:,} ({fmt_pct(metrics['Within1_%'])})",
        f"Off by ≥2 = {metrics['Off2plus']:,}",
    ]
    per_class_lines = ["Per-class Acc (recall):", *[f"{c}: {fmt_pct(per_class_acc.get(c, 0))}" for c in EPC_ORDER]]

    draw_paragraph(axMET, left_lines,  x=0.03, y=0.935, width=0.50, fs=PARA_FS, linesp=PARA_SP)
    draw_paragraph(axMET, per_class_lines, x=0.64, y=0.96,  width=0.33, fs=PARA_FS, linesp=PARA_SP)

    # Splits + Model
    if split_info:
        def fmt_counts(d):
            tot = sum(d.values()) if d else 0
            p = lambda v: f"{(100*v/tot):.1f}%" if tot else "0.0%"
            other = sum(v for k,v in d.items() if k not in ("train","val","test","other",None))
            out = [f"Train = {d.get('train',0):,} ({p(d.get('train',0))})",
                   f"Val   = {d.get('val',0):,} ({p(d.get('val',0))})",
                   f"Test  = {d.get('test',0):,} ({p(d.get('test',0))})"]
            if other: out.append(f"Other = {other:,}")
            return out
        splits_left = [f"Source: {split_info['source']}"]
        if "counts_all" in split_info:  splits_left += ["All rows:"] + ["  " + s for s in fmt_counts(split_info["counts_all"])]
        if "counts_eval" in split_info: splits_left += ["Eval rows (labels present):"] + ["  " + s for s in fmt_counts(split_info["counts_eval"])]
    else:
        splits_left = ["(No split info — add 'split' column or is_train/valid/test flags.)"]

    model_right = []
    importances_meta = os.path.join(cache_dir, "importances_meta.json")
    if os.path.exists(importances_meta):
        try:
            with open(importances_meta, "r", encoding="utf-8") as f: mm = json.load(f)
            model_right.append("Importances model: RandomForest")
            for k in ["n_estimators","criterion","max_depth","max_features","random_state","n_used_for_importances"]:
                if k in mm: model_right.append(f"{k}: {mm[k]}")
        except Exception:
            model_right.append("Model details: (not provided)")
    else:
        model_right.append("Model details: (not provided)")

    draw_paragraph(axSPLITS, splits_left, x=0.03, y=0.935, width=0.45, fs=PARA_FS, linesp=PARA_SP)
    draw_paragraph(axSPLITS, model_right, x=0.53, y=0.935, width=0.44, fs=PARA_FS, linesp=PARA_SP)

    # Features
    if isinstance(feat_series, pd.Series) and not feat_series.empty:
        top_feats = [f"{k}: {v:.1f}%" for k,v in feat_series.head(14).items()]
        draw_paragraph(axFEAT, top_feats, x=0.03, y=0.935, width=0.94, fs=PARA_FS, linesp=PARA_SP, two_cols=True)
    else:
        draw_paragraph(axFEAT, ["(Feature importances not available)"], x=0.03, y=0.935, width=0.94, fs=PARA_FS, linesp=PARA_SP)

    # Title & footer
    fig.suptitle(f"{args.city} — EPC vs RF Predictions (Building-Level)", fontsize=13, y=0.996)
    foot_left = ("Data: UK EPC Register; Building footprints: OS/Verisk/OSM (as available); "
                 "Model: Random Forest (local). Coordinates: EPSG:27700.")
    foot_right = datetime.now().strftime("Map generated %Y-%m-%d")
    fig.text(0.01, 0.004, foot_left, ha="left", va="bottom", fontsize=SMALL_FS, color="#444")
    fig.text(0.99, 0.004, foot_right, ha="right", va="bottom", fontsize=SMALL_FS, color="#444")

    # Save
    fig_base = os.path.join(run_dir, f"epc_rf_results_map_{now_stamp()}")
    pdf_path = fig_base + ".pdf"; png_path = fig_base + ".png"
    fig.savefig(pdf_path, dpi=DPI); log(pdf_path, "SAVED")
    fig.savefig(png_path, dpi=DPI); log(png_path, "SAVED")
    plt.close(fig)

    # Export 'latest' (copy only if changed size or absent)
    latest_dir = os.path.join(OUTROOT, "latest"); make_dirs(latest_dir)
    def copy_if_new(src, dst_dir):
        if not src or (not os.path.exists(src)): return
        dst = os.path.join(dst_dir, os.path.basename(src))
        if (not os.path.exists(dst)) or (os.path.getsize(dst) != os.path.getsize(src)):
            shutil.copyfile(src, dst); log(dst, "COPIED -> latest")
    for src in [pdf_path, png_path, metrics_json, cm_csv, dataset_stats_json, report_txt]:
        copy_if_new(src, latest_dir)

    # Manifest
    manifest = {
        "inputs": {"boundary": args.boundary, "buildings": args.buildings, "predictions": args.predictions},
        "fingerprint": fp, "cache_dir": cache_dir, "run_dir": run_dir,
        "artifacts": {
            "panel_parquet": panel_parquet if os.path.exists(panel_parquet) else None,
            "panel_gpkg": panel_gpkg if os.path.exists(panel_gpkg) else None,
            "confusion_matrix_csv": cm_csv, "metrics_json": metrics_json,
            "dataset_stats_json": dataset_stats_json,
            "importances_csv": importances_csv if os.path.exists(importances_csv) else None,
            "importances_meta": importances_meta if os.path.exists(importances_meta) else None,
            "figure_pdf": pdf_path, "figure_png": png_path,
            "env_meta_json": env_json, "run_report_txt": report_txt,
            "latest_dir": latest_dir
        },
        "city": args.city, "colorblind_safe": args.colorblind,
        "scalebar_km": args.scalebar_km
    }
    manifest_path = os.path.join(run_dir, "figure_inputs_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f: json.dump(manifest, f, indent=2)
    log(manifest_path, "SAVE")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("[ERROR]", e)
        sys.exit(1)
