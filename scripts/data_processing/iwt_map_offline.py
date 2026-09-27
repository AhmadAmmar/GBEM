"""
Step 2 — Offline IWT Map (Folium + local datasets only)

Reads pre-fetched assets produced by `iwt_fetch_assets.py` and builds the map.
- Western rivers: Indus, Jhelum, Chenab (from NE)
- Eastern rivers: Ravi, Beas, Sutlej (from NE)
- Kabul tributary (from NE; falls back to saved OSM lines)
- Dams/Weirs/Barrages: points (clustered, purple) from saved GeoJSON
- Reservoir outlines, optional canals, admin outlines (all from saved GeoJSON)
- Curated IWT sites layer with notes
- Basemap choices, river glow, in-line labels, fullscreen/minimap/measure/mouse position
- Auto-zoom to available layers

No internet data-fetching. (Basemap tiles still load online.)
"""

from __future__ import annotations

import json
import os
from typing import Dict, List

import geopandas as gpd
import pandas as pd
import folium
from folium.plugins import (
    MarkerCluster,
    PolyLineTextPath,
    Fullscreen,
    MiniMap,
    MeasureControl,
    MousePosition,
)
from shapely.geometry import LineString, MultiLineString, Polygon

# ------------------------------
# USER SETTINGS
# ------------------------------

# Where Step-1 saved everything (manifest lives here)
SCRIPT_DIR = os.path.dirname(__file__)
DATA_DIR   = os.path.join(SCRIPT_DIR, "data_iwt_assets")
MANIFEST   = os.path.join(DATA_DIR, "manifest.json")

# Output HTML
OUTPUT_HTML = "indus_iwt_map.html"

# Visual toggles
INCLUDE_ADMIN_OUTLINES = True
INCLUDE_CANALS         = False   # only if present in manifest

# ------------------------------
# CONSTANTS / STYLES
# ------------------------------

# Treaty rivers
WESTERN_RIVERS = ["Indus", "Jhelum", "Chenab"]
EASTERN_RIVERS = ["Ravi", "Beas", "Sutlej"]
OTHER_KEY_TRIBUTARIES = ["Kabul", "Kabol", "Kābul", "Cabul"]

RIVER_STYLE = {
    "Indus":  {"color": "#0057e7", "weight": 3},
    "Jhelum": {"color": "#1f77b4", "weight": 3},
    "Chenab": {"color": "#1f77b4", "weight": 3},
    "Ravi":   {"color": "#ff7f0e", "weight": 3},
    "Beas":   {"color": "#ff7f0e", "weight": 3},
    "Sutlej": {"color": "#ff7f0e", "weight": 3},
}
OTHER_TRIB_STYLE = {"color": "#2ca02c", "weight": 3}

# Curated IWT sites (static, offline)
CURATED_IWT_SITES = [
    {"name": "Tarbela Dam (Indus)", "lat": 34.088, "lon": 72.695, "type": "Dam", "note": "Largest on Indus; Western river."},
    {"name": "Mangla Dam (Jhelum)", "lat": 33.148, "lon": 73.643, "type": "Dam", "note": "Major storage on Western river."},
    {"name": "Chashma Barrage (Indus)", "lat": 32.433, "lon": 71.383, "type": "Barrage", "note": "Control + canal offtakes."},
    {"name": "Taunsa Barrage (Indus)", "lat": 30.705, "lon": 70.848, "type": "Barrage", "note": "Indus irrigation control."},
    {"name": "Guddu Barrage (Indus)", "lat": 28.411, "lon": 69.703, "type": "Barrage", "note": "Indus irrigation control."},
    {"name": "Sukkur Barrage (Indus)", "lat": 27.684, "lon": 68.852, "type": "Barrage", "note": "Historic barrage."},
    {"name": "Kotri Barrage (Indus)", "lat": 25.380, "lon": 68.313, "type": "Barrage", "note": "Downstream Indus barrage."},
    {"name": "Marala Headworks (Chenab)", "lat": 32.673, "lon": 74.463, "type": "Headworks", "note": "Chenab offtakes."},
    {"name": "Qadirabad Headworks (Chenab)", "lat": 32.330, "lon": 73.764, "type": "Headworks", "note": "Chenab offtakes."},
    {"name": "Balloki Headworks (Ravi)", "lat": 31.205, "lon": 73.882, "type": "Headworks", "note": "Eastern river diversions."},
    {"name": "Ranjit Sagar (Thein) Dam (Ravi)", "lat": 32.441, "lon": 75.705, "type": "Dam", "note": "Eastern river project."},
    {"name": "Harike Headworks (Sutlej–Beas)", "lat": 31.138, "lon": 74.955, "type": "Headworks", "note": "Confluence control."},
    {"name": "Ferozepur Headworks (Sutlej)", "lat": 30.962, "lon": 74.619, "type": "Headworks", "note": "Sutlej offtakes."},
    {"name": "Baglihar (Chenab)", "lat": 33.096, "lon": 75.715, "type": "Hydel", "note": "Run-of-river; Western river."},
    {"name": "Kishanganga (Jhelum/Nilm)", "lat": 34.535, "lon": 74.722, "type": "Hydel", "note": "Diversion project."},
    {"name": "Ratle (Chenab)", "lat": 33.110, "lon": 75.429, "type": "Hydel", "note": "Under development."},
    {"name": "Salal (Chenab)", "lat": 33.215, "lon": 74.726, "type": "Hydel", "note": "Run-of-river."},
    {"name": "Uri-II (Jhelum)", "lat": 34.080, "lon": 74.028, "type": "Hydel", "note": "Run-of-river."},
]

# ------------------------------
# HELPERS
# ------------------------------

def add_river_with_glow(group, geom, color, label):
    # halo
    folium.GeoJson(
        geom.__geo_interface__,
        style_function=lambda _f: {"color": "#ffffff", "weight": 7, "opacity": 0.65}
    ).add_to(group)
    # colored stroke
    folium.GeoJson(
        geom.__geo_interface__,
        style_function=lambda _f, c=color: {"color": c, "weight": 3, "opacity": 0.95},
        tooltip=folium.Tooltip(label),
        popup=folium.Popup(f"<b>{label}</b>")
    ).add_to(group)

def add_line_label(group, geom, text):
    def add_one(ls: LineString):
        coords = [(y, x) for x, y in list(ls.coords)]  # lon/lat -> lat/lon
        carrier = folium.PolyLine(locations=coords, opacity=0)
        group.add_child(carrier)
        PolyLineTextPath(
            carrier, text, repeat=True, offset=7,
            attributes={'font-weight': 'bold', 'font-size': '12px'}
        ).add_to(group)

    if isinstance(geom, LineString):
        add_one(geom)
    elif isinstance(geom, MultiLineString):
        for ls in geom.geoms:
            add_one(ls)

def load_manifest(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ------------------------------
# LOAD DATA (OFFLINE)
# ------------------------------

if not os.path.exists(MANIFEST):
    raise FileNotFoundError(f"manifest.json not found at {MANIFEST}. Run iwt_fetch_assets.py first.")

manifest = load_manifest(MANIFEST)

# Required datasets
rivers_path = manifest["ne_filtered_rivers"]
admin_path  = manifest.get("ne_admin0_bbox")
dams_pts_path   = manifest.get("osm_dams_points")
res_lines_path  = manifest.get("osm_reservoirs_lines")
canals_path     = manifest.get("osm_canals_lines")  # may be absent
kabul_lines_path= manifest.get("osm_kabul_lines")   # fallback

# Load geodataframes (any missing file becomes empty gdf)
def safe_read_geojson(p):
    if p and os.path.exists(p):
        return gpd.read_file(p).to_crs(4326)
    return gpd.GeoDataFrame(geometry=[], crs=4326)

ne_rivers = safe_read_geojson(rivers_path)
admin0    = safe_read_geojson(admin_path)
dams_pts  = safe_read_geojson(dams_pts_path)
res_lines = safe_read_geojson(res_lines_path)
canals    = safe_read_geojson(canals_path)
kabul_fb  = safe_read_geojson(kabul_lines_path)

# Categorize rivers
rivers_west  = ne_rivers[ne_rivers["name"].isin(WESTERN_RIVERS)]
rivers_east  = ne_rivers[ne_rivers["name"].isin(EASTERN_RIVERS)]
rivers_other = ne_rivers[ne_rivers["name"].isin(OTHER_KEY_TRIBUTARIES)]

# ------------------------------
# BUILD MAP
# ------------------------------

m = folium.Map(location=[29.5, 70.5], zoom_start=6, tiles="CartoDB positron", control_scale=True)

# Basemap choices
folium.TileLayer("CartoDB positron", name="Positron").add_to(m)
folium.TileLayer("CartoDB dark_matter", name="Dark").add_to(m)
folium.TileLayer(
    tiles="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    name="OpenTopoMap", attr="© OpenTopoMap, SRTM"
).add_to(m)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    name="ESRI Imagery", attr="Tiles © Esri"
).add_to(m)

# Feature groups
fg_admin = folium.FeatureGroup(name="Admin Outlines (NE)", show=False)
fg_west  = folium.FeatureGroup(name="Western Rivers (IWT)", show=True)
fg_east  = folium.FeatureGroup(name="Eastern Rivers (IWT)", show=True)
fg_other = folium.FeatureGroup(name="Other Key Tributaries", show=True)
fg_dams  = folium.FeatureGroup(name="Dams / Weirs / Barrages (OSM)", show=True)
fg_res   = folium.FeatureGroup(name="Reservoirs (OSM)", show=False)
fg_can   = folium.FeatureGroup(name="Named Canals (OSM)", show=False)
fg_cur   = folium.FeatureGroup(name="Key IWT Sites (Curated)", show=True)

# Admin outlines
if INCLUDE_ADMIN_OUTLINES and not admin0.empty:
    folium.GeoJson(
        admin0.to_json(),
        style_function=lambda _f: {"color":"#666", "weight":1, "opacity":0.8, "fillOpacity":0}
    ).add_to(fg_admin)
    fg_admin.add_to(m)

# Rivers (glow + labels)
for _, r in rivers_west.iterrows():
    col = RIVER_STYLE.get(r["name"], {"color":"#2b8cbe"})["color"]
    add_river_with_glow(fg_west, r["geometry"], col, f"{r['name']} (Western)")
    add_line_label(fg_west, r["geometry"], f"  {r['name'].upper()}  ▸  ")

for _, r in rivers_east.iterrows():
    col = RIVER_STYLE.get(r["name"], {"color":"#fdae61"})["color"]
    add_river_with_glow(fg_east, r["geometry"], col, f"{r['name']} (Eastern)")
    add_line_label(fg_east, r["geometry"], f"  {r['name'].upper()}  ▸  ")

if not rivers_other.empty:
    for _, r in rivers_other.iterrows():
        add_river_with_glow(fg_other, r["geometry"], OTHER_TRIB_STYLE["color"], r["name"])
        add_line_label(fg_other, r["geometry"], f"  {r['name'].upper()}  ▸  ")
elif not kabul_fb.empty:
    folium.GeoJson(
        kabul_fb.to_json(),
        style_function=lambda _f: OTHER_TRIB_STYLE,
        tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["River:"])
    ).add_to(fg_other)

fg_west.add_to(m); fg_east.add_to(m); fg_other.add_to(m)

# Purple cluster CSS for dams
from branca.element import Element
cluster_css = """
<style>
.marker-cluster-purple div { background-color: rgba(106,61,154,0.70); }
.marker-cluster-purple span { color: #fff; font-weight: 600; }
</style>"""
m.get_root().header.add_child(Element(cluster_css))
icon_create_function = """
function(cluster) {
  var childCount = cluster.getChildCount();
  var size = childCount < 50 ? 'small' : (childCount < 200 ? 'medium' : 'large');
  return new L.DivIcon({
    html: '<div><span>' + childCount + '</span></div>',
    className: 'marker-cluster marker-cluster-purple marker-cluster-' + size,
    iconSize: new L.Point(40, 40)
  });
}
"""

# Dams/Weirs/Barrages points (cluster)
cluster = MarkerCluster(icon_create_function=icon_create_function).add_to(fg_dams)
if not dams_pts.empty:
    for _, r in dams_pts.iterrows():
        name = r.get("name", "(unnamed)")
        tags = r.get("tags", "")
        html = f"""
        <div style='font-size:14px;'>
          <b>{name}</b><br/>
          <i>Dam/Weir/Barrage</i>
          <details style='margin-top:6px;'><summary>Tags</summary>
            <pre style='max-width:280px; white-space:pre-wrap;'>{tags}</pre>
          </details>
        </div>
        """
        folium.CircleMarker(
            location=[r.geometry.y, r.geometry.x],
            radius=5, color="#6a3d9a", fill=True, fill_opacity=0.9,
            tooltip=name, popup=folium.Popup(html, max_width=320)
        ).add_to(cluster)
fg_dams.add_to(m)

# Curated sites
for site in CURATED_IWT_SITES:
    html = f"<b>{site['name']}</b><br/>{site['type']}<br/>{site['note']}"
    folium.CircleMarker(
        location=[site["lat"], site["lon"]],
        radius=6, color="#222", fill=True, fill_color="#00bcd4", fill_opacity=0.95,
        tooltip=site["name"], popup=folium.Popup(html, max_width=280)
    ).add_to(fg_cur)
fg_cur.add_to(m)

# Reservoirs
if not res_lines.empty:
    folium.GeoJson(
        res_lines.to_json(),
        style_function=lambda _f: {
            "color": "#76b1e7", "weight": 1.2, "opacity": 0.85,
            "fillColor": "#76b1e7", "fillOpacity": 0.15
        },
        tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["Reservoir:"])
    ).add_to(fg_res)
    fg_res.add_to(m)

# Canals (only if present + desired)
if INCLUDE_CANALS and not canals.empty:
    folium.GeoJson(
        canals.to_json(),
        style_function=lambda _f: {"color": "#d95f0e", "weight": 1.2, "opacity": 0.9},
        tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["Canal:"])
    ).add_to(fg_can)
    fg_can.add_to(m)

# QoL tools
Fullscreen(position="topleft").add_to(m)
MiniMap(toggle_display=True, position="bottomright").add_to(m)
MeasureControl(position="topleft", primary_length_unit="kilometers").add_to(m)
MousePosition(position="bottomright", prefix="Lat/Lon", separator=" , ", num_digits=4).add_to(m)

# Layer control
folium.LayerControl(collapsed=False).add_to(m)

# Legend
legend_html = f"""
<div style="position: fixed; bottom: 20px; left: 20px; z-index: 9999;
            background: white; padding: 10px 12px; border: 1px solid #ccc;
            border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.25);
            font-size: 13px;">
  <div style='font-weight:600; margin-bottom:6px;'>Indus Waters Treaty – Map Legend</div>
  <div><span style='display:inline-block;width:14px;height:3px;background:{RIVER_STYLE['Indus']['color']};margin-right:6px;vertical-align:middle'></span>Western Rivers (Indus, Jhelum, Chenab)</div>
  <div><span style='display:inline-block;width:14px;height:3px;background:{RIVER_STYLE['Ravi']['color']};margin-right:6px;vertical-align:middle'></span>Eastern Rivers (Ravi, Beas, Sutlej)</div>
  <div><span style='display:inline-block;width:14px;height:3px;background:#2ca02c;margin-right:6px;vertical-align:middle'></span>Other Tributary (Kabul)</div>
  <div><span style='display:inline-block;width:10px;height:10px;border-radius:5px;background:#6a3d9a;display:inline-block;margin-right:6px;vertical-align:middle'></span>Dams / Weirs / Barrages (OSM)</div>
  <div><span style='display:inline-block;width:10px;height:10px;border-radius:5px;background:#00bcd4;display:inline-block;margin-right:6px;vertical-align:middle'></span>Key IWT Sites (Curated)</div>
  {"<div><span style='display:inline-block;width:14px;height:3px;background:#76b1e7;margin-right:6px;vertical-align:middle'></span>Reservoir outlines (OSM)</div>" if not res_lines.empty else ""}
  {"<div><span style='display:inline-block;width:14px;height:3px;background:#d95f0e;margin-right:6px;vertical-align:middle'></span>Named Canals (OSM)</div>" if (INCLUDE_CANALS and not canals.empty) else ""}
  {"<div><span style='display:inline-block;width:14px;height:3px;background:#666;margin-right:6px;vertical-align:middle'></span>Admin Outlines (NE)</div>" if (INCLUDE_ADMIN_OUTLINES and not admin0.empty) else ""}
  <div style='margin-top:6px; font-size:12px; color:#555;'>Use layer control (top-right) to toggle. Click features for details.</div>
</div>
"""
from branca.element import Element
m.get_root().html.add_child(Element(legend_html))

# Auto-zoom to available data
try:
    layers = []
    if len(ne_rivers) > 0: layers.append(ne_rivers)
    if len(dams_pts) > 0: layers.append(dams_pts)
    if len(res_lines) > 0: layers.append(res_lines)
    if INCLUDE_CANALS and len(canals) > 0: layers.append(canals)
    if INCLUDE_ADMIN_OUTLINES and len(admin0) > 0: layers.append(admin0)
    if len(kabul_fb) > 0: layers.append(kabul_fb)
    if layers:
        merged = gpd.GeoDataFrame(pd.concat(layers, ignore_index=True), geometry="geometry", crs=4326)
        minx, miny, maxx, maxy = merged.total_bounds
        m.fit_bounds([[miny, minx], [maxy, maxx]])
except Exception:
    pass

# Save
m.save(OUTPUT_HTML)
print(f"Saved: {OUTPUT_HTML}")
