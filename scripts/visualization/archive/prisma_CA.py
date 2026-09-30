# -*- coding: utf-8 -*-
"""
One-Column Literature/Systematic Review — Ultra-Compact (Objective 1)
- Boxes are auto-sized from text (tiny vertical padding)
- Right-gutter connectors (no arrows over text)
- Footer placed directly below last box; figure height shrinks to content
- Prints working directory + resolved Scopus CSV path; stamps it in footer
Outputs:
  - fig_lit_sysrev_workflow_onecol_TIGHT.pdf/.png  (auto height, no extra space)
  - fig_lit_sysrev_workflow_onecol_A4.pdf/.png     (optional A4 export if KEEP_A4=True)
"""

import os, pandas as pd, numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from textwrap import fill

# ───────────────────────── CONFIG ─────────────────────────
CSV_PATH = r"D:\OneDrive - Ulster University\PhD\Lit\Scopus\2025-07-02_scopus.csv"     # path to your Scopus CSV (TITLE-only queries)
KEEP_A4  = False            # set True to also export an A4 page with same layout

# Figures always go here, independent of wherever the source CSV lives
OUT_DIR = r"D:\OneDrive - Ulster University\PhD\Review_Figures"
os.makedirs(OUT_DIR, exist_ok=True)

TITLE    = "Literature & Systematic Review — Compact Workflow (Objective 1)"
SUBTITLE = "PRISMA-guided • TITLE-only Boolean blocks • bibliometrics • synthesis • publication plan"

# Colors (soft, print-friendly)
C_SCOPE, C_SEARCH, C_SCREEN  = "#e8f0fe", "#eafaf1", "#fff6e5"
C_EXTRACT, C_BIB, C_SYNTH, C_OUT = "#f3e8ff", "#f1f5f9", "#fde2e4", "#e2f0d9"
C_BORDER, C_TEXT = "#93A3B8", "#111827"
C_META, C_GUTTER = "#4B5563", "#475569"

# Fonts (tight)
FS_TITLE, FS_SUB, FS_HEAD, FS_META, FS_TEXT, FS_TINY = 14.5, 9.0, 10.2, 8.0, 7.9, 7.0
LINE_SPACING = 1.02  # dense lines

# Page width (inches); height will be computed from content (TIGHT export)
PAGE_W_IN = 8.27

# Layout margins (inches)
LEFT_IN   = 0.42
RIGHT_IN  = 0.45
TOP_IN    = 0.35     # to title
HEADER_GAP_IN = 0.10 # between title/subtitle and first box
FOOTER_GAP_IN = 0.12 # between last box and footer
BOTTOM_IN = 0.25     # bottom margin below footer

GUTTER_IN = 0.16     # right gutter where the vertical arrow runs

# ───────────── PATH / COUNTS ─────────────
RESOLVED_PATH = os.path.abspath(CSV_PATH)
CWD = os.getcwd()
FOUND = os.path.exists(RESOLVED_PATH)
print(f"[Lit/SysRev] Working directory : {CWD}")
print(f"[Lit/SysRev] CSV target path  : {RESOLVED_PATH}")
print(f"[Lit/SysRev] CSV found?       : {FOUND}")
PATH_NOTE = f"{RESOLVED_PATH}" + ("" if FOUND else " (not found)")

N_ID, N_AFTER_DEDUP = "n₁", "n₂"
N_TITLE_ABS_SCREENED, N_TITLE_ABS_EXCLUDED = "n₃", "n₄"
N_FULLTEXT_ASSESSED, N_FULLTEXT_EXCLUDED, N_INCLUDED = "n₅", "n₆", "n₇"

if FOUND:
    try:
        df = pd.read_csv(RESOLVED_PATH)
        df.columns = [c.lower() for c in df.columns]
        N_ID = len(df)
        doi_col   = "doi"   if "doi"   in df.columns else None
        title_col = "title" if "title" in df.columns else None
        eid_col   = "eid"   if "eid"   in df.columns else None
        if doi_col:
            key = df[doi_col].astype(str).str.strip().str.lower().replace("nan", np.nan)
        elif title_col:
            key = df[title_col].astype(str).str.strip().str.lower()
        elif eid_col:
            key = df[eid_col].astype(str).str.strip().str.lower()
        else:
            key = pd.Series(range(len(df)), name="_k")
        dfx = df.assign(_k=key).drop_duplicates(subset=["_k"])
        N_AFTER_DEDUP = len(dfx)
        # screening counts are not computed by this script (see review/s01_screen.py)
        N_TITLE_ABS_SCREENED = N_AFTER_DEDUP
        N_TITLE_ABS_EXCLUDED = "n/a"
        N_FULLTEXT_ASSESSED  = "n/a"
        N_FULLTEXT_EXCLUDED  = "n/a"
        N_INCLUDED           = "n/a"
    except Exception as e:
        print(f"[Lit/SysRev] CSV read error: {e}")

# ───────────── Helpers (size in inches) ─────────────
def line_h_in(fs_pt):  # text line height in inches
    return (fs_pt / 72.0)

def block_h_in(title_lines=1, meta_lines=1, bullet_lines=3,
               fs_head=FS_HEAD, fs_meta=FS_META, fs_text=FS_TEXT,
               line_spacing=LINE_SPACING, pad_top_in=0.03, pad_bottom_in=0.03):
    h  = line_h_in(fs_head) * (1.05 * title_lines)
    h += line_h_in(fs_meta) * (1.00 * meta_lines)
    # bullets (approximate; assumes no wraps — keep bullets concise)
    h += line_h_in(fs_text) * (bullet_lines + (bullet_lines-1)*(line_spacing-1))
    h += pad_top_in + pad_bottom_in
    return h

def add_block(ax, x_in, y_top_in, w_in, fc, title, meta, bullets):
    """
    Place a box using inch coordinates. Returns:
    - new y_top (below the box + small gap),
    - center_y for connectors.
    """
    title_lines  = title.count("\n")+1
    meta_lines   = meta.count("\n")+1 if meta else 0
    bullet_lines = len(bullets) if bullets else 0
    h_in = block_h_in(title_lines, meta_lines, bullet_lines)

    y_in = y_top_in - h_in
    # draw box
    p = FancyBboxPatch((x_in, y_in), w_in, h_in,
                       boxstyle=f"round,pad=0.0005,rounding_size=0.07",
                       transform=ax.transData,  # data coords (inches)
                       linewidth=0.55, edgecolor=C_BORDER, facecolor=fc)
    ax.add_patch(p)

    # content positions
    cur_y = y_in + h_in - 0.06  # tiny inset from top
    ax.text(x_in + 0.06, cur_y, title, fontsize=FS_HEAD, weight="bold",
            va="top", color=C_TEXT, transform=ax.transData)
    cur_y -= line_h_in(FS_HEAD) * 1.08

    if meta:
        ax.text(x_in + 0.06, cur_y, meta, fontsize=FS_META, va="top",
                color=C_META, transform=ax.transData)
        cur_y -= line_h_in(FS_META) * 1.05

    # bullets
    if bullets:
        ax.text(x_in + 0.06, cur_y, "\n".join("• "+b for b in bullets),
                fontsize=FS_TEXT, va="top", color=C_TEXT,
                linespacing=LINE_SPACING, transform=ax.transData)

    center_y_in = y_in + h_in/2.0
    # inter-block micro-gap
    next_y_top_in = y_in - 0.06
    return next_y_top_in, center_y_in

def connect_gutter(ax, box_right_in, y_from_in, y_to_in, gutter_x_in):
    # small horizontal tick, then vertical arrow in the gutter
    ax.annotate("", xy=(gutter_x_in, y_from_in), xytext=(box_right_in, y_from_in),
                arrowprops=dict(arrowstyle="-", lw=0.7, color=C_GUTTER),
                xycoords=ax.transData, textcoords=ax.transData)
    ax.annotate("", xy=(gutter_x_in, y_to_in), xytext=(gutter_x_in, y_from_in),
                arrowprops=dict(arrowstyle="-|>", lw=0.9, color=C_GUTTER),
                xycoords=ax.transData, textcoords=ax.transData)

# ───────────── Content (concise bullets) ─────────────
sample_A = "building • urban • residential • dwelling • housing-stock • typology"
sample_B = "EPC/EUI/UBEM • energy/thermal/comfort • retrofit • HVAC"
sample_C = "Sentinel/Landsat/SAR/LiDAR • LST • LCZ • thermography • GIS"

BLOCKS = [
    dict(
        fc=C_SCOPE,
        title="1) Scope & Protocol",
        meta="Report: Yes    Status: In progress",
        bullets=[
            "Research Qs & scope (urban buildings + energy performance via RS/GIS).",
            "PRISMA protocol: years, language, study types, inclusion/exclusion.",
            "Register plan; roles; reproducibility; privacy-by-design."
        ]
    ),
    dict(
        fc=C_SEARCH,
        title="2) Search Strategy & Retrieval",
        meta="Report: Yes    Status: Done",
        bullets=[
            "Databases: Scopus (RIS/CSV), Web of Science; curated Scholar; snowballing.",
            "TITLE-only Boolean: TITLE:(A) AND TITLE:(B) AND TITLE:(C).",
            f"A → {sample_A}",
            f"B → {sample_B}",
            f"C → {sample_C}",
            f"Records identified: {N_ID} ; after dedup: {N_AFTER_DEDUP}."
        ]
    ),
    dict(
        fc=C_SCREEN,
        title="3) Screening (PRISMA)",
        meta="Report: Partial    Status: In progress",
        bullets=[
            f"Title/abstract screening: screened {N_TITLE_ABS_SCREENED}; excluded {N_TITLE_ABS_EXCLUDED}.",
            f"Full-text eligibility: assessed {N_FULLTEXT_ASSESSED}; excluded {N_FULLTEXT_EXCLUDED}.",
            f"Included for synthesis: {N_INCLUDED}.",
            "Exclusions extend scope/RS-GIS/energy fit & duplicates to: non-English; not peer-reviewed;",
            "conference/short/abstract-only; too old; editorial/review; preprint duplicate; no full text; not empirical."
        ]
    ),
    dict(
        fc=C_EXTRACT,
        title="4) Data Extraction & Coding",
        meta="Report: Partial    Status: In progress",
        bullets=[
            "Template: modality; target (EPC/EUI/etc.); method (RF/XGB/CNN/GNN); scale/city; sources.",
            "Quality: sampling; leakage risk; validation; uncertainty; policy relevance.",
            "Repro notebooks: parse RIS/CSV; harmonise fields; export master tables."
        ]
    ),
    dict(
        fc=C_BIB,
        title="5) Bibliometrics / Scientometrics (results, separate)",
        meta="Report: No    Status: In progress",
        bullets=[
            "Time trend; top venues/institutions; collaboration networks.",
            "Keyword co-occurrence & thematic clusters (e.g., SAR/LST/street-view).",
            "Kept as *results* in a separate figure — not on the workflow page."
        ]
    ),
    dict(
        fc=C_SYNTH,
        title="6) Thematic Synthesis, Gaps & Alignment",
        meta="Report: Partial    Status: In progress",
        bullets=[
            "What works at city scale? Robust modalities/features/methods.",
            "Limits: resolution, bias, transferability, calibration/uncertainty, governance.",
            "Gap matrix → informs PhD objectives & experiments."
        ]
    ),
    dict(
        fc=C_OUT,
        title="7) Outputs, Repro & Publication Plan",
        meta="Report: Yes    Status: Continuous",
        bullets=[
            "Artifacts: PRISMA diagram; master tables; bibliometric figures; narrative synthesis.",
            "Systematic/scoping review paper (timeline-tracked); slides for confirmation.",
            "Versioned code/data; preregistered protocol; living repo; ethics note."
        ]
    )
]

# ───────────── Compute total height (inches) ─────────────
header_h_in = line_h_in(FS_TITLE)*1.15 + line_h_in(FS_SUB)*1.10
blocks_h_in = 0.0
for b in BLOCKS:
    title_lines  = b["title"].count("\n")+1
    meta_lines   = b["meta"].count("\n")+1 if b["meta"] else 0
    bullet_lines = len(b["bullets"])
    blocks_h_in += block_h_in(title_lines, meta_lines, bullet_lines)
# tiny inter-block gaps (0.06 in each)
blocks_h_in += 0.06 * (len(BLOCKS)-1)

footer_text = f"Counts source (if found): {PATH_NOTE}. Workflow shows process only; results (keyword clouds, yearly trends, co-occurrence) are separate figures. “Report” shows what’s included now for the confirmation; others proceed toward the review paper submission."
footer_h_in = line_h_in(FS_TINY) * 1.15

TOTAL_H_IN = TOP_IN + header_h_in + HEADER_GAP_IN + blocks_h_in + FOOTER_GAP_IN + footer_h_in + BOTTOM_IN

# Column geometry (inches)
x_left_in   = LEFT_IN
box_w_in    = PAGE_W_IN - LEFT_IN - RIGHT_IN - GUTTER_IN
box_right_in= x_left_in + box_w_in
gutter_x_in = box_right_in + 0.10  # small horizontal tick length

# ───────────── Draw (TIGHT canvas in inches) ─────────────
def draw_canvas(height_in, out_pdf, out_png):
    fig = plt.figure(figsize=(PAGE_W_IN, height_in), dpi=300)
    ax  = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, PAGE_W_IN); ax.set_ylim(0, height_in); ax.axis("off")

    # header
    y_cursor = height_in - TOP_IN
    ax.text(PAGE_W_IN/2, y_cursor, TITLE, ha="center", va="top",
            fontsize=FS_TITLE, weight="bold", color=C_TEXT, transform=ax.transData)
    y_cursor -= line_h_in(FS_TITLE)*1.15
    ax.text(PAGE_W_IN/2, y_cursor, SUBTITLE, ha="center", va="top",
            fontsize=FS_SUB, color=C_META, transform=ax.transData)
    y_cursor -= line_h_in(FS_SUB)*1.10 + HEADER_GAP_IN

    centers = []
    for b in BLOCKS:
        y_cursor, c_y = add_block(ax, x_left_in, y_cursor, box_w_in,
                                  b["fc"], b["title"], b["meta"], b["bullets"])
        centers.append((box_right_in, c_y))

    # connectors
    for i in range(len(centers)-1):
        connect_gutter(ax, centers[i][0], centers[i][1], centers[i+1][1], gutter_x_in)

    # footer snug under last box
    y_footer = y_cursor - FOOTER_GAP_IN
    ax.text(PAGE_W_IN/2, y_footer, fill(footer_text, 140),
            ha="center", va="top", fontsize=FS_TINY, color=C_META, transform=ax.transData)

    fig.savefig(out_pdf, bbox_inches="tight")
    fig.savefig(out_png, bbox_inches="tight")
    print(f"[Lit/SysRev] Saved: {os.path.abspath(out_pdf)} and {os.path.abspath(out_png)}")

# Tight (auto height, no empty space)
draw_canvas(TOTAL_H_IN,
            os.path.join(OUT_DIR, "fig_lit_sysrev_workflow_onecol_TIGHT.pdf"),
            os.path.join(OUT_DIR, "fig_lit_sysrev_workflow_onecol_TIGHT.png"))

# Optional A4 export (same layout, just sized to A4 height)
if KEEP_A4:
    draw_canvas(11.69, os.path.join(OUT_DIR, "fig_lit_sysrev_workflow_onecol_A4.pdf"),
                os.path.join(OUT_DIR, "fig_lit_sysrev_workflow_onecol_A4.png"))
