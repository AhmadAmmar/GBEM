# radiant_keywords_clusters.py  (compact, gapless grid)
# -------------------------------------------------------------------
# 2×2 panels (A/B/C/D) of top keywords per cluster — ultra-compact.
# - Auto-detects scopus.csv in: /mnt/data/, or current folder
# - Cleans near-duplicates; forces acronyms to ALL-CAPS
# - Panels have **no gaps** between them and equal size
# - Panel titles are moved slightly inside (not on the frame line)
# Outputs next to the CSV:
#   fig_keywords_clusters_ranked_columns_COMPACT.png / .pdf
#   top_keywords_by_cluster_COMPACT.csv
# -------------------------------------------------------------------

import os, re, collections, numpy as np, pandas as pd, matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

# -------------------- knobs (no CLI) --------------------
TOP_PER_CLUSTER = 12
GLOBAL_SCALE     = False   # True = same x-scale across panels; False = per panel
WRITE_CSV        = True

FIG_W, FIG_H, DPI = 9.0, 9.0, 300
TITLE_FS   = 13.5
PANEL_TTL  = 10.8
LABEL_FS   = 8.6
VALUE_FS   = 8.2
NOTE_FS    = 8.2

# Frames, padding, and layout
PANEL_PAD     = 0.004           # frame padding (very small)
PANEL_ROUND   = 0.010           # frame corner round
BAR_ROUND     = 0.003           # bar round
ROW_GAP       = 0.0030          # vertical gap between rows inside a panel
LEFT_LABEL_W  = 0.22            # fraction of panel width reserved for labels
BAR_RIGHT_PAD = 0.06            # space to right of bars for numeric values
LABEL_WRAP_CH = 24              # label wrap threshold
TITLE_INSET   = 0.010           # move title slightly **down** inside the frame

# Page gutters (title/footer)
TOP_MARGIN    = 0.06            # space for figure title
BOTTOM_MARGIN = 0.055           # space for footer
LEFT_MARGIN   = 0.055           # outer page margin
RIGHT_MARGIN  = 0.055

# ====================== FIND & READ SCOPUS CSV ====================
CANDIDATE_PATHS = [r"D:\OneDrive - Ulster University\PhD\Lit\Scopus\scopus.csv",
                   r"D:\OneDrive - Ulster University\PhD\Lit\Scopus\scopus(1).csv",
                   "/mnt/data/scopus.csv", "/mnt/data/scopus(2).csv",
                   "scopus.csv", "scopus(2).csv"]
CSV_PATH = next((p for p in CANDIDATE_PATHS if os.path.exists(p)), None)
print("[Keyword Panels] Working directory:", os.getcwd())
print("[Keyword Panels] CSV used:", CSV_PATH if CSV_PATH else "NOT FOUND")
if CSV_PATH is None:
    raise FileNotFoundError("Scopus CSV not found in: " + ", ".join(CANDIDATE_PATHS))

df = pd.read_csv(CSV_PATH)
df.columns = [c.strip() for c in df.columns]
lower_map = {c.lower(): c for c in df.columns}

def pick_col(names):
    for n in names:
        if n in df.columns: return n
        if n.lower() in lower_map: return lower_map[n.lower()]
    return None

col_authkw = pick_col(["Author Keywords", "Author keywords", "DE"])
col_indkw  = pick_col(["Index Keywords", "Index keywords", "ID"])

def split_kw_cell(s):
    if pd.isna(s): return []
    s = str(s)
    parts = re.split(r"[;,\|/]", s)
    toks = set(p.strip().lower() for p in parts if p and p.strip())
    toks = [re.sub(r"\s*\([^)]*\)", "", t).strip() for t in toks]      # drop (...)
    toks = [re.sub(r"\s+", " ", t.replace("-", " ")).strip() for t in toks]
    return sorted(set(t for t in toks if len(t) >= 2))

kw_counts_raw = collections.Counter()
if col_authkw or col_indkw:
    for _, row in df.iterrows():
        kws = set()
        if col_authkw and col_authkw in row: kws.update(split_kw_cell(row[col_authkw]))
        if col_indkw  and col_indkw  in row: kws.update(split_kw_cell(row[col_indkw ]))
        kw_counts_raw.update(kws)

if not kw_counts_raw:
    raise RuntimeError("No keywords parsed. Check the keyword columns in your CSV.")

# ===================== CLEAN & CANONICALISE =======================
CANON_RULES = [
    (r"\bartificial neural networks?\b", "artificial neural network"),
    (r"\bneural networks?\b", "neural network"),
    (r"\bsupport vector (machines?|regression)\b", "support vector machine"),
    (r"\brand(?:om)? forest(s)?\b", "random forest"),
    (r"\burban heat islands?\b", "urban heat island"),
    (r"\bbuilding energy performance\b", "energy performance"),
    (r"\bbuilding energy consumption\b", "energy consumption"),
    (r"\bconvolutional neural networks?\b", "convolutional neural network"),
    (r"\bthermal imaging\b", "thermal imagery"),
    (r"\bthermographic\b", "thermography"),
]

def canonicalize(term: str) -> str:
    t = term.strip().lower()
    for pat, rep in CANON_RULES: t = re.sub(pat, rep, t)
    # simple plural → singular
    t = re.sub(r"\bbuildings\b", "building", t)
    t = re.sub(r"\bcities\b", "city", t)
    t = re.sub(r"\bblocks\b", "block", t)
    t = re.sub(r"\bmodels\b", "model", t)
    return t

canon_counts = collections.Counter()
for k, n in kw_counts_raw.items():
    canon_counts[canonicalize(k)] += int(n)

kw_series = pd.Series(canon_counts).sort_values(ascending=False)

# ===================== CATEGORISATION (A/B/C/D) ===================
A_PATTERNS = [r"\b(building|urban|city|residential|dwelling|housing|apartment|flat|tenement|stock|typology|morphology|geometry|form|block|street|neighbou?rhood|envelope|fabric|lcz|local climate zone|urban heat island)\b"]
B_PATTERNS = [r"\b(energy performance|epc|eui|ubem|bem|overheat|thermal comfort|indoor temperature|heating|cooling|hvac|retrofit|u ?value|r ?value|heat loss|demand|consumption|insulation|blower door|leakage|air infiltration|fuel poverty|cold homes)\b"]
C_PATTERNS = [r"\b(remote sensing|earth observation|sentinel|landsat|modis|sar|lidar|thermograph|thermal (imag|band|imagery)|lst|viirs|aster|svf|sky view factor|wudapt|gee|google earth engine|gis|ndvi|ndbi|insar|dem|dsm|dtm)\b"]
D_PATTERNS = [r"\b(random forest|xgboost|xgb|svm|cnn|rnn|gnn|deep learn|neural|gradient boost|regression|calibration|validation|cross[-\s]?validation|transfer learn|domain adapt|energyplus|trnsys|citysim|qgis|arcgis|geoai|citygml|graph|clustering|topic model)\b"]

def cats_for(k: str) -> list[str]:
    cats = []
    for pat in A_PATTERNS:
        if re.search(pat, k): cats.append("A")
    for pat in B_PATTERNS:
        if re.search(pat, k): cats.append("B")
    for pat in C_PATTERNS:
        if re.search(pat, k): cats.append("C")
    for pat in D_PATTERNS:
        if re.search(pat, k): cats.append("D")
    return cats or ["Uncat"]

kw_to_cat = {k: cats_for(k) for k in kw_series.index}

# ===================== SELECT TOP-N PER CLUSTER ====================
selected, seen = {}, set()
for cat in ["A","B","C","D"]:
    items = []
    for k, n in kw_series.items():
        if k in seen: continue
        if cat in kw_to_cat[k]:
            items.append((k, int(n)))
            seen.add(k)
        if len(items) >= TOP_PER_CLUSTER: break
    selected[cat] = items

if WRITE_CSV:
    rows = []
    for cat, items in selected.items():
        for k, n in items: rows.append({"cluster": cat, "keyword": k, "count": n})
    out_csv = os.path.join(os.path.dirname(CSV_PATH) or os.getcwd(), "top_keywords_by_cluster_COMPACT.csv")
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    print("[Keyword Panels] Wrote:", out_csv)

# ====================== DISPLAY LABEL FORMATTER ====================
ACRONYM_FORCED = {
    "ndvi":"NDVI","gis":"GIS","lidar":"LIDAR","sar":"SAR","lst":"LST","viirs":"VIIRS","svf":"SVF",
    "lcz":"LCZ","uhi":"UHI","dem":"DEM","dsm":"DSM","dtm":"DTM","svm":"SVM","cnn":"CNN","rnn":"RNN",
    "gnn":"GNN","xgb":"XGB","hvac":"HVAC","trnsys":"TRNSYS","qgis":"QGIS","arcgis":"ArcGIS",
    "citygml":"CityGML","geoai":"GeoAI","ubem":"UBEM","bem":"BEM","eui":"EUI","epc":"EPC"
}
PROPER_CASE = {"energyplus":"EnergyPlus", "google earth engine":"Google Earth Engine",
               "landsat":"Landsat", "modis":"MODIS", "sentinel":"Sentinel", "wudapt":"WUDAPT",
               "citysim":"CitySim"}

def display_label(term: str) -> str:
    t = term.strip().lower()
    if t in PROPER_CASE: return PROPER_CASE[t]
    out = [ACRONYM_FORCED.get(tok, tok.capitalize()) for tok in t.split()]
    s = " ".join(out)
    s = re.sub(r"\bLi?DAR\b", "LIDAR", s, flags=re.I)
    return s

def wrap2(s: str, width: int = 24) -> str:
    words = s.split()
    l1, l2 = "", ""
    for w in words:
        test = (l1 + " " + w).strip()
        if len(test) <= width:
            l1 = test
        else:
            if l2 == "": l2 = w
            elif len(l2) + 1 + len(w) <= width: l2 = l2 + " " + w
            else: break
    return l1 if not l2 else (l1 + "\n" + l2)

# ============================ FIGURE ==============================
fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=DPI)
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis("off")

# Panel grid with **no gaps** (equal sizes)
x0 = LEFT_MARGIN
x1 = 1.0 - RIGHT_MARGIN
y0 = BOTTOM_MARGIN
y1 = 1.0 - TOP_MARGIN

panel_w = (x1 - x0) / 2.0
panel_h = (y1 - y0) / 2.0

panels = {
    "A": (x0,          x0 + panel_w, y0 + panel_h, y1),  # top-left
    "B": (x0 + panel_w, x1,           y0 + panel_h, y1),  # top-right
    "C": (x0 + panel_w, x1,           y0,           y0 + panel_h),  # bottom-right
    "D": (x0,          x0 + panel_w, y0,           y0 + panel_h),  # bottom-left
}
titles = {
    "A": "A — Built Environment",
    "B": "B — Energy/Comfort/Performance",
    "C": "C — RS/EO/GIS",
    "D": "D — Methods/Models/Tools",
}

GLOBAL_MAX = max([n for items in selected.values() for _, n in items], default=1)

def draw_panel(cat, items, rect):
    x0, x1, y0, y1 = rect
    # frame
    ax.add_patch(FancyBboxPatch((x0-PANEL_PAD, y0-PANEL_PAD),
                                (x1-x0)+2*PANEL_PAD, (y1-y0)+2*PANEL_PAD,
                                boxstyle=f"round,pad=0,rounding_size={PANEL_ROUND}",
                                fill=False, lw=0.8))
    # title — moved **inside** a bit so it doesn't sit on frame line
    ax.text((x0+x1)/2, y1 - TITLE_INSET, titles[cat], ha="center", va="top",
            fontsize=PANEL_TTL, fontweight="bold")
    if not items:
        ax.text((x0+x1)/2, (y0+y1)/2, "No terms", ha="center", va="center", fontsize=LABEL_FS)
        return

    # inner content box
    top = y1 - TITLE_INSET - 0.010     # small offset under the title
    bot = y0 + 0.018
    height = max(top - bot, 1e-6)
    n = len(items)
    bar_h = max(height / n - ROW_GAP, 0.006)

    # scaling
    local_max = max(n for _, n in items)
    denom = GLOBAL_MAX if GLOBAL_SCALE else local_max

    # lanes
    y = top - bar_h
    label_x = x0 + 0.010
    bar_x   = x0 + LEFT_LABEL_W
    max_bar_w = x1 - bar_x - BAR_RIGHT_PAD

    for kw, count in items:
        lbl = wrap2(display_label(kw), LABEL_WRAP_CH)
        ax.text(label_x, y + bar_h/2, lbl, ha="left", va="center", fontsize=LABEL_FS)
        bw = max_bar_w * (count / max(denom, 1))
        ax.add_patch(FancyBboxPatch((bar_x, y), bw, bar_h,
                                    boxstyle=f"round,pad=0,rounding_size={BAR_ROUND}"))
        ax.text(bar_x + bw + 0.010, y + bar_h/2, f"{count}", ha="left", va="center", fontsize=VALUE_FS)
        y -= (bar_h + ROW_GAP)

# draw in order
for cat in ["A","B","C","D"]:
    draw_panel(cat, selected.get(cat, []), panels[cat])

# header + note
ax.text(0.5, 0.98, "Keyword Landscape by Cluster (ranked, top terms per block)",
        ha="center", va="top", fontsize=TITLE_FS, fontweight="bold")
ax.text(0.5, 0.02,
        f"Source: {os.path.basename(CSV_PATH)}. Top {TOP_PER_CLUSTER} keywords per block (cleaned & deduped). "
        f"Bars use {'global' if GLOBAL_SCALE else 'within-panel'} scale.",
        ha="center", va="bottom", fontsize=NOTE_FS)

# save
out_dir = os.path.dirname(CSV_PATH) or os.getcwd()
png = os.path.join(out_dir, "fig_keywords_clusters_ranked_columns_COMPACT.png")
pdf = os.path.join(out_dir, "fig_keywords_clusters_ranked_columns_COMPACT.pdf")
plt.savefig(png, bbox_inches="tight")
plt.savefig(pdf, bbox_inches="tight")
print("[Keyword Panels] Saved:", png)
print("[Keyword Panels] Saved:", pdf)
