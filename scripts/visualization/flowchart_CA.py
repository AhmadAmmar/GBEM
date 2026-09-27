# -*- coding: utf-8 -*-
# workflow_flowchart_v2_compact_a4.py
# Compact v2 (Confirmation) flowchart that fits on one A4 page.

from graphviz import Digraph

# ── Output ────────────────────────────────────────────────────────────────
OUTPUT_PATH = r"D:/OneDrive - Ulster University/PhD/Output/workflow_flowchart_v2_compact_a4"
FORMAT = "pdf"     # vector for print; change to "png" if needed
FONT = "Helvetica"

# ── Theme ────────────────────────────────────────────────────────────────
THEME = {
    "done":        "#d9f2d9",  # green
    "in_progress": "#fff3cd",  # yellow
    "planned":     "#e7f1ff",  # blue
    "continuous":  "#efe7ff",  # lavender
}
NODE_STYLE = {"shape": "box", "style": "rounded,filled", "fontname": FONT, "fontsize": "10"}

def h(title, sub=""):
    title = (title.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"))
    sub   = (sub.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"))
    return f'''<
<B>{title}</B>{('<BR ALIGN="LEFT"/><FONT POINT-SIZE="9">'+sub+"</FONT>") if sub else ""}
>'''

def add(node_id, title, sub="", status="planned", graph=None, **kw):
    st = dict(NODE_STYLE, fillcolor=THEME[status], **kw)
    (graph or g).node(node_id, label=h(title, sub), **st)

# ── Graph ────────────────────────────────────────────────────────────────
g = Digraph("PhD_Workflow_V2_Compact_A4", format=FORMAT)
g.attr(
    rankdir="TB", splines="ortho", concentrate="true", compound="true",
    size="11.69,8.27!", ratio="compress", margin="0.2",  # A4 landscape fit
    nodesep="0.18", ranksep="0.22",
    fontname=FONT, fontsize="16",
    label="Assessing Building Energy Efficiency — Workflow v2 (Compact, A4)"
)
g.edge_attr.update({"arrowhead": "normal"})

# ── Foundations (1 compact node; continuous) ─────────────────────────────
with g.subgraph(name="cluster_found") as c:
    c.attr(label="Foundations (Continuous)", style="rounded", color="#888888", fontsize="12")
    add("FOUND", "Foundations",
        "Research scope • Ethics/Privacy (aggregate outputs) • Repro/versioning • Documentation",
        "continuous", c)

# ── Data & Assets (essential only) ───────────────────────────────────────
with g.subgraph(name="cluster_data") as c:
    c.attr(label="Data & Assets", style="rounded", color="#000000", fontsize="12")
    add("EPC_LON","EPC London + UPRN","union_v2 XY","done", c)
    add("EPC_BFS","EPC Belfast + UPRN","union_v2 XY","done", c)
    add("S1S2","Sentinel-1/2","mosaics + indices base","done", c)
    add("L8","Landsat-8 LST / sUHI","thermal proxies","in_progress", c)
    add("LCZ","LCZ / WorldCover","urban classes","in_progress", c)
    add("LIDAR","LiDAR","heights / SVF","planned", c)

# ── Preprocessing (condensed) ────────────────────────────────────────────
with g.subgraph(name="cluster_pre") as c:
    c.attr(label="Preprocessing", style="rounded", color="#000000", fontsize="12")
    add("CRS","CRS + Harmonization","resample/normalize","done", c)
    add("MASK","Quality Masks","cloud/SAR; valid frac","in_progress", c)
    add("R2V","Raster↔Vector Joins","zonal means per building","in_progress", c)
    add("SPLIT","Spatial Splits","blocked train/val/test","in_progress", c)

# ── Features (grouped) ───────────────────────────────────────────────────
with g.subgraph(name="cluster_feat") as c:
    c.attr(label="Feature Engineering", style="rounded", color="#000000", fontsize="12")
    add("IDX","Spectral Indices","NDVI/SAVI/LSWI/NDBI/IBI","in_progress", c)
    add("SARF","SAR Features","VV/VH ratios • textures","planned", c)
    add("MORPH","Morphology & Climate","LCZ stats • degree-days","in_progress", c)
    add("THERM","Thermal Anomalies","LST/sUHI contrasts","in_progress", c)

# ── Modeling (compact) ───────────────────────────────────────────────────
with g.subgraph(name="cluster_model") as c:
    c.attr(label="Modeling", style="rounded", color="#000000", fontsize="12")
    add("BASE","Baseline RF/XGB","Binary≈0.66 • Multi≈0.57","done", c)
    add("ORD","Ordinal","A–G aware","in_progress", c)
    add("CALUNC","Calibration + Uncertainty","Isotonic/Dirichlet • Conformal/entropy","in_progress", c)
    add("TRANS","Transfer LON↔BFS","generalization & uplift","in_progress", c)
    add("ABLFAIR","Ablations + Fairness","by feature family • LCZ/deprivation","planned", c)

# ── Evaluation (merged KPIs) ─────────────────────────────────────────────
with g.subgraph(name="cluster_eval") as c:
    c.attr(label="Evaluation", style="rounded", color="#000000", fontsize="12")
    add("CV","Spatially-Blocked CV","leakage-aware folds","in_progress", c)
    add("KPI","KPIs","Macro-F1 • within-1-grade • κ • AUROC • ECE","in_progress", c)
    add("VIS","Maps & Visuals","A–G + binary layers","done", c)

# ── Scaling, Communication & Policy (merged) ─────────────────────────────
with g.subgraph(name="cluster_out") as c:
    c.attr(label="Scaling • Communication • Policy", style="rounded", color="#000000", fontsize="12")
    add("PIPE","Automated Pipeline","batch/export orchestration","in_progress", c)
    add("DASH","Dashboards","split-screen A–G vs Binary","in_progress", c)
    add("BFS","Belfast Expansion","parity with London","in_progress", c)
    add("UK","UK-wide Scaling","phase onward","planned", c)
    add("COMMS","Review • Talks • Thesis","PRISMA/tables • AGI NI • chapters","in_progress", c)
    add("POLICY","Policy & Retrofit Targeting","high-priority areas","planned", c)

# ── Milestones & Legend (tiny) ───────────────────────────────────────────
with g.subgraph(name="cluster_meta") as c:
    c.attr(label="Milestones & Legend", style="rounded", color="#888888", fontsize="11")
    add("M1","Initial Assessment v1","Sep 2024","done", c)
    add("M2","Confirmation v2","Oct 2025","in_progress", c)
    add("M3","Confirmation Viva","Aug 2026","planned", c)
    c.edge("M1","M2"); c.edge("M2","M3")
    add("LG1","DONE",status="done",graph=c); add("LG2","IN PROGRESS",status="in_progress",graph=c)
    add("LG3","PLANNED",status="planned",graph=c); add("LG4","CONTINUOUS",status="continuous",graph=c)
    c.edge("LG1","LG2",style="invis"); c.edge("LG3","LG4",style="invis")

# ── Spine (minimal edges) ────────────────────────────────────────────────
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

# Gentle feedback loops (dashed/dotted)
g.edge("CV","CALUNC", dir="both", style="dashed")
g.edge("CV","ORD",    dir="both", style="dashed")
g.edge("KPI","IDX",   dir="both", style="dashed")
g.edge("POLICY","EPC_LON", style="dotted"); g.edge("POLICY","EPC_BFS", style="dotted")

# ── Render ───────────────────────────────────────────────────────────────
g.render(OUTPUT_PATH, view=True, cleanup=True)
print(f"Saved A4 compact flowchart → {OUTPUT_PATH}.{FORMAT}")
