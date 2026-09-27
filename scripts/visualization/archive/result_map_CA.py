# -*- coding: utf-8 -*-
"""
London EPC vs RF Predictions — Print-Ready Map (v2.4, overlap-proof A4)

• Top row: 3 maps (Actual / Predicted / Error)
• Middle row: Confusion Matrix | EPC Ratings (A–G) | Error Classes
• Bottom row: Accuracy Metrics | Data Splits + Model Details | Top RF Features
• Auto text wrapping & two-column paragraphs (no tables), safe margins
• Logs every file read/saved
"""

from __future__ import annotations
import os, sys, math, warnings, json, textwrap
from datetime import datetime
from typing import List, Tuple, Optional, Dict

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import Rectangle

from sklearn.metrics import (
    accuracy_score, balanced_accuracy_score, precision_score,
    recall_score, f1_score, cohen_kappa_score
)
from sklearn.ensemble import RandomForestClassifier

warnings.filterwarnings("ignore")

# ── USER I/O ─────────────────────────────────────────────────────────────
OUTDIR = r"D:/OneDrive - Ulster University/PhD/Maps"
LONDON_BOUNDARY = r"D:/OneDrive - Ulster University/PhD/data/london/SHP/london.shp"
BUILDINGS_FILE  = r"D:/OneDrive - Ulster University/PhD/data/london/london_2024_epc_predictions.geojson"
BUILDINGS_LAYER = None

PREDICTIONS_FILE = None  # CSV/Parquet if predictions separate
JOIN_KEY_BUILDINGS = "UPRN"
JOIN_KEY_PRED      = "UPRN"

FEATURE_IMPORTANCE_FILE = None  # optional CSV: ["Feature","Importance"]
MODEL_META_FILE = None          # optional JSON: {"model_name":..., "params":{...}, "notes":...}

ACTUAL_RATING_CANDIDATES = ["CURRENT_ENERGY_RATING","EPC_RATING","epc_actual","label_true","actual_label"]
PRED_RATING_CANDIDATES   = ["predicted_rating","PRED_EPC","pred_epc","epc_pred","label_pred","predicted_label","PRED_EPC_RATING"]
PRED_CONF_CANDIDATES     = ["pred_conf","pred_proba_max","max_prob"]

SAVE_PDF = True
SAVE_PNG = True
DPI = 400
FIGSIZE_INCH = (11.69, 8.27)  # A4 landscape

RENDER_STYLE = "points"       # "points" or "polygons"

# Dot sizing
SIZE_MODE   = "auto"          # "auto" or "manual"
TARGET_FILL = 0.010
MIN_PT      = 0.9
MAX_PT      = 1.6
DOT_PT      = 1.4             # if SIZE_MODE="manual"
POINT_ALPHA = 0.98
POINT_MARKER = "o"

# Feature candidates for quick RF importances (if CSV not supplied)
FEATURE_CANDIDATES = [
    'B2','B3','B4','B5','B6','B7','B8','B8A','B11','B12',
    'VV','VH','L8B10','NDVI','NDBI','UI','IBI','EVI','NDWI','GNDVI',
    'VV_VH_Sum','VV_VH_Difference','VV_VH_Product','VV_VH_Normalized_Difference',
    'VH_Proportion','VV_Proportion','Advanced_Polarization_Index',
    'Moisture_Index','LSWI','BUI','Brightness_Index','SWIR_NDWI','SAVI','RE_NDVI','Albedo_Proxy'
]
MAX_IMPORTANCE_SAMPLE = 50000

# Split detection
SPLIT_COLUMN_CANDIDATES = ["split","dataset","data_split","set","phase","subset","partition","fold","cv_split"]
BOOLEAN_SPLIT_HINTS = ["train","valid","val","test"]

# ── CONSTS ──────────────────────────────────────────────────────────────
EPC_ORDER: List[str] = list("ABCDEFG")
EPC_TO_IDX = {c:i for i,c in enumerate(EPC_ORDER)}
EPC_COLORS = {"A":"#1a9850","B":"#66bd63","C":"#a6d96a","D":"#fdae61","E":"#f46d43","F":"#d73027","G":"#a50026","NA":"#cccccc"}
ERROR_CLASSES = ["Correct","Off-by-1","Off-by-2+"]
ERROR_COLORS  = {"Correct":"#4daf4a","Off-by-1":"#ffb74d","Off-by-2+":"#e41a1c"}
TARGET_CRS = 27700  # British National Grid

# ── UTILITIES ───────────────────────────────────────────────────────────
def log(path: str, label: str): print(f"[{label}] {os.path.abspath(path)}")
def ensure_outdir(path: str): os.makedirs(path, exist_ok=True)

def load_boundary(path: str) -> gpd.GeoDataFrame:
    log(path, "LOAD boundary")
    gdf = gpd.read_file(path)
    if gdf.crs is None: raise ValueError("Boundary file has no CRS.")
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

def find_first_column(cols: List[str], cands: List[str]) -> Optional[str]:
    low = {c.lower(): c for c in cols}
    for k in cands:
        if k.lower() in low: return low[k.lower()]
    return None

def normalise_epc(x) -> Optional[str]:
    if pd.isna(x): return None
    s = str(x).strip().upper()
    if s in EPC_TO_IDX: return s
    if s.startswith("RATING ") and s[-1] in EPC_TO_IDX: return s[-1]
    return None

def add_scalebar(ax, length_km: Optional[float]=None, loc=(0.06,0.08)):
    x0,x1 = ax.get_xlim(); y0,y1 = ax.get_ylim()
    extent_km = (x1-x0)/1000.0
    if length_km is None:
        raw = max(extent_km/5, 1e-6)
        pow10 = 10**math.floor(math.log10(raw))
        base = raw/pow10
        nice = 1 if base<=1 else (2 if base<=2 else (5 if base<=5 else 10))
        length_km = nice*pow10
    px = x0 + loc[0]*(x1-x0); py = y0 + loc[1]*(y1-y0); length_m = length_km*1000
    ax.add_patch(Rectangle((px,py), length_m, (y1-y0)*0.005, facecolor="k", edgecolor="none"))
    ax.text(px+length_m/2, py+(y1-y0)*0.010, f"{int(length_km)} km", ha="center", va="bottom", fontsize=8,
            color="k", path_effects=[pe.withStroke(linewidth=3, foreground="white")])

def add_north_arrow_axfrac(ax, xy=(0.10,0.22), length_frac=0.11):
    x, y = xy
    ax.annotate("", xy=(x, y+length_frac), xytext=(x, y),
                xycoords="axes fraction", textcoords="axes fraction",
                arrowprops=dict(arrowstyle='-|>', linewidth=1.2, color='k'))
    ax.text(x, y+length_frac+0.03, "N", transform=ax.transAxes, ha="center", va="bottom",
            fontsize=9, color="k", path_effects=[pe.withStroke(linewidth=3, foreground="white")])

def fmt_pct(x):
    try: return f"{100.0*float(x):.1f}%"
    except Exception: return "NA"

def compute_confusion_and_metrics(df: pd.DataFrame, col_true: str, col_pred: str):
    cm = pd.crosstab(df[col_true], df[col_pred], dropna=False)
    for c in EPC_ORDER:
        if c not in cm.index: cm.loc[c] = 0
        if c not in cm.columns: cm[c] = 0
    cm = cm.loc[EPC_ORDER, EPC_ORDER].astype(int)

    y_true = pd.Categorical(df[col_true], categories=EPC_ORDER)
    y_pred = pd.Categorical(df[col_pred], categories=EPC_ORDER)
    yt, yp = y_true.codes, y_pred.codes
    m = (yt >= 0) & (yp >= 0)
    yt, yp = yt[m], yp[m]
    n = int(yt.size)

    overall_acc = accuracy_score(yt, yp) if n else np.nan
    bal_acc     = balanced_accuracy_score(yt, yp) if n else np.nan
    p_macro     = precision_score(yt, yp, average="macro", zero_division=0) if n else np.nan
    r_macro     = recall_score(yt, yp, average="macro", zero_division=0) if n else np.nan
    f1_macro    = f1_score(yt, yp, average="macro", zero_division=0) if n else np.nan
    f1_weighted = f1_score(yt, yp, average="weighted", zero_division=0) if n else np.nan
    kappa       = cohen_kappa_score(yt, yp) if n else np.nan

    absdiff = np.abs(yt - yp) if n else np.array([])
    exact   = int((absdiff == 0).sum())
    within1 = int((absdiff <= 1).sum())
    off2    = int((absdiff >= 2).sum())

    per_class_acc = (np.diag(cm.values) / cm.sum(axis=1).replace(0, np.nan)).fillna(0.0).to_dict()

    metrics = {
        "N": n,
        "Overall_Acc": overall_acc,
        "Balanced_Acc": bal_acc,
        "Macro_Precision": p_macro,
        "Macro_Recall": r_macro,
        "Macro_F1": f1_macro,
        "Weighted_F1": f1_weighted,
        "Cohen_Kappa": kappa,
        "PerClassAcc": per_class_acc,
        "Exact": exact,
        "Within1": within1,
        "Off2plus": off2,
        "Exact_%": (exact/n if n else np.nan),
        "Within1_%": (within1/n if n else np.nan),
    }
    return cm, metrics

def _as_points(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.empty or gdf.geom_type.isin(["Point"]).all(): return gdf
    pts = gdf.copy(); pts["geometry"] = pts.geometry.representative_point(); return pts

def auto_markersize_pt2(ax, n_points, fig, target_fill=0.010, min_pt=1.0, max_pt=2.0):
    if n_points <= 0: return min_pt**2
    bb = ax.get_position()
    fig_w, fig_h = fig.get_size_inches()
    panel_area_in2 = (bb.width * fig_w) * (bb.height * fig_h)
    area_pt2 = panel_area_in2 * (72.0**2)
    s = target_fill * area_pt2 / n_points
    r_pt = math.sqrt(max(s, 1e-4))
    r_pt = min(max(r_pt, min_pt), max_pt)
    return r_pt**2

def compute_feature_importances_if_possible(
    gdf: gpd.GeoDataFrame,
    label_col: str = "EPC_ACTUAL",
    candidates: List[str] = None,
    max_rows: int = MAX_IMPORTANCE_SAMPLE
) -> Tuple[Optional[pd.Series], Optional[int], Optional[Dict]]:
    candidates = candidates or FEATURE_CANDIDATES

    if FEATURE_IMPORTANCE_FILE and os.path.exists(FEATURE_IMPORTANCE_FILE):
        log(FEATURE_IMPORTANCE_FILE, "LOAD feature_importances")
        try:
            imp = pd.read_csv(FEATURE_IMPORTANCE_FILE)
            if {"Feature","Importance"}.issubset(set(imp.columns)):
                s = imp.set_index("Feature")["Importance"].astype(float)
                s = (100.0 * s / s.sum()).sort_values(ascending=False)
                return s, None, {"source": "file"}
        except Exception:
            pass

    cols_present = [c for c in candidates if c in gdf.columns]
    if len(cols_present) < 5:
        return None, None, None

    df = gdf[cols_present + [label_col]].dropna()
    if df.empty: return None, None, None
    n_used = len(df)
    if n_used > max_rows:
        df = df.sample(n=max_rows, random_state=42)
        n_used = max_rows

    y = pd.Categorical(df[label_col], categories=EPC_ORDER).codes
    m = y >= 0
    y = y[m]; X = df.loc[m, cols_present].astype(float)
    if len(np.unique(y)) < 2: return None, None, None

    rf = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
    rf.fit(X, y)
    s = pd.Series(rf.feature_importances_, index=cols_present)
    s = (100.0 * s / s.sum()).sort_values(ascending=False)
    shown_params = {
        "model": "RandomForestClassifier",
        "n_estimators": 200,
        "criterion": "gini",
        "max_depth": None,
        "max_features": "sqrt",
        "random_state": 42,
        "n_used_for_importances": int(n_used)
    }
    return s, int(n_used), shown_params

def compute_splits(df: pd.DataFrame, label_true="EPC_ACTUAL", label_pred="EPC_PRED") -> Optional[dict]:
    cols = list(df.columns)
    split_col = find_first_column(cols, SPLIT_COLUMN_CANDIDATES)
    if split_col:
        s = df[split_col].map(lambda v: str(v).strip().lower()).fillna("unknown")
        all_counts = s.value_counts()
        eval_mask = df[label_true].notna() & df[label_pred].notna()
        eval_counts = s[eval_mask].value_counts()
        return {"source": f"column '{split_col}'",
                "counts_all": all_counts.to_dict(),
                "counts_eval": eval_counts.to_dict()}
    present = {}
    for c in cols:
        lc = c.lower()
        for hint in BOOLEAN_SPLIT_HINTS:
            if hint in lc:
                present[hint] = c
    if present:
        cats = pd.Series(index=df.index, dtype="object")
        for k, col in present.items():
            mask = df[col].astype(bool)
            cats[mask] = {"train":"train","valid":"val","val":"val","test":"test"}.get(k, k)
        cats = cats.fillna("other")
        all_counts = cats.value_counts()
        eval_mask = df[label_true].notna() & df[label_pred].notna()
        eval_counts = cats[eval_mask].value_counts()
        return {"source": "boolean columns " + ", ".join(present.values()),
                "counts_all": all_counts.to_dict(),
                "counts_eval": eval_counts.to_dict()}
    return None

# ── PARAGRAPH RENDERER (width-aware wrap, no tables) ────────────────────
def card(ax, title: str):
    ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis("off")
    ax.add_patch(Rectangle((0,0),1,1, facecolor="white", edgecolor="#dddddd",
                           transform=ax.transAxes, zorder=0))
    ax.set_title(title, fontsize=10, loc="left", pad=6)

def wrap_lines(lines: List[str], width_frac: float, base_chars_fullwidth=58) -> List[str]:
    """Approximate line wrapping by character count derived from axes width fraction."""
    max_chars = max(18, int(base_chars_fullwidth * (width_frac / 0.94)))
    out: List[str] = []
    for s in lines:
        out.extend(textwrap.wrap(s, width=max_chars, break_long_words=False, break_on_hyphens=False) or [""])
    return out

def draw_paragraph(ax, text_lines: List[str], x=0.03, y=0.935, width=0.94,
                   fs=8.4, linespacing=1.16, colsplit=False):
    """Draw a wrapped 1- or 2-column paragraph inside a card axes."""
    if not text_lines: return
    lines = wrap_lines(text_lines, width_frac=width)

    if (len(lines) > 16 or colsplit) and width >= 0.9:
        half = int(np.ceil(len(lines)/2))
        left = "\n".join(lines[:half])
        right = "\n".join(lines[half:])
        ax.text(x, y, left, ha="left", va="top", fontsize=fs, linespacing=linespacing)
        ax.text(x + 0.48, y, right, ha="left", va="top", fontsize=fs, linespacing=linespacing)
    else:
        para = "\n".join(lines)
        ax.text(x, y, para, ha="left", va="top", fontsize=fs, linespacing=linespacing)

# ── MAIN ────────────────────────────────────────────────────────────────
def main():
    ensure_outdir(OUTDIR)

    # Load
    lon_boundary = load_boundary(LONDON_BOUNDARY)
    lon_bounds_union = lon_boundary.geometry.unary_union
    bld = load_buildings(BUILDINGS_FILE, BUILDINGS_LAYER)

    have_pred_in_bld = find_first_column(bld.columns.tolist(), PRED_RATING_CANDIDATES)
    if have_pred_in_bld is None and PREDICTIONS_FILE:
        pred = load_predictions(PREDICTIONS_FILE)
        bld[JOIN_KEY_BUILDINGS] = bld[JOIN_KEY_BUILDINGS].astype(str)
        pred[JOIN_KEY_PRED]     = pred[JOIN_KEY_PRED].astype(str)
        pred_label_col = find_first_column(pred.columns.tolist(), PRED_RATING_CANDIDATES)
        if pred_label_col is None:
            raise KeyError("Predicted EPC column not found in predictions table.")
        pred_conf_col  = find_first_column(pred.columns.tolist(), PRED_CONF_CANDIDATES)
        keep = [JOIN_KEY_PRED, pred_label_col] + ([pred_conf_col] if pred_conf_col else [])
        pred_slim = pred[keep].drop_duplicates(JOIN_KEY_PRED)
        bld = bld.merge(pred_slim, left_on=JOIN_KEY_BUILDINGS, right_on=JOIN_KEY_PRED, how="left")
        bld.rename(columns={pred_label_col:"EPC_PRED"}, inplace=True)
        if pred_conf_col: bld.rename(columns={pred_conf_col:"PRED_CONF"}, inplace=True)
    elif have_pred_in_bld is not None:
        bld.rename(columns={have_pred_in_bld:"EPC_PRED"}, inplace=True)
    else:
        raise RuntimeError("Predicted EPC not found; provide PREDICTIONS_FILE or include it in BUILDINGS_FILE.")

    actual_col = find_first_column(bld.columns.tolist(), ACTUAL_RATING_CANDIDATES)
    if actual_col is None: raise KeyError("Actual EPC rating column not found.")
    if actual_col != "EPC_ACTUAL": bld.rename(columns={actual_col:"EPC_ACTUAL"}, inplace=True)

    bld["EPC_ACTUAL"] = bld["EPC_ACTUAL"].map(normalise_epc)
    bld["EPC_PRED"]   = bld["EPC_PRED"].map(normalise_epc)
    try:
        bld = gpd.clip(bld, lon_bounds_union)
    except Exception:
        bld = bld[bld.intersects(lon_bounds_union)].copy()

    # Error classes & metrics
    idx_true = bld["EPC_ACTUAL"].map(EPC_TO_IDX)
    idx_pred = bld["EPC_PRED"].map(EPC_TO_IDX)
    diff = (idx_true - idx_pred).abs()
    bld["ERR_CLASS"] = np.select([diff.eq(0), diff.eq(1), diff.ge(2)], ERROR_CLASSES, default=None)

    mask_eval = idx_true.notna() & idx_pred.notna()
    cm, metrics = compute_confusion_and_metrics(bld.loc[mask_eval, ["EPC_ACTUAL","EPC_PRED"]], "EPC_ACTUAL", "EPC_PRED")

    # Splits & model details
    split_info = compute_splits(bld, "EPC_ACTUAL", "EPC_PRED")
    model_meta = None
    if MODEL_META_FILE and os.path.exists(MODEL_META_FILE):
        log(MODEL_META_FILE, "LOAD model_meta")
        try:
            with open(MODEL_META_FILE, "r", encoding="utf-8") as f:
                model_meta = json.load(f)
        except Exception:
            model_meta = None

    # Feature importances
    feat_series, imp_n_used, rf_params = compute_feature_importances_if_possible(bld, label_col="EPC_ACTUAL")
    top_feats = [f"{k}: {v:.1f}%" for k, v in (feat_series.head(14).items() if isinstance(feat_series, pd.Series) else [])]

    # ── FIGURE (constrained layout, generous foot margin) ───────────────
    plt.rcParams["pdf.fonttype"] = 42; plt.rcParams["ps.fonttype"] = 42
    fig = plt.figure(figsize=FIGSIZE_INCH, dpi=DPI, constrained_layout=True)

    # Two big bands; extra height for bottom to avoid footer collisions
    sf_top, sf_bottom = fig.subfigures(2, 1, height_ratios=[2.35, 1.95])

    # TOP: maps
    axA, axB, axC = sf_top.subplots(1, 3, gridspec_kw={"wspace": 0.02})
    for ax in (axA, axB, axC):
        lon_boundary.plot(ax=ax, facecolor="none", edgecolor="#333333", linewidth=0.6)

    plot_pts = _as_points(bld)
    DOT_AREA = auto_markersize_pt2(axA, len(plot_pts), fig, target_fill=TARGET_FILL, min_pt=MIN_PT, max_pt=MAX_PT)

    def cseries(gdf, col, pal, default_key):
        return gdf[col].map(lambda v: pal.get(v, pal[default_key]))

    # draw maps
    for ax, col, title in [(axA,"EPC_ACTUAL","A) Actual EPC Rating (A–G)"),
                           (axB,"EPC_PRED","B) RF Predicted EPC Rating (A–G)")]:
        ax.set_title(title, fontsize=11, loc="left"); ax.set_axis_off()
        plot_pts.plot(ax=ax, color=cseries(plot_pts, col, EPC_COLORS, "NA"),
                      markersize=DOT_AREA, marker=POINT_MARKER,
                      alpha=POINT_ALPHA, linewidth=0, rasterized=True)

    axC.set_title("C) Prediction Error Class", fontsize=11, loc="left"); axC.set_axis_off()
    plot_pts.plot(ax=axC, color=plot_pts["ERR_CLASS"].map(lambda v: ERROR_COLORS.get(v, "#cccccc")),
                  markersize=DOT_AREA, marker=POINT_MARKER, alpha=POINT_ALPHA, linewidth=0, rasterized=True)

    x0,y0,x1,y1 = lon_bounds_union.bounds
    for ax in (axA, axB, axC):
        ax.set_xlim(x0,x1); ax.set_ylim(y0,y1)
    add_scalebar(axA); add_north_arrow_axfrac(axA, xy=(0.11, 0.20), length_frac=0.11)

    # BOTTOM: two rows
    row1, row2 = sf_bottom.subfigures(2, 1, height_ratios=[1.0, 1.0])

    # Row 1: CM | EPC legend | Error legend
    axCM, axLEG_RAT, axLEG_ERR = row1.subplots(1, 3, gridspec_kw={"wspace": 0.24}, width_ratios=[1.35, 1.2, 1.0])
    axCM.set_title("Confusion Matrix (counts)", fontsize=10, loc="left", pad=6)
    axCM.imshow(cm.values, cmap="Greys", interpolation="nearest")
    axCM.set_xticks(range(len(EPC_ORDER))); axCM.set_yticks(range(len(EPC_ORDER)))
    axCM.set_xticklabels(EPC_ORDER, fontsize=8); axCM.set_yticklabels(EPC_ORDER, fontsize=8)
    axCM.set_xlabel("Predicted", fontsize=9); axCM.set_ylabel("Actual", fontsize=9)
    for i in range(len(EPC_ORDER)):
        for j in range(len(EPC_ORDER)):
            v = cm.iloc[i,j]
            axCM.text(j, i, f"{v}", ha="center", va="center", fontsize=7,
                      color="black", path_effects=[pe.withStroke(linewidth=2, foreground="white")])

    def card(ax, title: str):
        ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis("off")
        ax.add_patch(Rectangle((0,0),1,1, facecolor="white", edgecolor="#dddddd",
                               transform=ax.transAxes, zorder=0))
        ax.set_title(title, fontsize=10, loc="left", pad=6)

    # EPC legend bar
    card(axLEG_RAT, "EPC Ratings (A–G)")
    ncols = 7; left=0.03; width=0.94/ncols; y0b=0.50; h=0.28
    for i,c in enumerate(EPC_ORDER):
        axLEG_RAT.add_patch(Rectangle((left + i*width, y0b), width, h,
                                      facecolor=EPC_COLORS[c], edgecolor="none", transform=axLEG_RAT.transAxes))
        axLEG_RAT.text(left + (i+0.5)*width, y0b+h/2, c, ha="center", va="center",
                       fontsize=10, color="black", transform=axLEG_RAT.transAxes)
    axLEG_RAT.text(0.03, 0.24, "Better  →  Worse", fontsize=8, ha="left", transform=axLEG_RAT.transAxes)

    # Error legend
    card(axLEG_ERR, "Error Classes")
    for i, cls in enumerate(ERROR_CLASSES):
        axLEG_ERR.add_patch(Rectangle((0.06, 0.74 - 0.25*i), 0.22, 0.20,
                                      facecolor=ERROR_COLORS[cls], edgecolor="none",
                                      transform=axLEG_ERR.transAxes))
        axLEG_ERR.text(0.32, 0.84 - 0.25*i, cls, ha="left", va="center", fontsize=9,
                       transform=axLEG_ERR.transAxes)

    # Row 2: Metrics | Splits+Model | Features
    axMET, axSPLITS, axFEAT = row2.subplots(1, 3, gridspec_kw={"wspace": 0.24})
    card(axMET,   "Accuracy Metrics")
    card(axSPLITS,"Data Splits & Model Details")
    card(axFEAT,  "Top RF Features (% importance)")

    # Metrics — shorten long line to prevent wrap into right column
    m = metrics
    left_lines = [
        f"N = {m['N']:,}",
        f"Overall Acc = {fmt_pct(m['Overall_Acc'])}",
        f"Balanced Acc = {fmt_pct(m['Balanced_Acc'])}",
        "Macro P/R/F1 = " + " / ".join([fmt_pct(m['Macro_Precision']), fmt_pct(m['Macro_Recall']), fmt_pct(m['Macro_F1'])]),
        f"Weighted F1 = {fmt_pct(m['Weighted_F1'])}",
        f"Cohen's κ = {m['Cohen_Kappa']:.3f}" if pd.notna(m['Cohen_Kappa']) else "Cohen's κ = NA",
        f"Exact = {m['Exact']:,} ({fmt_pct(m['Exact_%'])})",
        f"Within ±1 = {m['Within1']:,} ({fmt_pct(m['Within1_%'])})",
        f"Off by ≥2 = {m['Off2plus']:,}",
    ]
    pc = m["PerClassAcc"]
    right_lines = ["Per-class Acc (recall):"] + [f"{c}: {fmt_pct(pc.get(c,0))}" for c in EPC_ORDER]
    draw_paragraph(axMET, left_lines,  x=0.03, y=0.935, width=0.46, fs=8.6, linespacing=1.18)
    draw_paragraph(axMET, right_lines, x=0.54, y=0.935, width=0.43, fs=8.6, linespacing=1.18)

    # Splits (left) + Model (right) in one card (prevents footer collision)
    split_lines = []
    if split_info:
        def fmt_counts(dd):
            tot = sum(dd.values()) if dd else 0
            p = lambda v: f"{(100*v/tot):.1f}%" if tot else "0.0%"
            other = sum(v for k,v in dd.items() if k not in ("train","val","test"))
            return [
                f"Train = {dd.get('train',0):,} ({p(dd.get('train',0))})",
                f"Val   = {dd.get('val',0):,} ({p(dd.get('val',0))})",
                f"Test  = {dd.get('test',0):,} ({p(dd.get('test',0))})",
                *( [f"Other = {other:,}"] if other else [] )
            ]
        split_lines.append(f"Source: {split_info['source']}")
        split_lines.append("All rows:")
        split_lines += ["  " + s for s in fmt_counts(split_info.get("counts_all", {}))]
        split_lines.append("Eval rows (labels present):")
        split_lines += ["  " + s for s in fmt_counts(split_info.get("counts_eval", {}))]
    else:
        split_lines = ["(No split info — add 'split' column or is_train/valid/test.)"]

    model_lines = []
    if MODEL_META_FILE and model_meta:
        name = model_meta.get("model_name","(model)")
        model_lines.append(f"Model: {name}")
        params = model_meta.get("params",{})
        for k,v in list(params.items())[:6]:
            model_lines.append(f"{k}: {v}")
        if model_meta.get("notes"):
            notes = str(model_meta["notes"])
            model_lines.append(f"Notes: {notes[:70]}{'…' if len(notes)>70 else ''}")
    elif rf_params:
        model_lines.append("Importances model: RandomForest")
        for k in ["n_estimators","criterion","max_depth","max_features","random_state","n_used_for_importances"]:
            if k in rf_params:
                model_lines.append(f"{k}: {rf_params[k]}")
    else:
        model_lines.append("Model details: (not provided)")

    # two side-by-side paragraphs in this card
    draw_paragraph(axSPLITS, split_lines, x=0.03, y=0.935, width=0.45, fs=8.4, linespacing=1.16)
    draw_paragraph(axSPLITS, model_lines, x=0.53, y=0.935, width=0.44, fs=8.4, linespacing=1.16)

    # Features (auto split to two columns if many)
    if top_feats:
        draw_paragraph(axFEAT, top_feats, x=0.03, y=0.935, width=0.94, fs=8.4, linespacing=1.16, colsplit=True)
    else:
        draw_paragraph(axFEAT, ["(Not available from inputs)"], x=0.03, y=0.935, width=0.94, fs=8.6, linespacing=1.18)

    # Title & footers (safe margin)
    fig.suptitle("Greater London — EPC vs RF Predictions (Building-Level)", fontsize=13, y=0.996)
    foot_left = ("Data: UK EPC Register; Building footprints: OS/Verisk/OSM (as available); "
                 "Model: Random Forest (London). Coordinates: EPSG:27700.")
    foot_right = datetime.now().strftime("Map generated %Y-%m-%d")
    fig.text(0.01, 0.004, foot_left, ha="left", va="bottom", fontsize=8, color="#444")
    fig.text(0.99, 0.004, foot_right, ha="right", va="bottom", fontsize=8, color="#444")

    # Save
    base = f"london_epc_rf_results_map_{datetime.now().strftime('%Y%m%d_%H%M')}"
    ensure_outdir(OUTDIR)
    if SAVE_PDF:
        pdf_path = os.path.join(OUTDIR, base + ".pdf")
        fig.savefig(pdf_path, dpi=DPI)
        log(pdf_path, "SAVED")
    if SAVE_PNG:
        png_path = os.path.join(OUTDIR, base + ".png")
        fig.savefig(png_path, dpi=DPI)
        log(png_path, "SAVED")
    plt.close(fig)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("[ERROR]", e)
        sys.exit(1)
