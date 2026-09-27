# -*- coding: utf-8 -*-
"""
Confusion Matrix (stand-alone, auto-inputs, 2× cell size, bigger numbers, no padding)

What it does (no CLI args required):
1) Tries to load the confusion_matrix_counts.csv from:
     D:/OneDrive - Ulster University/PhD/Maps/confirm_report/london_epc_rf_maps/latest/
   If missing, it looks in the most recent run_* folder.
   If still missing, it computes the CM from the newest cached cache/fp_*/panel.parquet.

2) Renders a clean confusion matrix with ~2× larger cells (0.60 in per cell)
   and 16-pt cell numbers (white stroke for readability).

3) Saves to the same 'latest' folder:
   - confusion_matrix_large_counts.csv
   - confusion_matrix_large.pdf  (bbox_inches="tight", pad_inches=0)
   - confusion_matrix_large.png  (bbox_inches="tight", pad_inches=0)
"""

from __future__ import annotations
import os, sys, glob, json
from datetime import datetime
from typing import Optional, List

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.colors import ListedColormap

# ───────────────────────── Config ─────────────────────────
BASE_DEFAULT     = r"D:/OneDrive - Ulster University/PhD"
OUTROOT_DEFAULT  = os.path.join(BASE_DEFAULT, "Maps", "confirm_report", "london_epc_rf_maps")

# Appearance
CELL_IN     = 0.60     # per-cell size in inches  (~2×)
NUMBERS_FS  = 14       # cell value font size (doubled)
AXIS_FS     = 14       # tick/axis fonts
TITLE_FS    = 20
PNG_DPI     = 600

# EPC order and colors (distance-based background)
EPC_ORDER   = list("ABCDEFG")
EPC_TO_IDX  = {c:i for i,c in enumerate(EPC_ORDER)}
DIST_CMAP   = ListedColormap(["#bfe7bf", "#ffd89a", "#f6b0b0"])  # correct / off-by-1 / off-by-2+

# ───────────────────────── Helpers ─────────────────────────
def log(msg: str): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def safe_makedirs(p: str): os.makedirs(p, exist_ok=True)

def find_latest_cm_csv(outroot: str) -> Optional[str]:
    p = os.path.join(outroot, "latest", "confusion_matrix_counts.csv")
    return p if os.path.exists(p) else None

def find_recent_run_cm(outroot: str) -> Optional[str]:
    run_dirs = sorted(glob.glob(os.path.join(outroot, "run_*")), key=os.path.getmtime, reverse=True)
    for rd in run_dirs:
        cand = os.path.join(rd, "confusion_matrix_counts.csv")
        if os.path.exists(cand): return cand
    return None

def find_newest_panel_parquet(outroot: str) -> Optional[str]:
    panels = glob.glob(os.path.join(outroot, "cache", "fp_*", "panel.parquet"))
    if not panels: return None
    return max(panels, key=os.path.getmtime)

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

def compute_cm_from_panel(panel_path: str) -> pd.DataFrame:
    log(f"Loading panel: {panel_path}")
    bld = gpd.read_parquet(panel_path)

    ACTUAL_RATING_CANDS = ["CURRENT_ENERGY_RATING","EPC_RATING","epc_actual","label_true","actual_label","EPC_ACTUAL"]
    PRED_RATING_CANDS   = ["predicted_rating","PRED_EPC","pred_epc","epc_pred","label_pred","predicted_label","PRED_EPC_RATING","EPC_PRED"]

    col_true = find_col(bld.columns.tolist(), ACTUAL_RATING_CANDS)
    col_pred = find_col(bld.columns.tolist(), PRED_RATING_CANDS)
    if not col_true or not col_pred:
        raise RuntimeError("Could not find actual/predicted EPC columns in panel.")

    bld[col_true] = bld[col_true].map(normalize_epc)
    bld[col_pred] = bld[col_pred].map(normalize_epc)
    eval_mask = bld[col_true].notna() & bld[col_pred].notna()
    df = bld.loc[eval_mask, [col_true, col_pred]].copy()

    cm = pd.crosstab(df[col_true], df[col_pred], dropna=False).reindex(index=EPC_ORDER, columns=EPC_ORDER, fill_value=0)
    return cm.astype(int)

def load_confusion_matrix(outroot: str) -> pd.DataFrame:
    p = find_latest_cm_csv(outroot)
    if p:
        log(f"Using CM from latest/: {p}")
        cm = pd.read_csv(p, index_col=0)
        return cm.reindex(index=EPC_ORDER, columns=EPC_ORDER, fill_value=0).astype(int)

    p = find_recent_run_cm(outroot)
    if p:
        log(f"Using CM from most-recent run: {p}")
        cm = pd.read_csv(p, index_col=0)
        return cm.reindex(index=EPC_ORDER, columns=EPC_ORDER, fill_value=0).astype(int)

    panel = find_newest_panel_parquet(outroot)
    if panel:
        log("No CM CSV found; computing from newest panel.parquet.")
        return compute_cm_from_panel(panel)

    raise FileNotFoundError("Could not find a confusion matrix CSV or a cached panel.parquet to compute it.")

def draw_confusion_matrix_large(cm: pd.DataFrame,
                                cell_in: float = CELL_IN,
                                numbers_fs: int = NUMBERS_FS,
                                axis_fs: int = AXIS_FS,
                                title_fs: int = TITLE_FS):
    """Return (fig, ax) with fixed per-cell physical size; title inside axes (no outer padding)."""
    n = len(EPC_ORDER)
    grid_w = n * cell_in
    grid_h = n * cell_in

    # Margins (inches) reserved INSIDE the figure for ticks/labels/title.
    # Keep these modest; outer padding will be stripped at save via pad_inches=0.
    LM, RM, BM, TM = 0.9, 0.5, 0.9, 0.6
    fig_w = LM + grid_w + RM
    fig_h = BM + grid_h + TM

    fig = plt.figure(figsize=(fig_w, fig_h), dpi=PNG_DPI)
    # Axes coordinates so the grid area is exactly grid_w x grid_h:
    ax_left = LM / fig_w
    ax_bottom = BM / fig_h
    ax_width = grid_w / fig_w
    ax_height = grid_h / fig_h
    ax = fig.add_axes([ax_left, ax_bottom, ax_width, ax_height])

    # Distance-based background
    nrange = np.arange(n)
    dist = np.minimum(np.abs(nrange[:, None] - nrange[None, :]), 2)
    ax.imshow(dist, cmap=DIST_CMAP, vmin=0, vmax=2, alpha=0.55, zorder=0)

    # Grid lines
    ax.set_xticks(np.arange(-.5, n, 1), minor=True)
    ax.set_yticks(np.arange(-.5, n, 1), minor=True)
    ax.grid(which="minor", color="#333333", linewidth=0.9)

    # Ticks/labels
    ax.set_xticks(range(n)); ax.set_yticks(range(n))
    ax.set_xticklabels(EPC_ORDER, fontsize=axis_fs)
    ax.set_yticklabels(EPC_ORDER, fontsize=axis_fs)
    ax.set_xlabel("Predicted", fontsize=axis_fs)
    ax.set_ylabel("Actual", fontsize=axis_fs)

    # Counts
    for i in range(n):
        for j in range(n):
            v = int(cm.iloc[i, j])
            ax.text(j, i, f"{v}", ha="center", va="center",
                    fontsize=numbers_fs, color="black", zorder=2,
                    path_effects=[pe.withStroke(linewidth=2.8, foreground="white")])

    # Tight to the grid
    ax.set_xlim(-0.5, n - 0.5); ax.set_ylim(n - 0.5, -0.5)

    # Title inside the top padding area (still part of bbox, no extra frame)
    fig.text(ax_left + ax_width/2, ax_bottom + ax_height + (TM-0.2)/fig_h,
             "Confusion Matrix (counts)", ha="center", va="bottom", fontsize=title_fs)

    return fig, ax

# ───────────────────────── Main ─────────────────────────
def main():
    outroot = OUTROOT_DEFAULT
    latest_dir = os.path.join(outroot, "latest")
    safe_makedirs(latest_dir)

    # Load or compute CM
    cm = load_confusion_matrix(outroot)
    cm = cm.reindex(index=EPC_ORDER, columns=EPC_ORDER, fill_value=0).astype(int)

    # Draw
    fig, ax = draw_confusion_matrix_large(cm, CELL_IN, NUMBERS_FS, AXIS_FS, TITLE_FS)

    # Save (NO PADDING)
    base = os.path.join(latest_dir, "confusion_matrix_large")
    csv_path = f"{base}_counts.csv"
    pdf_path = f"{base}.pdf"
    png_path = f"{base}.png"

    cm.to_csv(csv_path, index=True)
    fig.savefig(pdf_path, dpi=PNG_DPI, bbox_inches="tight", pad_inches=0)
    fig.savefig(png_path, dpi=PNG_DPI, bbox_inches="tight", pad_inches=0)
    plt.close(fig)

    log(f"SAVED CSV: {csv_path}")
    log(f"SAVED PDF: {pdf_path}")
    log(f"SAVED PNG: {png_path}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("[ERROR]", e)
        sys.exit(1)
