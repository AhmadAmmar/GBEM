# -*- coding: utf-8 -*-
"""
workflow_flowchart_v2_animated_always_legend.py
• Staged PNGs + PPTX 'animated' deck (right/left keys to advance/back)
• Legend is ALWAYS visible (compact HTML-table node)
• Layout: A4 landscape fit; compact v2 workflow

Reqs:
  conda install -c conda-forge graphviz python-graphviz python-pptx
"""

import os
from graphviz import Digraph
from pptx import Presentation
from pptx.util import Inches, Pt

# ------------------ Paths ------------------
OUTPUT_DIR = r"D:/OneDrive - Ulster University/PhD/Output/workflow_v2_animated"
os.makedirs(OUTPUT_DIR, exist_ok=True)
BASENAME = "workflow_v2_compact_step"

# ------------------ Theme ------------------
FONT = "Helvetica"
THEME = {
    "done":        "#d9f2d9",   # green
    "in_progress": "#fff3cd",   # yellow
    "planned":     "#e7f1ff",   # blue
    "continuous":  "#efe7ff",   # lavender
}
FADED_FILL = "#f2f2f2"
FADED_FONT = "#808080"

NODE_STYLE = {"shape": "box", "style": "rounded,filled", "fontname": FONT, "fontsize": "10"}

def h(title, sub=""):
    esc = lambda s: s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    title, sub = esc(title), esc(sub)
    return f'''<
<B>{title}</B>{('<BR ALIGN="LEFT"/><FONT POINT-SIZE="9">'+sub+"</FONT>") if sub else ""}
>'''

def add(g, nid, title, sub="", status="planned", faded=False, **kw):
    st = dict(NODE_STYLE, **kw)
    st["fillcolor"] = THEME.get(status, THEME["planned"])
    if faded:
        st["fillcolor"] = FADED_FILL
        st["fontcolor"] = FADED_FONT
        st["color"]     = "#c9c9c9"
        st["style"]     = "rounded,filled,dashed"
    g.node(nid, label=h(title, sub), **st)

def legend_html():
    # Compact, readable legend as a single HTML table (always shown)
    return f"""<
<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="2" CELLPADDING="2">
  <TR><TD ALIGN="LEFT"><B>Legend</B></TD></TR>
  <TR>
    <TD>
      <TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4">
        <TR>
          <TD BGCOLOR="{THEME['done']}">DONE</TD>
          <TD BGCOLOR="{THEME['in_progress']}">IN&nbsp;PROGRESS</TD>
          <TD BGCOLOR="{THEME['planned']}">PLANNED</TD>
          <TD BGCOLOR="{THEME['continuous']}">CONTINUOUS</TD>
        </TR>
      </TABLE>
    </TD>
  </TR>
</TABLE>
>"""

def build_graph(stage_idx):
    """
    Stage order:
      1 Foundations
      2 Data
      3 Preprocessing
      4 Features
      5 Modeling
      6 Evaluation
      7 Scaling/Comms/Policy
      8 Milestones (legend is ALWAYS visible)
    """
    g = Digraph("PhD_Workflow_V2_Compact_A4", format="png")
    g.attr(
        rankdir="TB", splines="ortho", concentrate="true", compound="true",
        size="11.69,8.27!", ratio="compress", margin="0.2",
        nodesep="0.18", ranksep="0.22",
        fontname=FONT, fontsize="16",
        label="Assessing Building Energy Efficiency — Workflow v2 (Compact, A4)"
    )
    g.edge_attr.update({"arrowhead": "normal"})

    reveal = {
        "found": stage_idx >= 1,
        "data":  stage_idx >= 2,
        "pre":   stage_idx >= 3,
        "feat":  stage_idx >= 4,
        "model": stage_idx >= 5,
        "eval":  stage_idx >= 6,
        "out":   stage_idx >= 7,
        "mile":  stage_idx >= 8,
    }

    # ── ALWAYS-ON Legend (compact table) ─────────────────────────────
    with g.subgraph(name="cluster_legend") as c:
        c.attr(label="Legend", style="rounded", color="#aaaaaa", fontsize="11")
        c.node("LEG", label=legend_html(), shape="box", style="rounded", fontname=FONT)

    # ── Foundations ──────────────────────────────────────────────────
    with g.subgraph(name="cluster_found") as c:
        c.attr(label="Foundations (Continuous)", style="rounded", color="#888888", fontsize="12")
        add(c, "FOUND", "Foundations",
            "Research scope • Ethics/Privacy (aggregate) • Repro/versioning • Documentation",
            "continuous", faded=not reveal["found"])

    # ── Data & Assets ────────────────────────────────────────────────
    with g.subgraph(name="cluster_data") as c:
        c.attr(label="Data & Assets", style="rounded", color="#000000", fontsize="12")
        for nid, title, sub, status in [
            ("EPC_LON","EPC London + UPRN","union_v2 XY","done"),
            ("EPC_BFS","EPC Belfast + UPRN","union_v2 XY","done"),
            ("S1S2","Sentinel-1/2","mosaics + indices base","done"),
            ("L8","Landsat-8 LST / sUHI","thermal proxies","in_progress"),
            ("LCZ","LCZ / WorldCover","urban classes","in_progress"),
            ("LIDAR","LiDAR","heights / SVF","planned"),
        ]:
            add(c, nid, title, sub, status, faded=not reveal["data"])

    # ── Preprocessing ────────────────────────────────────────────────
    with g.subgraph(name="cluster_pre") as c:
        c.attr(label="Preprocessing", style="rounded", color="#000000", fontsize="12")
        for nid, title, sub, status in [
            ("CRS","CRS + Harmonization","resample/normalize","done"),
            ("MASK","Quality Masks","cloud/SAR; valid frac","in_progress"),
            ("R2V","Raster↔Vector Joins","zonal means per building","in_progress"),
            ("SPLIT","Spatial Splits","blocked train/val/test","in_progress"),
        ]:
            add(c, nid, title, sub, status, faded=not reveal["pre"])

    # ── Features ─────────────────────────────────────────────────────
    with g.subgraph(name="cluster_feat") as c:
        c.attr(label="Feature Engineering", style="rounded", color="#000000", fontsize="12")
        for nid, title, sub, status in [
            ("IDX","Spectral Indices","NDVI/SAVI/LSWI/NDBI/IBI","in_progress"),
            ("SARF","SAR Features","VV/VH ratios • textures","planned"),
            ("MORPH","Morphology & Climate","LCZ stats • degree-days","in_progress"),
            ("THERM","Thermal Anomalies","LST/sUHI contrasts","in_progress"),
        ]:
            add(c, nid, title, sub, status, faded=not reveal["feat"])

    # ── Modeling ─────────────────────────────────────────────────────
    with g.subgraph(name="cluster_model") as c:
        c.attr(label="Modeling", style="rounded", color="#000000", fontsize="12")
        for nid, title, sub, status in [
            ("BASE","Baseline RF/XGB","Binary≈0.66 • Multi≈0.57","done"),
            ("ORD","Ordinal","A–G aware","in_progress"),
            ("CALUNC","Calibration + Uncertainty","Isotonic/Dirichlet • Conformal/entropy","in_progress"),
            ("TRANS","Transfer LON↔BFS","generalization & uplift","in_progress"),
            ("ABLFAIR","Ablations + Fairness","feature families • LCZ/deprivation","planned"),
        ]:
            add(c, nid, title, sub, status, faded=not reveal["model"])

    # ── Evaluation ───────────────────────────────────────────────────
    with g.subgraph(name="cluster_eval") as c:
        c.attr(label="Evaluation", style="rounded", color="#000000", fontsize="12")
        for nid, title, sub, status in [
            ("CV","Spatially-Blocked CV","leakage-aware folds","in_progress"),
            ("KPI","KPIs","Macro-F1 • within-1-grade • κ • AUROC • ECE","in_progress"),
            ("VIS","Maps & Visuals","A–G + binary layers","done"),
        ]:
            add(c, nid, title, sub, status, faded=not reveal["eval"])

    # ── Scaling / Comms / Policy ─────────────────────────────────────
    with g.subgraph(name="cluster_out") as c:
        c.attr(label="Scaling • Communication • Policy", style="rounded", color="#000000", fontsize="12")
        for nid, title, sub, status in [
            ("PIPE","Automated Pipeline","batch/export orchestration","in_progress"),
            ("DASH","Dashboards","split-screen A–G vs Binary","in_progress"),
            ("BFS","Belfast Expansion","parity with London","in_progress"),
            ("UK","UK-wide Scaling","phase onward","planned"),
            ("COMMS","Review • Talks • Thesis","PRISMA/tables • AGI NI • chapters","in_progress"),
            ("POLICY","Policy & Retrofit Targeting","high-priority areas","planned"),
        ]:
            add(c, nid, title, sub, status, faded=not reveal["out"])

    # ── Milestones (legend is separate/always on) ────────────────────
    with g.subgraph(name="cluster_mile") as c:
        c.attr(label="Milestones", style="rounded", color="#888888", fontsize="11")
        for nid, title, sub, status in [
            ("M1","Initial Assessment v1","Sep 2024","done"),
            ("M2","Confirmation v2","Oct 2025","in_progress"),
            ("M3","Confirmation Viva","Aug 2026","planned"),
        ]:
            add(c, nid, title, sub, status, faded=not reveal["mile"])
        c.edge("M1","M2"); c.edge("M2","M3")

    # ── Main spine (keep edges for stable layout) ────────────────────
    g.edge("FOUND","EPC_LON", ltail="cluster_found", lhead="cluster_data")
    for src in ["EPC_LON","EPC_BFS","S1S2","L8","LCZ","LIDAR"]:
        g.edge(src,"CRS", ltail="cluster_data", lhead="cluster_pre")

    g.edge("SPLIT","IDX", ltail="cluster_pre", lhead="cluster_feat")
    for f in ["IDX","SARF","MORPH","THERM"]:
        g.edge(f,"BASE", ltail="cluster_feat", lhead="cluster_model")

    for m in ["BASE","ORD","CALUNC","TRANS","ABLFAIR"]:
        g.edge(m,"CV", ltail="cluster_model", lhead="cluster_eval")

    g.edge("KPI","PIPE", ltail="cluster_eval", lhead="cluster_out")
    g.edge("PIPE","DASH"); g.edge("DASH","BFS"); g.edge("BFS","UK")
    g.edge("UK","POLICY"); g.edge("COMMS","POLICY")

    # Feedback loops
    g.edge("CV","CALUNC", dir="both", style="dashed")
    g.edge("CV","ORD",    dir="both", style="dashed")
    g.edge("KPI","IDX",   dir="both", style="dashed")
    g.edge("POLICY","EPC_LON", style="dotted"); g.edge("POLICY","EPC_BFS", style="dotted")
    return g

# ------------------ Render staged images ------------------
STAGES = [
    (1, "Foundations"),
    (2, "Data & Assets"),
    (3, "Preprocessing"),
    (4, "Feature Engineering"),
    (5, "Modeling"),
    (6, "Evaluation"),
    (7, "Scaling • Comms • Policy"),
    (8, "Milestones"),
]

png_paths = []
for idx, name in STAGES:
    g = build_graph(idx)
    out = os.path.join(OUTPUT_DIR, f"{BASENAME}_{idx:02d}_{name.replace(' ', '_').replace('•','-')}")
    png = g.render(out, format="png", view=False, cleanup=True)
    png_paths.append((name, png))

# ------------------ Build PPTX ------------------
prs = Presentation()
# Widescreen; switch to A4 by uncommenting the two lines below
# prs.slide_width  = Inches(11.69)
# prs.slide_height = Inches(8.27)

title_fontsz = Pt(24)
subtitle_fontsz = Pt(14)

# Title slide
slide = prs.slides.add_slide(prs.slide_layouts[5])  # blank
tx = slide.shapes.add_textbox(Inches(0.4), Inches(0.3), prs.slide_width - Inches(0.8), Inches(1.4))
tf = tx.text_frame
p = tf.paragraphs[0]; p.text = "Assessing Building Energy Efficiency — Workflow v2 (Animated)"; p.font.bold = True
p.font.size = title_fontsz; p.font.name = FONT
p2 = tf.add_paragraph(); p2.text = "Legend is always visible. Use →/← or click to navigate."
p2.font.size = subtitle_fontsz; p2.font.name = FONT

# One slide per stage
for (label, path) in png_paths:
    slide = prs.slides.add_slide(prs.slide_layouts[5])  # blank
    hdr = slide.shapes.add_textbox(Inches(0.4), Inches(0.3), prs.slide_width - Inches(0.8), Inches(0.6))
    ht = hdr.text_frame; ht.clear()
    hp = ht.paragraphs[0]; hp.text = f"Workflow v2 — {label}"
    hp.font.size = subtitle_fontsz; hp.font.bold = True; hp.font.name = FONT
    # Image full width
    max_w = prs.slide_width - Inches(0.6)
    slide.shapes.add_picture(path, Inches(0.3), Inches(0.9), width=max_w)

pptx_path = os.path.join(OUTPUT_DIR, "workflow_v2_animated_always_legend.pptx")
prs.save(pptx_path)
print("Exported PPTX:", pptx_path)
print("Stage PNGs:", [p for _, p in png_paths])
