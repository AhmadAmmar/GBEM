# -*- coding: utf-8 -*-
"""
Literature Review — Compact Slide Workflow (Objective 1) — WIDTH-AUTO
- Automatically sets the figure/box width to ~ the longest text line + padding.
- One column; right gutter for connectors; slide-friendly fonts.
- Prints CWD + resolved scopus.csv path and stamps it in the footer.

Outputs:
  fig_lit_sysrev_workflow_slide_COMPACT_TIGHTWIDTH.png / .pdf
"""

import os, pandas as pd, numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from textwrap import fill

# ------------------------ CONFIG ------------------------
CSV_PATH = r"D:\OneDrive - Ulster University\PhD\Lit\Scopus\2025-07-02_scopus.csv"
TITLE    = "Literature Review Workflow - Objective 1"
SUBTITLE = ""

DPI      = 300

# Palette
C_SCOPE, C_SEARCH, C_SCREEN  = "#e8f0fe", "#eafaf1", "#fff6e5"
C_EXTRACT, C_BIB, C_SYNTH, C_OUT = "#f3e8ff", "#f1f5f9", "#fde2e4", "#e2f0d9"
C_BORDER, C_TEXT = "#93A3B8", "#0f172a"
C_META, C_GUTTER = "#475569", "#475569"

# Fonts (slide-friendly)
FS_TITLE, FS_SUB, FS_HEAD, FS_META, FS_TEXT, FS_FOOT = 22, 12, 14, 11, 11, 9.2
LINE_SPACING = 1.03

# Layout constants (inches)
TOP_IN, BOTTOM_IN  = 0.45, 0.40
LEFT_IN, RIGHT_IN  = 0.60, 0.65
HEADER_GAP_IN      = 0.10
FOOTER_GAP_IN      = 0.12
GUTTER_IN          = 0.18     # right-side connector lane
TEXT_INSET_L       = 0.08     # left inset inside a box for text start
RIGHT_PAD_INSIDE   = 0.30     # space on the right inside a box after the longest line
INTER_BOX_GAP      = 0.05
BOX_PAD_ROUND      = 0.07     # corner radius

MIN_W_IN, MAX_W_IN = 8.8, 14.0   # gentle bounds for slide width

# ----------------- PATH & LIGHT COUNTS ------------------
RESOLVED_PATH = os.path.abspath(CSV_PATH)
CWD = os.getcwd()
FOUND = os.path.exists(RESOLVED_PATH)
print(f"[Slide/WidthAuto] CWD : {CWD}")
print(f"[Slide/WidthAuto] CSV : {RESOLVED_PATH}  (found={FOUND})")

N_ID, N_AFTER_DEDUP = "n₁", "n₂"
N_TITLE_ABS_SCREENED, N_FULLTEXT_ASSESSED, N_INCLUDED = "n₃", "n₅", "n₇"

if FOUND:
    try:
        df = pd.read_csv(RESOLVED_PATH)
        df.columns = [c.lower() for c in df.columns]
        N_ID = len(df)

        if "doi" in df.columns:
            key = df["doi"].astype(str).str.strip().str.lower().replace("nan", np.nan)
        elif "title" in df.columns:
            key = df["title"].astype(str).str.strip().str.lower()
        elif "eid" in df.columns:
            key = df["eid"].astype(str).str.strip().str.lower()
        else:
            key = pd.Series(range(len(df)), name="_k")
        dfx = df.assign(_k=key).drop_duplicates(subset=["_k"])
        N_AFTER_DEDUP = len(dfx)

        N_TITLE_ABS_SCREENED = N_AFTER_DEDUP
        N_FULLTEXT_ASSESSED  = "TBD"
        N_INCLUDED           = "TBD"
    except Exception as e:
        print("[Slide/WidthAuto] CSV read error:", e)

# --------------------- content (trimmed) ----------------


BLOCKS = [
    dict(c="#e8f0fe",  t="1) Scope & Protocol",
         m="Report: Yes   Status: In progress",
         b=["Research Qs & scope; PRISMA protocol; preregistered plan."]),
    dict(c="#eafaf1",  t="2) Search Strategy & Retrieval",
         m="Report: Yes   Status: Done",
         b=[f"TITLE-only Boolean A∧B∧C; Scopus + WoS + Scholar + snowball.",
            f"A: building / urban / housing / typology",
            f"B: EPC / EUI / UBEM / energy / thermal / retrofit / HVAC",
            f"C: Sentinel / Landsat / SAR / LiDAR / LST / LCZ / GIS",
            f"Identified: {N_ID}  |  Dedup: {N_AFTER_DEDUP}."]),
    dict(c="#fff6e5",  t="3) Screening (PRISMA)",
         m="Report: Partial   Status: In progress",
         b=[f"Title/abstract: {N_TITLE_ABS_SCREENED}  |  Full-text: {N_FULLTEXT_ASSESSED}  |  Included: {N_INCLUDED}.",
            "Exclusions: out-of-scope/RS-GIS/energy, duplicate, non-English, not peer-reviewed, too old."]),
    dict(c="#f3e8ff",  t="4) Data Extraction & Coding",
         m="Report: Partial   Status: In progress",
         b=["Template (modality/target/method/scale); quality & validation."]),
    dict(c="#f1f5f9",  t="5) Bibliometrics (results, separate)",
         m="Report: No   Status: In progress",
         b=["Time trend, venues, collaboration, keyword co-occurrence."]),
    dict(c="#fde2e4",  t="6) Synthesis, Gaps & Alignment",
         m="Report: Partial   Status: In progress",
         b=["What works; limits (resolution/bias/transferability/uncertainty); gap matrix → experiments."]),
    dict(c="#e2f0d9",  t="7) Outputs & Publication Plan",
         m="Report: Yes   Status: Continuous",
         b=["PRISMA + master tables; paper (timeline-tracked); versioned repo & ethics note."]),
]

# --------------------- text measuring -------------------
def measure_line_width_in(text: str, fontsize: float, weight="normal") -> float:
    """Return rendered width (inches) of a single line for the given font settings."""
    # transient 1×1 fig for measuring using RendererAgg
    fig = plt.figure(figsize=(1, 1), dpi=DPI)
    canvas = FigureCanvas(fig)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis("off")
    t = ax.text(0, 0.5, text, fontsize=fontsize, fontweight=weight, va="center", ha="left")
    canvas.draw()
    bbox = t.get_window_extent(renderer=canvas.get_renderer())
    plt.close(fig)
    return bbox.width / DPI  # inches

# longest single line across all titles/meta/bullets
longest_in = 0.0
for blk in BLOCKS:
    longest_in = max(longest_in,
                     measure_line_width_in(blk["t"], FS_HEAD, weight="bold"),
                     measure_line_width_in(blk["m"], FS_META))
    for line in blk["b"]:
        longest_in = max(longest_in, measure_line_width_in("• " + line, FS_TEXT))

# Required content width inside the box (text start to text end)
content_w_in = TEXT_INSET_L + longest_in + RIGHT_PAD_INSIDE

# Box width and full figure width
box_w_in = content_w_in
W_IN = LEFT_IN + box_w_in + GUTTER_IN + RIGHT_IN
W_IN = max(MIN_W_IN, min(W_IN, MAX_W_IN))  # clamp gently

# For height we keep a slide-friendly value; content will fit vertically
H_IN = 7.5  # typical 16:9 height; you can tweak if you prefer shorter

def line_h(fs): return fs / 72.0

# --------------------- draw Figure ----------------------
fig = plt.figure(figsize=(W_IN, H_IN), dpi=DPI)
ax  = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W_IN); ax.set_ylim(0, H_IN); ax.axis("off")

# header
y = H_IN - TOP_IN
ax.text(W_IN/2, y, TITLE, ha="center", va="top", fontsize=FS_TITLE, weight="bold", color=C_TEXT)
y -= line_h(FS_TITLE)*1.08
ax.text(W_IN/2, y, SUBTITLE, ha="center", va="top", fontsize=FS_SUB, color=C_META)
y -= line_h(FS_SUB)*1.05 + 0.10

# geometry for boxes
x_left    = LEFT_IN
box_right = x_left + box_w_in
gutter_x  = box_right + 0.10

centers = []
for blk in BLOCKS:
    # compute box height from lines count
    title_lines  = blk["t"].count("\n") + 1
    meta_lines   = blk["m"].count("\n") + 1
    bullet_lines = len(blk["b"])
    h  = line_h(FS_HEAD) * (1.10 * title_lines)
    h += line_h(FS_META) * (1.00 * meta_lines)
    if bullet_lines:
        h += line_h(FS_TEXT) * bullet_lines
        h += line_h(FS_TEXT) * (bullet_lines - 1) * (LINE_SPACING - 1)
    h += 0.06  # tiny intrinsic padding

    y_box_bottom = y - h
    # frame
    ax.add_patch(FancyBboxPatch((x_left, y_box_bottom), box_w_in, h,
                                boxstyle=f"round,pad=0.0005,rounding_size={BOX_PAD_ROUND}",
                                linewidth=0.8, edgecolor=C_BORDER, facecolor=blk["c"]))
    # title
    cur_y = y - 0.06
    ax.text(x_left + TEXT_INSET_L, cur_y, blk["t"], fontsize=FS_HEAD, weight="bold",
            va="top", color=C_TEXT)
    cur_y -= line_h(FS_HEAD)*1.08
    # meta
    ax.text(x_left + TEXT_INSET_L, cur_y, blk["m"], fontsize=FS_META, va="top", color=C_META)
    cur_y -= line_h(FS_META)*1.02
    # bullets
    if blk["b"]:
        ax.text(x_left + TEXT_INSET_L, cur_y,
                "\n".join("• " + L for L in blk["b"]),
                fontsize=FS_TEXT, va="top", color=C_TEXT, linespacing=LINE_SPACING)

    centers.append((box_right, y_box_bottom + h/2))
    y = y_box_bottom - INTER_BOX_GAP

# connectors
for i in range(len(centers)-1):
    # short tick → vertical arrow in gutter
    ax.annotate("", xy=(gutter_x, centers[i][1]), xytext=(centers[i][0], centers[i][1]),
                arrowprops=dict(arrowstyle="-", lw=0.7, color=C_GUTTER))
    ax.annotate("", xy=(gutter_x, centers[i+1][1]), xytext=(gutter_x, centers[i][1]),
                arrowprops=dict(arrowstyle="-|>", lw=0.9, color=C_GUTTER))

# save
out_png = "fig_lit_sysrev_workflow_slide_COMPACT_TIGHTWIDTH.png"
out_pdf = "fig_lit_sysrev_workflow_slide_COMPACT_TIGHTWIDTH.pdf"
plt.savefig(out_png, bbox_inches="tight")
plt.savefig(out_pdf, bbox_inches="tight")
print("[Slide/WidthAuto] Saved:", os.path.abspath(out_png))
print("[Slide/WidthAuto] Saved:", os.path.abspath(out_pdf))
