# -*- coding: utf-8 -*-
"""
Literature Review Workflow (Objective 1) — Focus Animation
- Width auto-sizes to longest line (slide friendly).
- Generates frames that focus on one block at a time (others blurred+dimmed),
  then a final 'all blocks' frame.
- Exports frames/, an animated GIF, and MP4 (if imageio-ffmpeg available).

Outputs in CWD:
  frames/workflow_focus_000.png ... workflow_focus_008.png
  workflow_focus.gif
  workflow_focus.mp4   (if ffmpeg available)
"""

import os, math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from PIL import Image, ImageFilter, ImageDraw

# Optional MP4 (graceful fallback if not installed)
_try_mp4 = True
try:
    import imageio.v2 as imageio
    _HAVE_IMAGEIO = True
except Exception:
    _HAVE_IMAGEIO = False
    _try_mp4 = False

# ---------------------------- CONFIG ----------------------------
CSV_PATH = r"D:\OneDrive - Ulster University\PhD\Lit\Scopus\2025-07-02_scopus.csv"     # used only for counts if available
TITLE    = "Literature Review Workflow - Objective 1"
SUBTITLE = ""               # keep empty for slide

DPI      = 300

# Figures (and the intermediate frames/ folder) always go here, independent
# of wherever the source CSV lives
OUT_DIR = r"D:\OneDrive - Ulster University\PhD\Review_Figures"
os.makedirs(OUT_DIR, exist_ok=True)
H_IN     = 7.5              # slide-ish height; width is auto (8.8–14 in clamp)

# Palette
C_SCOPE, C_SEARCH, C_SCREEN  = "#e8f0fe", "#eafaf1", "#fff6e5"
C_EXTRACT, C_BIB, C_SYNTH, C_OUT = "#f3e8ff", "#f1f5f9", "#fde2e4", "#e2f0d9"
C_BORDER, C_TEXT = "#93A3B8", "#0f172a"
C_META, C_GUTTER = "#475569", "#475569"

# Fonts (slide-friendly)
FS_TITLE, FS_SUB, FS_HEAD, FS_META, FS_TEXT = 22, 12, 14, 11, 11
LINE_SPACING = 1.03

# Layout (inches)
TOP_IN, BOTTOM_IN  = 0.45, 0.40
LEFT_IN, RIGHT_IN  = 0.60, 0.65
HEADER_GAP_IN      = 0.10
GUTTER_IN          = 0.18
TEXT_INSET_L       = 0.08
RIGHT_PAD_INSIDE   = 0.30
INTER_BOX_GAP      = 0.05
BOX_PAD_ROUND      = 0.07
MIN_W_IN, MAX_W_IN = 8.8, 14.0

# Animation styling
BLUR_RADIUS   = 4        # Gaussian blur for non-focused area
DIM_ALPHA     = 80       # 0–255; how much to darken non-focused area
HIGHLIGHT_W   = 6        # px; highlight stroke around the focused block
HIGHLIGHT_COL = (30, 64, 175, 220)  # deep blue (RGBA) for focus ring
FRAME_MS      = 900      # GIF frame duration per step (ms)
EASING_PAD_PX = 4        # extra crop padding (px) to hide blur seams

# ---------------------- Helper: text widths ----------------------
def _measure_line_width_in(text, fontsize, weight="normal"):
    fig = plt.figure(figsize=(1, 1), dpi=DPI)
    canvas = FigureCanvas(fig)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis("off")
    t = ax.text(0, 0.5, text, fontsize=fontsize, fontweight=weight,
                va="center", ha="left")
    canvas.draw()
    bbox = t.get_window_extent(renderer=canvas.get_renderer())
    plt.close(fig)
    return bbox.width / DPI

def _line_h_in(fs): return fs/72.0

# ---------------------- Data & counts (light) --------------------
RESOLVED_PATH = os.path.abspath(CSV_PATH)
FOUND = os.path.exists(RESOLVED_PATH)
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
    except Exception:
        pass

# ------------------------- Blocks (trim) -------------------------
BLOCKS = [
    dict(c=C_SCOPE,  t="1) Scope & Protocol",
         m="Report: Yes   Status: In progress",
         b=["Research Qs & scope; PRISMA protocol; preregistered plan."]),
    dict(c=C_SEARCH, t="2) Search Strategy & Retrieval",
         m="Report: Yes   Status: Done",
         b=[f"TITLE-only Boolean A∧B∧C; Scopus + WoS + Scholar + snowball.",
            f"A: building / urban / housing / typology",
            f"B: EPC / EUI / UBEM / energy / thermal / retrofit / HVAC",
            f"C: Sentinel / Landsat / SAR / LiDAR / LST / LCZ / GIS",
            f"Identified: {N_ID}  |  Dedup: {N_AFTER_DEDUP}."]),
    dict(c=C_SCREEN, t="3) Screening (PRISMA)",
         m="Report: Partial   Status: In progress",
         b=[f"Title/abstract: {N_TITLE_ABS_SCREENED}  |  Full-text: {N_FULLTEXT_ASSESSED}  |  Included: {N_INCLUDED}.",
            "Exclusions: out-of-scope/RS-GIS/energy, duplicate, non-English, not peer-reviewed, too old."]),
    dict(c=C_EXTRACT, t="4) Data Extraction & Coding",
         m="Report: Partial   Status: In progress",
         b=["Template (modality/target/method/scale); quality & validation."]),
    dict(c=C_BIB,    t="5) Bibliometrics (results, separate)",
         m="Report: No   Status: In progress",
         b=["Time trend, venues, collaboration, keyword co-occurrence."]),
    dict(c=C_SYNTH,  t="6) Synthesis, Gaps & Alignment",
         m="Report: Partial   Status: In progress",
         b=["What works; limits (resolution/bias/transferability/uncertainty); gap matrix → experiments."]),
    dict(c=C_OUT,    t="7) Outputs & Publication Plan",
         m="Report: Yes   Status: Continuous",
         b=["PRISMA + master tables; paper (timeline-tracked); versioned repo & ethics note."]),
]

# --------------------- Width auto & drawing ----------------------
def compute_layout_width():
    longest = 0.0
    for blk in BLOCKS:
        longest = max(longest,
                      _measure_line_width_in(blk["t"], FS_HEAD, weight="bold"),
                      _measure_line_width_in(blk["m"], FS_META))
        for L in blk["b"]:
            longest = max(longest, _measure_line_width_in("• " + L, FS_TEXT))
    content_w_in = TEXT_INSET_L + longest + RIGHT_PAD_INSIDE
    W = LEFT_IN + content_w_in + GUTTER_IN + RIGHT_IN
    return max(MIN_W_IN, min(W, MAX_W_IN)), content_w_in

def draw_base(save_path_png=None, save_path_pdf=None):
    """Draws the whole figure, returns (fig, ax, bboxes_in, px_size)."""
    W_IN, box_w_in = compute_layout_width()
    fig = plt.figure(figsize=(W_IN, H_IN), dpi=DPI)
    ax  = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W_IN); ax.set_ylim(0, H_IN); ax.axis("off")

    # header
    y = H_IN - TOP_IN
    ax.text(W_IN/2, y, TITLE, ha="center", va="top", fontsize=FS_TITLE, weight="bold", color=C_TEXT)
    y -= _line_h_in(FS_TITLE)*1.08
    if SUBTITLE:
        ax.text(W_IN/2, y, SUBTITLE, ha="center", va="top", fontsize=FS_SUB, color=C_META)
        y -= _line_h_in(FS_SUB)*1.05
    y -= HEADER_GAP_IN

    x_left = LEFT_IN
    box_right = x_left + box_w_in
    gutter_x = box_right + 0.10

    bboxes_in = []  # list of (x, y_bottom, w, h) in inches
    centers = []

    for blk in BLOCKS:
        title_lines  = blk["t"].count("\n") + 1
        meta_lines   = blk["m"].count("\n") + 1
        bullet_lines = len(blk["b"])
        h  = _line_h_in(FS_HEAD) * (1.10 * title_lines)
        h += _line_h_in(FS_META) * (1.00 * meta_lines)
        if bullet_lines:
            h += _line_h_in(FS_TEXT) * bullet_lines
            h += _line_h_in(FS_TEXT) * (bullet_lines - 1) * (LINE_SPACING - 1)
        h += 0.06

        yb = y - h
        ax.add_patch(FancyBboxPatch((x_left, yb), box_w_in, h,
                                    boxstyle=f"round,pad=0.0005,rounding_size={BOX_PAD_ROUND}",
                                    linewidth=0.8, edgecolor=C_BORDER, facecolor=blk["c"]))
        cur_y = y - 0.06
        ax.text(x_left + TEXT_INSET_L, cur_y, blk["t"], fontsize=FS_HEAD, weight="bold", va="top", color=C_TEXT)
        cur_y -= _line_h_in(FS_HEAD)*1.08
        ax.text(x_left + TEXT_INSET_L, cur_y, blk["m"], fontsize=FS_META, va="top", color=C_META)
        cur_y -= _line_h_in(FS_META)*1.02
        if blk["b"]:
            ax.text(x_left + TEXT_INSET_L, cur_y, "\n".join("• "+L for L in blk["b"]),
                    fontsize=FS_TEXT, va="top", color=C_TEXT, linespacing=LINE_SPACING)

        centers.append((box_right, yb + h/2))
        bboxes_in.append((x_left, yb, box_w_in, h))
        y = yb - INTER_BOX_GAP

    # connectors in gutter
    for i in range(len(centers)-1):
        ax.annotate("", xy=(gutter_x, centers[i][1]), xytext=(centers[i][0], centers[i][1]),
                    arrowprops=dict(arrowstyle="-", lw=0.7, color=C_GUTTER))
        ax.annotate("", xy=(gutter_x, centers[i+1][1]), xytext=(gutter_x, centers[i][1]),
                    arrowprops=dict(arrowstyle="-|>", lw=0.9, color=C_GUTTER))

    if save_path_png:
        fig.savefig(save_path_png, dpi=DPI, bbox_inches="tight")
    if save_path_pdf:
        fig.savefig(save_path_pdf, dpi=DPI, bbox_inches="tight")

    # Return pixel size of saved PNG (for consistent compositing)
    fig.canvas.draw()
    width_px  = int(round(fig.bbox.width))
    height_px = int(round(fig.bbox.height))
    return fig, ax, bboxes_in, (width_px, height_px)

# ------------------------- Animation build -----------------------
def inches_to_px(bbox_in, fig_px_size, W_IN, H_IN):
    """Convert (x, yb, w, h) inches to pixel box on the exported image."""
    x_in, yb_in, w_in, h_in = bbox_in
    # bbox_inches='tight' can shift origin; safest is to compute scale from figure size
    # Using full figure inches times DPI:
    scale_x = DPI
    scale_y = DPI
    # matplotlib's origin is bottom-left for y; our yb_in is also from bottom.
    x_px = int(round(x_in * scale_x))
    y_px = int(round(yb_in * scale_y))
    w_px = int(round(w_in * scale_x))
    h_px = int(round(h_in * scale_y))
    return (x_px, y_px, w_px, h_px)

def build_animation():
    frames_dir = os.path.join(OUT_DIR, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    base_png = os.path.join(frames_dir, "_base_full.png")
    base_pdf = os.path.join(frames_dir, "_base_full.pdf")
    fig, ax, bboxes_in, fig_px = draw_base(save_path_png=base_png, save_path_pdf=base_pdf)
    plt.close(fig)

    # open base and prepare blurred/dim versions per step
    base = Image.open(base_png).convert("RGBA")
    Wpx, Hpx = base.size

    frames = []
    for step, bbox_in in enumerate(bboxes_in, start=1):
        # Blur + dim full image
        blurred = base.filter(ImageFilter.GaussianBlur(radius=BLUR_RADIUS))
        dim = Image.new("RGBA", base.size, (0, 0, 0, DIM_ALPHA))
        blurred = Image.alpha_composite(blurred, dim)

        # Paste sharp crop of focused block
        x_px, y_px, w_px, h_px = inches_to_px(bbox_in, fig_px, fig.get_figwidth(), fig.get_figheight())
        # convert from bottom-left origin (inches) to PIL origin (top-left)
        y_px_from_top = Hpx - (y_px + h_px)

        crop_box = (max(0, x_px - EASING_PAD_PX),
                    max(0, y_px_from_top - EASING_PAD_PX),
                    min(Wpx, x_px + w_px + EASING_PAD_PX),
                    min(Hpx, y_px_from_top + h_px + EASING_PAD_PX))
        sharp_crop = base.crop(crop_box)
        frame = blurred.copy()
        frame.paste(sharp_crop, crop_box)

        # Focus ring
        draw = ImageDraw.Draw(frame)
        rr = 14  # rounded corner radius in px
        ring_box = (x_px, y_px_from_top, x_px + w_px, y_px_from_top + h_px)
        draw.rounded_rectangle(ring_box, radius=rr, outline=HIGHLIGHT_COL, width=HIGHLIGHT_W)

        out_path = os.path.join(frames_dir, f"workflow_focus_{step:03d}.png")
        frame.save(out_path)
        frames.append(frame)

    # Final 'all clear' frame (no blur)
    all_clear = base.copy()
    out_path = os.path.join(frames_dir, f"workflow_focus_{len(bboxes_in)+1:03d}.png")
    all_clear.save(out_path)
    frames.append(all_clear)

    # GIF
    gif_path = os.path.join(OUT_DIR, "workflow_focus.gif")
    frames[0].save(gif_path, save_all=True, append_images=frames[1:],
                   duration=FRAME_MS, loop=0, disposal=2)
    print("Wrote GIF:", os.path.abspath(gif_path))

    # MP4 (optional)
    if _try_mp4 and _HAVE_IMAGEIO:
        mp4_path = os.path.join(OUT_DIR, "workflow_focus.mp4")
        imageio.mimsave(mp4_path, [np.array(f.convert("RGB")) for f in frames], fps=max(1, int(1000/FRAME_MS)))
        print("Wrote MP4:", os.path.abspath(mp4_path))
    else:
        print("MP4 skipped (imageio-ffmpeg not available).")

if __name__ == "__main__":
    print("[Animate] Building frames/GIF/MP4 …")
    build_animation()
    print("[Animate] Done. Insert workflow_focus.gif or workflow_focus.mp4 into your slide.")
