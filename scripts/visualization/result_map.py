# -*- coding: utf-8 -*-
"""
London EPC vs RF Predictions — Print-Ready Map (v1.4) — All Points + Auto Point Size
"""

from __future__ import annotations
import os, sys, math, warnings
from datetime import datetime
from typing import List, Tuple, Optional

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Rectangle, FancyArrowPatch
import matplotlib.patheffects as pe

warnings.filterwarnings("ignore")

# ─────────────────────────────── USER I/O ───────────────────────────────
OUTDIR = r"D:/OneDrive - Ulster University/PhD/Maps"
LONDON_BOUNDARY = r"D:/OneDrive - Ulster University/PhD/data/London/SHP/london.shp"
BUILDINGS_FILE  = r"D:/OneDrive - Ulster University/PhD/Data/London/london_2024_epc_predictions.geojson"
BUILDINGS_LAYER = None
PREDICTIONS_FILE = None
JOIN_KEY_BUILDINGS = "UPRN"
JOIN_KEY_PRED = "UPRN"

ACTUAL_RATING_CANDIDATES = ["CURRENT_ENERGY_RATING","EPC_RATING","epc_actual","label_true","actual_label"]
PRED_RATING_CANDIDATES   = ["predicted_rating","PRED_EPC","pred_epc","epc_pred","label_pred","predicted_label","PRED_EPC_RATING"]
PRED_CONF_CANDIDATES     = ["pred_conf","pred_proba_max","max_prob"]

# Plotting controls
SAVE_PDF = True
SAVE_PNG = True
DPI = 400
FIGSIZE_INCH = (11.69, 8.27)  # A4 landscape
PANEL_BORDER = True

# Rendering style
RENDER_STYLE = "points"     # "points" or "polygons"

# Point-size control
SIZE_MODE = "auto"          # "auto" or "manual"
TARGET_FILL = 0.010         # ~1.0% of the panel area covered by dots
MIN_PT = 1.0                # clamp radius in points
MAX_PT = 2.2
DOT_PT = 1.8                # used only when SIZE_MODE="manual"
POINT_ALPHA = 0.98
POINT_MARKER = "o"

# ───────────────────────────── CONST/PALETTES ───────────────────────────
EPC_ORDER: List[str] = list("ABCDEFG")
EPC_TO_IDX = {c:i for i,c in enumerate(EPC_ORDER)}
EPC_COLORS = {"A":"#1a9850","B":"#66bd63","C":"#a6d96a","D":"#fdae61","E":"#f46d43","F":"#d73027","G":"#a50026","NA":"#cccccc"}
ERROR_CLASSES = ["Correct","Off-by-1","Off-by-2+"]
ERROR_COLORS  = {"Correct":"#4daf4a","Off-by-1":"#ffb74d","Off-by-2+":"#e41a1c"}
TARGET_CRS = 27700  # BNG

# ────────────────────────────── UTILITIES ───────────────────────────────
def ensure_outdir(path: str): os.makedirs(path, exist_ok=True)

def load_boundary(path: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    if gdf.crs is None: raise ValueError("Boundary file has no CRS.")
    return gdf.to_crs(TARGET_CRS)

def load_buildings(path: str, layer: Optional[str]) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
    if gdf.crs is None: raise ValueError("Buildings file has no CRS.")
    return gdf.to_crs(TARGET_CRS)

def load_predictions(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv": return pd.read_csv(path)
    if ext in (".parq", ".parquet"): return pd.read_parquet(path)
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

def add_scalebar(ax, length_km: Optional[float]=None, loc: Tuple[float,float]=(0.05,0.05)):
    x0,x1 = ax.get_xlim(); y0,y1 = ax.get_ylim()
    extent_km = (x1-x0)/1000.0
    if length_km is None:
        raw = max(extent_km/5, 1e-6); pow10 = 10**math.floor(math.log10(raw))
        base = raw/pow10; nice = 1 if base<=1 else (2 if base<=2 else (5 if base<=5 else 10))
        length_km = nice*pow10
    px = x0 + loc[0]*(x1-x0); py = y0 + loc[1]*(y1-y0); length_m = length_km*1000
    ax.add_patch(Rectangle((px,py), length_m, (y1-y0)*0.005, facecolor="k", edgecolor="none"))
    ax.text(px+length_m/2, py+(y1-y0)*0.008, f"{int(length_km)} km", ha="center", va="bottom", fontsize=8,
            color="k", path_effects=[pe.withStroke(linewidth=3, foreground="white")])

def add_north_arrow(ax, loc: Tuple[float,float]=(0.95,0.12)):
    x0,x1 = ax.get_xlim(); y0,y1 = ax.get_ylim()
    px = x0 + loc[0]*(x1-x0); py = y0 + loc[1]*(y1-y0); size = (y1-y0)*0.06
    arr = FancyArrowPatch((px,py), (px,py+size), arrowstyle='-|>', mutation_scale=12,
                          linewidth=1.2, facecolor='k', edgecolor='k')
    ax.add_patch(arr)
    ax.text(px, py+size+(y1-y0)*0.01, 'N', ha='center', va='bottom', fontsize=9,
            color='k', path_effects=[pe.withStroke(linewidth=3, foreground='white')])

def epc_legend_patches() -> List[Rectangle]:
    return [Rectangle((0,0),1,1,facecolor=EPC_COLORS[c], edgecolor='none') for c in EPC_ORDER]

def compute_confusion_stats(df: pd.DataFrame, col_true: str, col_pred: str):
    cm = pd.crosstab(df[col_true], df[col_pred], dropna=False)
    for c in EPC_ORDER:
        if c not in cm.index: cm.loc[c] = 0
        if c not in cm.columns: cm[c] = 0
    cm = cm.loc[EPC_ORDER, EPC_ORDER].astype(int)
    idx_true = df[col_true].map(EPC_TO_IDX); idx_pred = df[col_pred].map(EPC_TO_IDX)
    diff = (idx_true - idx_pred).abs(); n = len(df)
    metrics = {"N":int(n), "Exact":int((diff==0).sum()),
               "Within1":int((diff<=1).sum()), "Off2plus":int((diff>=2).sum())}
    metrics["Exact_%"] = 100.0*metrics["Exact"]/max(n,1)
    metrics["Within1_%"] = 100.0*metrics["Within1"]/max(n,1)
    return cm, metrics

def draw_confusion_matrix(ax, cm: pd.DataFrame):
    ax.imshow(cm.values, cmap="Greys", interpolation="nearest")
    ax.set_xticks(range(len(EPC_ORDER))); ax.set_yticks(range(len(EPC_ORDER)))
    ax.set_xticklabels(EPC_ORDER, fontsize=8); ax.set_yticklabels(EPC_ORDER, fontsize=8)
    ax.set_xlabel("Predicted", fontsize=9); ax.set_ylabel("Actual", fontsize=9)
    for i in range(len(EPC_ORDER)):
        for j in range(len(EPC_ORDER)):
            v = cm.iloc[i,j]
            ax.text(j, i, f"{v}", ha="center", va="center", fontsize=7,
                    color="black", path_effects=[pe.withStroke(linewidth=2, foreground="white")])
    ax.grid(False)

def _as_points(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.empty or gdf.geom_type.isin(["Point"]).all(): return gdf
    pts = gdf.copy(); pts["geometry"] = pts.geometry.representative_point(); return pts

# ────────────────────────────── MAIN ───────────────────────────────
def main():
    ensure_outdir(OUTDIR)

    # 1) Boundary & buildings
    lon_boundary = load_boundary(LONDON_BOUNDARY)
    lon_bounds_union = lon_boundary.geometry.unary_union
    bld = load_buildings(BUILDINGS_FILE, BUILDINGS_LAYER)

    # 2) Join predictions if needed
    have_pred_in_bld = find_first_column(bld.columns.tolist(), PRED_RATING_CANDIDATES)
    if have_pred_in_bld is None and PREDICTIONS_FILE:
        pred = load_predictions(PREDICTIONS_FILE)
        bld[JOIN_KEY_BUILDINGS] = bld[JOIN_KEY_BUILDINGS].astype(str)
        pred[JOIN_KEY_PRED] = pred[JOIN_KEY_PRED].astype(str)
        pred_label_col = find_first_column(pred.columns.tolist(), PRED_RATING_CANDIDATES)
        if pred_label_col is None:
            raise KeyError("Predicted EPC column not found in predictions table.")
        pred_conf_col = find_first_column(pred.columns.tolist(), PRED_CONF_CANDIDATES)
        keep = [JOIN_KEY_PRED, pred_label_col] + ([pred_conf_col] if pred_conf_col else [])
        pred_slim = pred[keep].drop_duplicates(JOIN_KEY_PRED)
        bld = bld.merge(pred_slim, left_on=JOIN_KEY_BUILDINGS, right_on=JOIN_KEY_PRED, how="left")
        bld.rename(columns={pred_label_col: "EPC_PRED"}, inplace=True)
        if pred_conf_col: bld.rename(columns={pred_conf_col: "PRED_CONF"}, inplace=True)
    elif have_pred_in_bld is not None:
        bld.rename(columns={have_pred_in_bld: "EPC_PRED"}, inplace=True)
    else:
        raise RuntimeError("Predicted EPC not found; provide PREDICTIONS_FILE or include it in BUILDINGS_FILE.")

    # 3) Actual column
    actual_col = find_first_column(bld.columns.tolist(), ACTUAL_RATING_CANDIDATES)
    if actual_col is None: raise KeyError("Actual EPC rating column not found.")
    if actual_col != "EPC_ACTUAL": bld.rename(columns={actual_col: "EPC_ACTUAL"}, inplace=True)

    # 4) Normalise & clip
    bld["EPC_ACTUAL"] = bld["EPC_ACTUAL"].map(normalise_epc)
    bld["EPC_PRED"]   = bld["EPC_PRED"].map(normalise_epc)
    try:
        bld = gpd.clip(bld, lon_bounds_union)
    except Exception:
        bld = bld[bld.intersects(lon_bounds_union)].copy()

    # 5) Error classes
    bld["_idx_true"] = bld["EPC_ACTUAL"].map(EPC_TO_IDX)
    bld["_idx_pred"] = bld["EPC_PRED"].map(EPC_TO_IDX)
    bld["_absdiff"]  = (bld["_idx_true"] - bld["_idx_pred"]).abs()
    bld["ERR_CLASS"] = np.select(
        [bld["_absdiff"].eq(0), bld["_absdiff"].eq(1), bld["_absdiff"].ge(2)],
        ERROR_CLASSES, default=None,
    )

    # 6) Metrics
    mask_eval = bld["_idx_true"].notna() & bld["_idx_pred"].notna()
    eval_df = bld.loc[mask_eval, ["EPC_ACTUAL","EPC_PRED"]].copy()
    cm, metrics = compute_confusion_stats(eval_df, "EPC_ACTUAL", "EPC_PRED")

    # 7) Prepare plotting data
    plot_gdf = bld
    plot_pts = _as_points(plot_gdf)

    # 8) Figure & axes
    plt.rcParams["pdf.fonttype"] = 42; plt.rcParams["ps.fonttype"] = 42
    fig = plt.figure(figsize=FIGSIZE_INCH, dpi=DPI)
    gs = GridSpec(2, 3, figure=fig, height_ratios=[18, 6], width_ratios=[1,1,1], wspace=0.02, hspace=0.08)
    axA = fig.add_subplot(gs[0,0]); axB = fig.add_subplot(gs[0,1]); axC = fig.add_subplot(gs[0,2])
    axCM = fig.add_subplot(gs[1,0]); axLEG_RAT = fig.add_subplot(gs[1,1]); axLEG_ERR = fig.add_subplot(gs[1,2])

    for ax in (axA, axB, axC, axCM, axLEG_RAT, axLEG_ERR):
        for s in ax.spines.values():
            s.set_visible(PANEL_BORDER); s.set_linewidth(0.6 if PANEL_BORDER else 0)

    # Background boundary
    for ax in (axA, axB, axC):
        lon_boundary.plot(ax=ax, facecolor="none", edgecolor="#333333", linewidth=0.6)

    # Helper colorers
    def cseries(gdf, col, pal, default_key):
        return gdf[col].map(lambda v: pal.get(v, pal[default_key]))

    # Auto markersize (pt^2) based on panel area & target fill
    def auto_markersize_pt2(ax, n_points, target_fill=TARGET_FILL, min_pt=MIN_PT, max_pt=MAX_PT):
        if n_points <= 0: return (min_pt**2)
        bb = ax.get_position()  # figure fraction
        fig_w, fig_h = fig.get_size_inches()
        panel_area_in2 = (bb.width * fig_w) * (bb.height * fig_h)
        area_pt2 = panel_area_in2 * (72.0**2)
        s = target_fill * area_pt2 / n_points
        r_pt = math.sqrt(max(s, 0.0001))
        r_pt = min(max(r_pt, min_pt), max_pt)
        return r_pt**2

    if RENDER_STYLE == "points":
        if SIZE_MODE == "auto":
            DOT_AREA = auto_markersize_pt2(axA, len(plot_pts))
        else:
            DOT_AREA = float(DOT_PT)**2

    # PANEL A
    axA.set_title("A) Actual EPC Rating (A–G)", fontsize=11, loc="left"); axA.set_axis_off()
    if RENDER_STYLE == "points":
        plot_pts.plot(ax=axA, color=cseries(plot_pts, "EPC_ACTUAL", EPC_COLORS, "NA"),
                      markersize=DOT_AREA, marker=POINT_MARKER,
                      alpha=POINT_ALPHA, linewidth=0, rasterized=True)
    else:
        plot_gdf.plot(ax=axA, color=cseries(plot_gdf, "EPC_ACTUAL", EPC_COLORS, "NA"),
                      linewidth=0, rasterized=True)
    add_scalebar(axA); add_north_arrow(axA)

    # PANEL B
    axB.set_title("B) RF Predicted EPC Rating (A–G)", fontsize=11, loc="left"); axB.set_axis_off()
    if RENDER_STYLE == "points":
        plot_pts.plot(ax=axB, color=cseries(plot_pts, "EPC_PRED", EPC_COLORS, "NA"),
                      markersize=DOT_AREA, marker=POINT_MARKER,
                      alpha=POINT_ALPHA, linewidth=0, rasterized=True)
    else:
        plot_gdf.plot(ax=axB, color=cseries(plot_gdf, "EPC_PRED", EPC_COLORS, "NA"),
                      linewidth=0, rasterized=True)

    # PANEL C
    axC.set_title("C) Prediction Error Class", fontsize=11, loc="left"); axC.set_axis_off()
    if RENDER_STYLE == "points":
        plot_pts.plot(ax=axC, color=plot_pts["ERR_CLASS"].map(lambda v: ERROR_COLORS.get(v, "#cccccc")),
                      markersize=DOT_AREA, marker=POINT_MARKER,
                      alpha=POINT_ALPHA, linewidth=0, rasterized=True)
    else:
        plot_gdf.plot(ax=axC, color=plot_gdf["ERR_CLASS"].map(lambda v: ERROR_COLORS.get(v, "#cccccc")),
                      linewidth=0, rasterized=True)

    # Sync extents
    x0,y0,x1,y1 = lon_bounds_union.bounds
    for ax in (axA, axB, axC):
        ax.set_xlim(x0,x1); ax.set_ylim(y0,y1)

    # CM + legends
    axCM.set_title("Confusion Matrix (counts)", fontsize=10, loc="left")
    draw_confusion_matrix(axCM, cm)

    axLEG_RAT.set_title("Legend — EPC Ratings", fontsize=10, loc="left"); axLEG_RAT.axis("off")
    patches = epc_legend_patches(); labels = EPC_ORDER; ncols = 7
    for i,(p,lab) in enumerate(zip(patches, labels)):
        axLEG_RAT.add_patch(Rectangle((i,0), 1, 0.6, facecolor=p.get_facecolor(), edgecolor="none"))
        axLEG_RAT.text(i+0.5, 0.3, lab, ha="center", va="center", fontsize=9)
    axLEG_RAT.set_xlim(0,ncols); axLEG_RAT.set_ylim(0,0.8)

    axLEG_ERR.set_title("Legend — Error Classes", fontsize=10, loc="left"); axLEG_ERR.axis("off")
    for i,cls in enumerate(ERROR_CLASSES):
        axLEG_ERR.add_patch(Rectangle((0,i), 0.5, 0.5, facecolor=ERROR_COLORS[cls], edgecolor="none"))
        axLEG_ERR.text(0.7, i+0.25, cls, ha="left", va="center", fontsize=9)
    axLEG_ERR.set_xlim(0,5); axLEG_ERR.set_ylim(0,3)

    metrics_lines = [
        f"N = {metrics['N']:,}",
        f"Exact match = {metrics['Exact']:,} ({metrics['Exact_%']:.1f}%)",
        f"Within ±1 grade = {metrics['Within1']:,} ({metrics['Within1_%']:.1f}%)",
        f"Off by ≥2 = {metrics['Off2plus']:,}",
    ]
    axLEG_ERR.text(2.0, 1.5, "\n".join(metrics_lines), ha="left", va="center", fontsize=9)

    # Title/footers
    fig.suptitle("Greater London — EPC vs RF Predictions (Building-Level)", fontsize=13, y=0.99)
    foot_left = ("Data: UK EPC Register; Building footprints: OS/Verisk/OSM (as available); "
                 "Model: Random Forest (London). Coordinates: EPSG:27700.")
    foot_right = datetime.now().strftime("Map generated %Y-%m-%d")
    fig.text(0.01, 0.01, foot_left, ha="left", va="bottom", fontsize=8, color="#444")
    fig.text(0.99, 0.01, foot_right, ha="right", va="bottom", fontsize=8, color="#444")

    # Save
    base = f"london_epc_rf_results_map_{datetime.now().strftime('%Y%m%d_%H%M')}"
    ensure_outdir(OUTDIR)
    if SAVE_PDF:
        fig.savefig(os.path.join(OUTDIR, base + ".pdf"), dpi=DPI, bbox_inches="tight")
    if SAVE_PNG:
        fig.savefig(os.path.join(OUTDIR, base + ".png"), dpi=DPI, bbox_inches="tight")
    plt.close(fig)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("[ERROR]", e)
        sys.exit(1)
