# -*- coding: utf-8 -*-
# workflow_flowchart_v2_vertical_slide_status_bullets_fixed_readable.py
# Vertical 16:9 slide — title at top, side-by-side legends at bottom.
# Nodes use LEFT-aligned HTML tables with bold, larger text for readability.
# Exports SVG (vector), PNG (900 DPI), PDF (vector).

from graphviz import Digraph

OUT  = r"D:/OneDrive - Ulster University/PhD/Output/workflow_flowchart_v2_vertical_slide_status_bullets_fixed_readable"
FONT = "Helvetica"

# Stage (node fill) colors
THEME = {
    "done":        "#d9f2d9",
    "in_progress": "#fff3cd",
    "planned":     "#e7f1ff",
    "continuous":  "#efe7ff",
}

# Bullet (text) colors (darker, readable)
DOT = {
    "done":        "#2e7d32",   # dark green
    "in_progress": "#cc7a00",   # dark amber
    "planned":     "#2a63c5",   # dark blue
    "continuous":  "#6c3bb6",   # dark purple
}

NODE = {"shape":"box","style":"rounded,filled","fontname":FONT,"fontsize":"12","penwidth":"1.2"}  # +1 pt

def esc(s: str) -> str:
    return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def bullet(label: str, status: str, pt: int = 11) -> str:
    # colored dot + bold text (slightly larger)
    return f'<FONT COLOR="{DOT[status]}">●</FONT>&nbsp;<B><FONT POINT-SIZE="{pt}">{esc(label)}</FONT></B>'

def table_label(title: str, rows: list[str]) -> str:
    """HTML-like TABLE label with bold, slightly larger title and left-aligned bullet rows."""
    title = esc(title)
    body = "".join(f'<TR><TD ALIGN="LEFT">{r}</TD></TR>' for r in rows)
    return f"""<
<TABLE BORDER="0" CELLBORDER="0" CELLPADDING="0" CELLSPACING="2">
  <TR><TD ALIGN="LEFT"><FONT POINT-SIZE="12"><B>{title}</B></FONT></TD></TR>
  {body}
</TABLE>
>"""

def legend_html():
    # Two legends side-by-side: (left) Stage fill, (right) Bullet colors
    return f"""<
<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="8" CELLPADDING="0">
  <TR>
    <TD>
      <TABLE BORDER="0" CELLBORDER="1" CELLPADDING="4" CELLSPACING="0">
        <TR><TD COLSPAN="4" ALIGN="LEFT"><B>Legend — Stage (node fill)</B></TD></TR>
        <TR>
          <TD BGCOLOR="{THEME['done']}">DONE</TD>
          <TD BGCOLOR="{THEME['in_progress']}">IN&nbsp;PROGRESS</TD>
          <TD BGCOLOR="{THEME['planned']}">PLANNED</TD>
          <TD BGCOLOR="{THEME['continuous']}">CONTINUOUS</TD>
        </TR>
      </TABLE>
    </TD>
    <TD>
      <TABLE BORDER="0" CELLBORDER="1" CELLPADDING="4" CELLSPACING="0">
        <TR><TD COLSPAN="4" ALIGN="LEFT"><B>Legend — Subcomponents (bullets)</B></TD></TR>
        <TR>
          <TD ALIGN="LEFT"><FONT COLOR="{DOT['done']}">●</FONT>&nbsp;Done</TD>
          <TD ALIGN="LEFT"><FONT COLOR="{DOT['in_progress']}">●</FONT>&nbsp;In&nbsp;Progress</TD>
          <TD ALIGN="LEFT"><FONT COLOR="{DOT['planned']}">●</FONT>&nbsp;Planned</TD>
          <TD ALIGN="LEFT"><FONT COLOR="{DOT['continuous']}">●</FONT>&nbsp;Continuous</TD>
        </TR>
      </TABLE>
    </TD>
  </TR>
</TABLE>
>"""

g = Digraph("Workflow_V2_Vertical_Slide_StatusBullets_Fixed_Readable", format="svg")
g.attr(rankdir="TB", splines="ortho", concentrate="true", compound="true",
       size="13.33,7.5!", ratio="compress", margin="0.25",      # 16:9 slide
       nodesep="0.20", ranksep="0.30",
       fontname=FONT, fontsize="18",
       dpi="900",  # high DPI for raster outputs (PNG); SVG/PDF are vector
       label="Assessing Building Energy Efficiency — Workflow v2",
       labelloc="t")
g.edge_attr.update({"arrowhead":"normal"})

def add_node(nid, title, stage_status, items, **kw):
    st = dict(NODE, fillcolor=THEME[stage_status])
    st.setdefault("width", "6.8")  # a bit wider so larger text wraps less
    st.update(kw)
    g.node(nid, label=table_label(title, items), **st)

# ───────────── Nodes ─────────────
add_node("FOUND", "Foundations (Continuous)", "continuous", [
    bullet("Research scope & objectives", "continuous"),
    bullet("Ethics, privacy, reproducibility, versioning & documentation", "continuous"),
])

add_node("DATA", "Data & Assets", "in_progress", [
    bullet("EPC — London & Belfast with UPRN", "done"),
    bullet("Sentinel-1 SAR & Sentinel-2 multispectral mosaics", "done"),
    bullet("LST / sUHI, LCZ, ERA-5 Climate Layers, LiDAR or DEM, SVF", "in_progress"),
])

add_node("PREP", "Preprocessing", "done", [
    bullet("Filtering, quality masks, CRS standardization & normalization", "done"),
    bullet("Raster→Vector joins (zonal means per building)", "done"),
    bullet("Spatially blocked train/validation/test splits", "done"),
])

add_node("FEAT", "Feature Engineering", "in_progress", [
    bullet("Spectral indices (NDVI, SAVI, LSWI, NDBI, IBI, albedo proxy)", "done"),
    bullet("SAR ratios & texture metrics", "in_progress"),
    bullet("Urban morphology, micro-climate & thermal anomalies", "in_progress"),
])

add_node("MODEL", "Modeling", "in_progress", [
    bullet("RF/XGB baseline", "done"),
    bullet("Ordinal learning (A–G aware), calibration & uncertainty, transfer learning London ↔ Belfast", "in_progress"),
])

add_node("EVAL", "Evaluation", "in_progress", [
    bullet("KPIs: Macro-F1, within-one-grade, Quadratic κ, AUROC, ECE", "in_progress"),
    bullet("Maps & visuals: 1. A–G & binary layers, 2. hotspots, 3. uncertainty", "in_progress"),
])

add_node("OUT", "Scaling • Communication • Policy", "in_progress", [
    bullet("Automated pipeline & batch/export orchestration", "in_progress"),
    bullet("Dashboards (split-screen A–G vs binary)", "in_progress"),
    bullet("Belfast expansion → UK-wide scaling", "in_progress"),
    bullet("Papers, talks & thesis", "in_progress"),
    bullet("Policy & retrofit targeting", "planned"),
])

# Spine + gentle feedback hints
g.edge("FOUND","DATA"); g.edge("DATA","PREP"); g.edge("PREP","FEAT")
g.edge("FEAT","MODEL"); g.edge("MODEL","EVAL"); g.edge("EVAL","OUT")
g.edge("EVAL","MODEL", style="dashed", dir="back")
g.edge("OUT","DATA",  style="dotted", dir="back")

# Legends at bottom (side-by-side)
with g.subgraph(name="rank_legend") as r:
    r.attr(rank="sink")
    r.node("LEG", label=legend_html(), shape="box", style="rounded", fontname=FONT, fontsize="10")
g.edge("OUT","LEG", style="invis")

# Render
g.render(OUT, format="svg", view=False, cleanup=True)
g.render(OUT, format="png", view=False, cleanup=True)   # uses dpi=900
g.render(OUT, format="pdf", view=False, cleanup=True)

print("Saved:", OUT + ".svg,", OUT + ".png,", OUT + ".pdf")
