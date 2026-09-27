# iwt_map_offline_auto.py
from __future__ import annotations
import os, json, html
import geopandas as gpd
import pandas as pd
import folium
from folium.plugins import (
    MarkerCluster, PolyLineTextPath, Fullscreen, MiniMap, MeasureControl, MousePosition
)
from shapely.geometry import LineString, MultiLineString

SCRIPT_DIR = os.path.dirname(__file__)
DATA_DIR   = os.path.join(SCRIPT_DIR, "data_iwt_assets")
MANIFEST   = os.path.join(DATA_DIR, "manifest.json")
CURATED_GJ = os.path.join(DATA_DIR, "curated", "curated_sites.geojson")
OUTPUT_HTML = "indus_iwt_map.html"

LABELS_VISIBLE_FROM_ZOOM = 8
INCLUDE_ADMIN_OUTLINES = True
INCLUDE_CANALS = False

WESTERN_RIVERS = ["Indus","Jhelum","Chenab"]
EASTERN_RIVERS = ["Ravi","Beas","Sutlej"]
OTHER_KEY_TRIBUTARIES = ["Kabul","Kabol","Kābul","Cabul"]
RIVER_STYLE = {
    "Indus":{"color":"#0057e7","weight":3},"Jhelum":{"color":"#1f77b4","weight":3},
    "Chenab":{"color":"#1f77b4","weight":3},"Ravi":{"color":"#ff7f0e","weight":3},
    "Beas":{"color":"#ff7f0e","weight":3},"Sutlej":{"color":"#ff7f0e","weight":3}
}
OTHER_TRIB_STYLE={"color":"#2ca02c","weight":3}

def safe_read(p):
    if p and os.path.exists(p): return gpd.read_file(p).to_crs(4326)
    return gpd.GeoDataFrame(geometry=[], crs=4326)

def add_river_with_glow(group, geom, color, label):
    folium.GeoJson(geom.__geo_interface__, style_function=lambda _f: {"color":"#fff","weight":7,"opacity":0.65}).add_to(group)
    folium.GeoJson(geom.__geo_interface__, style_function=lambda _f, c=color: {"color":c,"weight":3,"opacity":0.95},
                   tooltip=folium.Tooltip(label), popup=folium.Popup(f"<b>{label}</b>")).add_to(group)

def add_line_label(group, geom, text):
    def add_one(ls: LineString):
        coords = [(y, x) for x, y in list(ls.coords)]
        carrier = folium.PolyLine(locations=coords, opacity=0); group.add_child(carrier)
        PolyLineTextPath(carrier, text, repeat=True, offset=7,
                         attributes={'font-weight':'bold','font-size':'12px'}).add_to(group)
    if isinstance(geom, LineString): add_one(geom)
    elif isinstance(geom, MultiLineString):
        for ls in geom.geoms: add_one(ls)

# Load manifest
if not os.path.exists(MANIFEST): raise FileNotFoundError("Run iwt_fetch_assets.py first.")
with open(MANIFEST, "r", encoding="utf-8") as f: manifest = json.load(f)

# Paths
rivers_path = manifest["ne_filtered_rivers"]
admin_path  = manifest.get("ne_admin0_bbox")
dams_pts_path  = manifest.get("osm_dams_points")
res_lines_path = manifest.get("osm_reservoirs_lines")
canals_path    = manifest.get("osm_canals_lines")
kabul_fb_path  = manifest.get("osm_kabul_lines")

# Data
ne_rivers = safe_read(rivers_path)
admin0    = safe_read(admin_path)
dams_pts  = safe_read(dams_pts_path)  # (optional: show raw layer too)
res_lines = safe_read(res_lines_path)
canals    = safe_read(canals_path)
kabul_fb  = safe_read(kabul_fb_path)
curated   = safe_read(CURATED_GJ)

rivers_west  = ne_rivers[ne_rivers["name"].isin(WESTERN_RIVERS)]
rivers_east  = ne_rivers[ne_rivers["name"].isin(EASTERN_RIVERS)]
rivers_other = ne_rivers[ne_rivers["name"].isin(OTHER_KEY_TRIBUTARIES)]

# Map
m = folium.Map(location=[29.5,70.5], zoom_start=6, tiles="CartoDB dark_matter", control_scale=True)
for tl in [
    ("CartoDB positron","CartoDB positron"),
    ("CartoDB dark_matter","CartoDB dark_matter"),
    ("OpenTopoMap","https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png","© OpenTopoMap, SRTM"),
    ("ESRI Imagery","https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}","Tiles © Esri"),
]:
    if len(tl)==2: folium.TileLayer(tl[0], name=tl[0]).add_to(m)
    else: folium.TileLayer(tiles=tl[1], name=tl[0], attr=tl[2]).add_to(m)

# Groups
fg_admin=folium.FeatureGroup(name="Admin Outlines (NE)", show=False).add_to(m)
fg_west=folium.FeatureGroup(name="Western Rivers (IWT)", show=True).add_to(m)
fg_east=folium.FeatureGroup(name="Eastern Rivers (IWT)", show=True).add_to(m)
fg_other=folium.FeatureGroup(name="Other Key Tributaries", show=True).add_to(m)
fg_dams=folium.FeatureGroup(name="Dams / Weirs / Barrages (OSM)", show=False).add_to(m)  # raw (optional)
fg_res=folium.FeatureGroup(name="Reservoirs (OSM)", show=False).add_to(m)
fg_can=folium.FeatureGroup(name="Named Canals (OSM)", show=False).add_to(m)
fg_cur=folium.FeatureGroup(name="Key Sites (Auto-curated)", show=True).add_to(m)
fg_lbl=folium.FeatureGroup(name="Labels (Auto-curated + OSM)", show=True).add_to(m)

# Admin
if INCLUDE_ADMIN_OUTLINES and not admin0.empty:
    folium.GeoJson(admin0.to_json(), style_function=lambda _f: {"color":"#666","weight":1,"opacity":0.8,"fillOpacity":0}).add_to(fg_admin)

# Rivers
for _, r in rivers_west.iterrows():
    col=RIVER_STYLE.get(r["name"],{"color":"#2b8cbe"})["color"]
    add_river_with_glow(fg_west, r["geometry"], col, f"{r['name']} (Western)")
    add_line_label(fg_west, r["geometry"], f"  {r['name'].upper()}  ▸  ")
for _, r in rivers_east.iterrows():
    col=RIVER_STYLE.get(r["name"],{"color":"#fdae61"})["color"]
    add_river_with_glow(fg_east, r["geometry"], col, f"{r['name']} (Eastern)")
    add_line_label(fg_east, r["geometry"], f"  {r['name'].upper()}  ▸  ")
if not rivers_other.empty:
    for _, r in rivers_other.iterrows():
        add_river_with_glow(fg_other, r["geometry"], OTHER_TRIB_STYLE["color"], r["name"])
        add_line_label(fg_other, r["geometry"], f"  {r['name'].upper()}  ▸  ")
elif not kabul_fb.empty:
    folium.GeoJson(kabul_fb.to_json(), style_function=lambda _f: OTHER_TRIB_STYLE,
                   tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["River:"])).add_to(fg_other)

# Optional raw OSM layer (so you can compare)
if not dams_pts.empty:
    from folium.plugins import MarkerCluster
    from branca.element import Element
    m.get_root().header.add_child(Element("<style>.marker-cluster-purple div{background:rgba(106,61,154,0.70);} .marker-cluster-purple span{color:#fff;font-weight:600;}</style>"))
    icon_create_function = """
    function(cluster){
      var n=cluster.getChildCount(), size = n<50?'small':(n<200?'medium':'large');
      return new L.DivIcon({html:'<div><span>'+n+'</span></div>', className:'marker-cluster marker-cluster-purple marker-cluster-'+size, iconSize:new L.Point(40,40)});
    }"""
    cluster = MarkerCluster(icon_create_function=icon_create_function).add_to(fg_dams)
    for _, r in dams_pts.iterrows():
        nm = r.get("name","(unnamed)")
        folium.CircleMarker([r.geometry.y, r.geometry.x], radius=4, color="#6a3d9a", fill=True, fill_opacity=0.9,
                            tooltip=nm, popup=folium.Popup(html.escape(nm), max_width=280)).add_to(cluster)

# Auto-curated sites (deduped + ranked)
if not curated.empty:
    for _, s in curated.iterrows():
        nm = s["name"]; kind = s.get("kind","Site"); sc = int(s.get("score",0)); dd = int(s.get("dedup_count",1))
        html_popup = f"<b>{html.escape(str(nm))}</b><br/>{html.escape(kind)}<br/><small>score:{sc}  dedup:{dd}</small>"
        folium.CircleMarker([s.geometry.y, s.geometry.x], radius=6, color="#222", fill=True, fill_color="#00bcd4", fill_opacity=0.95,
                            tooltip=nm, popup=folium.Popup(html_popup, max_width=300)).add_to(fg_cur)
        folium.Marker(
            [s.geometry.y, s.geometry.x],
            icon=folium.DivIcon(html=f"<div class='poi-label curated'>{html.escape(str(nm))}</div>")
        ).add_to(fg_lbl)

# Reservoirs / canals
if not res_lines.empty:
    folium.GeoJson(res_lines.to_json(), style_function=lambda _f: {"color":"#76b1e7","weight":1.2,"opacity":0.85,"fillColor":"#76b1e7","fillOpacity":0.15},
                   tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["Reservoir:"])).add_to(fg_res)
if INCLUDE_CANALS and not canals.empty:
    folium.GeoJson(canals.to_json(), style_function=lambda _f: {"color":"#d95f0e","weight":1.2,"opacity":0.9},
                   tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["Canal:"])).add_to(fg_can)

# QoL
from branca.element import Element, MacroElement
folium.LayerControl(collapsed=False).add_to(m)
from jinja2 import Template
style_css = """
<style>
.poi-label{font:12px/1.0 Arial,sans-serif;color:#eaeaea;text-shadow:-1px -1px 0 #000,1px -1px 0 #000,-1px 1px 0 #000,1px 1px 0 #000;white-space:nowrap;}
.poi-label.curated{color:#00bcd4;}
</style>"""
m.get_root().header.add_child(Element(style_css))
from folium.plugins import Fullscreen, MiniMap, MeasureControl, MousePosition
Fullscreen(position="topleft").add_to(m)
MiniMap(toggle_display=True, position="bottomright").add_to(m)
MeasureControl(position="topleft", primary_length_unit="kilometers").add_to(m)
MousePosition(position="bottomright", prefix="Lat/Lon", separator=" , ", num_digits=4).add_to(m)

# Zoom-gated label visibility
class BindZoomLabels(MacroElement):
    def __init__(self, zoom:int):
        super().__init__(); self.zoom=zoom
        self._template = Template("""
        {% macro script(this, kwargs) %}
        var map = {{this._parent.get_name()}};
        function _updateLabels(){
          var show = map.getZoom() >= {{this.zoom}};
          var els = document.getElementsByClassName('poi-label');
          for (var i=0;i<els.length;i++){ els[i].style.display = show ? 'block' : 'none'; }
        }
        map.on('zoomend', _updateLabels); _updateLabels();
        {% endmacro %}
        """)
BindZoomLabels(LABELS_VISIBLE_FROM_ZOOM).add_to(m)

# Fit bounds
try:
    layers=[]
    for g in (ne_rivers, curated, res_lines, canals, admin0, kabul_fb):
        if len(g)>0: layers.append(g)
    if layers:
        merged = gpd.GeoDataFrame(pd.concat(layers, ignore_index=True), geometry="geometry", crs=4326)
        minx,miny,maxx,maxy = merged.total_bounds
        m.fit_bounds([[miny,minx],[maxy,maxx]])
except Exception: pass

m.save(OUTPUT_HTML); print(f"Saved: {OUTPUT_HTML}")
