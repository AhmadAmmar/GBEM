"""
IWT Indus System – Interactive Map (Folium + OSM + Natural Earth)

Creates an interactive HTML map of Indus Waters Treaty–related geography:
- Western rivers: Indus, Jhelum, Chenab
- Eastern rivers: Ravi, Beas, Sutlej
- Key tributary: Kabul (+ alt spellings), with OSM fallback
- OSM dams / weirs / barrages (name catchers for headworks etc.)
- Optional OSM reservoirs + named canals
- Optional Natural Earth Admin-0 country outlines
- Curated IWT sites layer with short notes
- Basemap choices, river “glow”, purple clusters, on-line labels,
  fullscreen/minimap/measure/mouse-pos, auto-zoom, legend

Run:
    pip install folium geopandas shapely requests pyproj rtree fiona
    python iwt_map.py
"""

from __future__ import annotations

import io
import json
import zipfile
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
import requests
from shapely.geometry import LineString, MultiLineString, Point, Polygon

# ------------------------------
# CONFIG
# ------------------------------

# Rough bbox covering the Indus basin & adjoining areas (south, west, north, east)
BBOX = (23.0, 60.0, 37.8, 80.5)

# Toggles
INCLUDE_RESERVOIRS = True
INCLUDE_CANALS = False       # Can be heavy
INCLUDE_ADMIN_OUTLINES = True

# Optional local paths if you pre-download data (leave "" to skip)
LOCAL_NE_RIVERS_ZIP = r""   # e.g., r"D:\...\ne_10m_rivers_lake_centerlines.zip"
LOCAL_NE_ADMIN0_ZIP = r""   # e.g., r"D:\...\ne_10m_admin_0_countries.zip"

# Output HTML
OUTPUT_HTML = "indus_iwt_map.html"

# Natural Earth – mirrors
NE_RIVERS_URLS = [
    "https://naciscdn.org/naturalearth/10m/physical/ne_10m_rivers_lake_centerlines.zip",
    "https://naturalearth.s3.amazonaws.com/10m_physical/ne_10m_rivers_lake_centerlines.zip",
    "https://www.naturalearthdata.com/http//www.naturalearthdata.com/download/10m/physical/ne_10m_rivers_lake_centerlines.zip",
]
NE_ADMIN0_URLS = [
    "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip",
    "https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_admin_0_countries.zip",
]

# Treaty rivers
WESTERN_RIVERS = ["Indus", "Jhelum", "Chenab"]
EASTERN_RIVERS = ["Ravi", "Beas", "Sutlej"]
OTHER_KEY_TRIBUTARIES = ["Kabul", "Kabol", "Kābul", "Cabul"]

RIVER_STYLE = {
    "Indus": {"color": "#0057e7", "weight": 3},
    "Jhelum": {"color": "#1f77b4", "weight": 3},
    "Chenab": {"color": "#1f77b4", "weight": 3},
    "Ravi": {"color": "#ff7f0e", "weight": 3},
    "Beas": {"color": "#ff7f0e", "weight": 3},
    "Sutlej": {"color": "#ff7f0e", "weight": 3},
}
OTHER_TRIB_STYLE = {"color": "#2ca02c", "weight": 3}

OVERPASS_ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]

# Optional: curated key IWT sites (lat, lon)
CURATED_IWT_SITES = [
    # Pakistan (Western)
    {"name": "Tarbela Dam (Indus)", "lat": 34.088, "lon": 72.695,
     "type": "Dam", "note": "Largest on Indus; Western Rivers."},
    {"name": "Mangla Dam (Jhelum)", "lat": 33.148, "lon": 73.643,
     "type": "Dam", "note": "Major storage on Western river."},
    {"name": "Chashma Barrage (Indus)", "lat": 32.433, "lon": 71.383,
     "type": "Barrage", "note": "Indus control + canal offtakes."},
    {"name": "Taunsa Barrage (Indus)", "lat": 30.705, "lon": 70.848,
     "type": "Barrage", "note": "Indus irrigation control."},
    {"name": "Guddu Barrage (Indus)", "lat": 28.411, "lon": 69.703,
     "type": "Barrage", "note": "Indus irrigation control."},
    {"name": "Sukkur Barrage (Indus)", "lat": 27.684, "lon": 68.852,
     "type": "Barrage", "note": "Historic Indus barrage."},
    {"name": "Kotri Barrage (Indus)", "lat": 25.380, "lon": 68.313,
     "type": "Barrage", "note": "Downstream Indus barrage."},
    {"name": "Marala Headworks (Chenab)", "lat": 32.673, "lon": 74.463,
     "type": "Headworks", "note": "Chenab offtakes."},
    {"name": "Qadirabad Headworks (Chenab)", "lat": 32.330, "lon": 73.764,
     "type": "Headworks", "note": "Chenab offtakes."},
    {"name": "Balloki Headworks (Ravi)", "lat": 31.205, "lon": 73.882,
     "type": "Headworks", "note": "Eastern; diversions."},

    # India (Eastern + Jhelum/Chenab projects)
    {"name": "Ranjit Sagar (Thein) Dam (Ravi)", "lat": 32.441, "lon": 75.705,
     "type": "Dam", "note": "Eastern river project."},
    {"name": "Harike Headworks (Sutlej-Beas)", "lat": 31.138, "lon": 74.955,
     "type": "Headworks", "note": "Sutlej–Beas confluence control."},
    {"name": "Ferozepur Headworks (Sutlej)", "lat": 30.962, "lon": 74.619,
     "type": "Headworks", "note": "Sutlej offtakes."},
    {"name": "Baglihar (Chenab)", "lat": 33.096, "lon": 75.715,
     "type": "Hydel", "note": "Run-of-river on Western river."},
    {"name": "Kishanganga (Jhelum/Nilm)", "lat": 34.535, "lon": 74.722,
     "type": "Hydel", "note": "Diversion project on Western river."},
    {"name": "Ratle (Chenab)", "lat": 33.110, "lon": 75.429,
     "type": "Hydel", "note": "Under development; Western river."},
    {"name": "Salal (Chenab)", "lat": 33.215, "lon": 74.726,
     "type": "Hydel", "note": "Run-of-river."},
    {"name": "Uri-II (Jhelum)", "lat": 34.080, "lon": 74.028,
     "type": "Hydel", "note": "Run-of-river."},
]

# ------------------------------
# HELPERS
# ------------------------------

def bbox_str() -> str:
    s, w, n, e = BBOX  # Overpass expects south,west,north,east
    return f"{s},{w},{n},{e}"

def _download_zip(urls: List[str], local_path: str = "", what: str = "") -> bytes:
    import os
    if local_path and os.path.exists(local_path):
        print(f"Loading {what} (local): {local_path}")
        with open(local_path, "rb") as f:
            return f.read()

    headers = {"User-Agent": "Mozilla/5.0 (IWT-Map/1.0)"}
    last_err = None
    for url in urls:
        try:
            print(f"Downloading {what} from: {url}")
            r = requests.get(url, headers=headers, timeout=180)
            if r.status_code == 200 and r.content:
                print(f"✓ Downloaded {what}: {url}")
                return r.content
            last_err = RuntimeError(f"Fetch failed {r.status_code} from {url}")
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"{what} download failed from all mirrors. Last error: {last_err}")

def _read_shp_from_zip_bytes(zip_bytes: bytes, shp_contains: str) -> gpd.GeoDataFrame:
    import tempfile, os
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        with tempfile.TemporaryDirectory() as tmp:
            zf.extractall(tmp)
            shp_path = None
            for root, _, files in os.walk(tmp):
                for f in files:
                    if f.endswith(".shp") and shp_contains in f:
                        shp_path = os.path.join(root, f)
                        break
            if not shp_path:
                raise RuntimeError(f"Could not find a .shp containing '{shp_contains}'")
            gdf = gpd.read_file(shp_path)
    return gdf

def download_and_read_ne_rivers() -> gpd.GeoDataFrame:
    content = _download_zip(NE_RIVERS_URLS, LOCAL_NE_RIVERS_ZIP, "Natural Earth rivers")
    gdf = _read_shp_from_zip_bytes(content, "rivers_lake_centerlines")
    south, west, north, east = BBOX
    bbox_poly = Polygon([(west, south), (east, south), (east, north), (west, north)])
    gdf = gdf.to_crs(4326)
    gdf = gdf[gdf.geometry.intersects(bbox_poly)]
    keep = set(WESTERN_RIVERS + EASTERN_RIVERS + OTHER_KEY_TRIBUTARIES + ["Sindhu"])
    name_col = next((c for c in ("name", "name_en", "name_ru", "name_de") if c in gdf.columns), None)
    if name_col:
        gdf = gdf[gdf[name_col].isin(keep)].rename(columns={name_col: "name"})
    else:
        gdf["name"] = "(unnamed)"
    return gdf[["name", "geometry"]]

def download_and_read_ne_admin0() -> gpd.GeoDataFrame:
    content = _download_zip(NE_ADMIN0_URLS, LOCAL_NE_ADMIN0_ZIP, "NE Admin-0 countries")
    gdf = _read_shp_from_zip_bytes(content, "admin_0_countries")
    south, west, north, east = BBOX
    bbox_poly = Polygon([(west, south), (east, south), (east, north), (west, north)])
    gdf = gdf.to_crs(4326)
    gdf = gdf[gdf.geometry.intersects(bbox_poly)]
    return gdf[["ADMIN", "geometry"]]

def overpass_query(query: str) -> Dict:
    last_err = None
    for ep in OVERPASS_ENDPOINTS:
        try:
            resp = requests.post(ep, data={"data": query}, timeout=300,
                                 headers={"User-Agent": "Mozilla/5.0 (IWT-Map/1.0)"})
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"All Overpass endpoints failed. Last error: {last_err}")

def elements_to_point_gdf(elements: List[Dict], feature_type: str) -> gpd.GeoDataFrame:
    rows = []
    for el in elements:
        osm_type = el.get("type")
        osm_id = el.get("id")
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("alt_name") or "(unnamed)"
        if osm_type == "node":
            lat, lon = el.get("lat"), el.get("lon")
            if lat is None or lon is None:
                continue
            geom = Point(lon, lat)
        else:
            coords = el.get("geometry")
            if not coords:
                continue
            line = LineString([(c["lon"], c["lat"]) for c in coords])
            geom = line.centroid
        rows.append({
            "name": name,
            "feature_type": feature_type,
            "osm_type": osm_type,
            "osm_id": osm_id,
            "source": "OSM Overpass",
            "tags": json.dumps(tags, ensure_ascii=False),
            "geometry": geom,
        })
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=4326) if rows else gpd.GeoDataFrame(
        columns=["name", "feature_type", "osm_type", "osm_id", "source", "tags", "geometry"], crs=4326
    )

def elements_to_lines_gdf(elements: List[Dict], feature_type: str) -> gpd.GeoDataFrame:
    rows = []
    for el in elements:
        if el.get("type") not in ("way", "relation"):
            continue
        tags = el.get("tags", {})
        name = tags.get("name") or "(unnamed)"
        coords = el.get("geometry")
        if not coords:
            continue
        line = LineString([(c["lon"], c["lat"]) for c in coords])
        rows.append({"name": name, "feature_type": feature_type, "source": "OSM Overpass", "tags": json.dumps(tags, ensure_ascii=False), "geometry": line})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=4326) if rows else gpd.GeoDataFrame(
        columns=["name", "feature_type", "source", "tags", "geometry"], crs=4326
    )

# Pretty rivers
def add_river_with_glow(group, geom, color, label):
    # white halo
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
        pl = folium.PolyLine(locations=coords, opacity=0)
        group.add_child(pl)
        PolyLineTextPath(pl, text, repeat=True, offset=7,
                         attributes={'font-weight': 'bold', 'font-size': '12px'}).add_to(group)

    if isinstance(geom, LineString):
        add_one(geom)
    elif isinstance(geom, MultiLineString):
        for ls in geom.geoms:
            add_one(ls)

# ------------------------------
# FETCH DATA
# ------------------------------

print("Downloading Natural Earth rivers...")
ne_rivers = download_and_read_ne_rivers()

rivers_west = ne_rivers[ne_rivers["name"].isin(WESTERN_RIVERS)]
rivers_east = ne_rivers[ne_rivers["name"].isin(EASTERN_RIVERS)]
rivers_other = ne_rivers[ne_rivers["name"].isin(OTHER_KEY_TRIBUTARIES)]

print("Querying OSM for dams/barrages/weirs...")
q_dams = """
[out:json][timeout:300];
(
  nwr["man_made"="dam"]({bbox});
  nwr["man_made"="weir"]({bbox});
  nwr["waterway"="weir"]({bbox});
  nwr["waterway"="dam"]({bbox});
  nwr["dam:type"="barrage"]({bbox});
  // name catchers for inconsistent tagging
  nwr["name"~"Barrage|Headworks|Head Works|Head-Works",i]({bbox});
  nwr["name"~"Tarbela|Mangla|Baglihar|Kishanganga|Ratle|Guddu|Sukkur|Kotri|Taunsa|Chashma|Qadirabad|Marala|Balloki|Ferozepur|Harike",i]({bbox});
);
out body geom;
""".format(bbox=bbox_str())
dams_pts = elements_to_point_gdf(overpass_query(q_dams).get("elements", []), "Dam/Weir/Barrage")
print("Dams/Weirs/Barrages:", len(dams_pts))

if INCLUDE_RESERVOIRS:
    print("Querying OSM for reservoirs...")
    q_res = """
[out:json][timeout:300];
(
  nwr["natural"="water"]["water"="reservoir"]({bbox});
  nwr["landuse"="reservoir"]({bbox});
);
out body geom;
""".format(bbox=bbox_str())
    res_polylines = elements_to_lines_gdf(overpass_query(q_res).get("elements", []), "Reservoir")
    print("Reservoir outlines:", len(res_polylines))
else:
    res_polylines = gpd.GeoDataFrame(columns=["name","feature_type","source","tags","geometry"], crs=4326)

if INCLUDE_CANALS:
    print("Querying OSM for named canals (heavy)…")
    q_canals = """
[out:json][timeout:300];
(
  way["waterway"="canal"]["name"]({bbox});
  relation["waterway"="canal"]["name"]({bbox});
);
out body geom;
""".format(bbox=bbox_str())
    canals = elements_to_lines_gdf(overpass_query(q_canals).get("elements", []), "Canal")
    print("Named canals:", len(canals))
else:
    canals = gpd.GeoDataFrame(columns=["name","feature_type","source","tags","geometry"], crs=4326)

# Kabul fallback (if NE didn’t have it)
kabul_fallback = None
if rivers_other.empty:
    print("Fetching Kabul River via OSM fallback…")
    q_kabul = """
[out:json][timeout:180];
( way["waterway"="river"]["name"~"Kabul|Kabol|Kābul|Cabul",i]({bbox}); );
out body geom;
""".format(bbox=bbox_str())
    kabul_fallback = elements_to_lines_gdf(overpass_query(q_kabul).get("elements", []), "River (OSM)")
    print("Kabul fallback lines:", len(kabul_fallback))

# Optional admin outlines
if INCLUDE_ADMIN_OUTLINES:
    print("Downloading Admin-0 outlines…")
    admin0 = download_and_read_ne_admin0()
else:
    admin0 = gpd.GeoDataFrame(columns=["ADMIN", "geometry"], crs=4326)

# ------------------------------
# BUILD MAP
# ------------------------------

m = folium.Map(location=[29.5, 70.5], zoom_start=6, tiles="CartoDB positron", control_scale=True)

# Basemap choices
folium.TileLayer("CartoDB positron", name="Positron").add_to(m)
folium.TileLayer("CartoDB dark_matter", name="Dark").add_to(m)
folium.TileLayer(
    tiles="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    name="OpenTopoMap",
    attr="© OpenTopoMap, SRTM"
).add_to(m)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    name="ESRI Imagery",
    attr="Tiles © Esri"
).add_to(m)

# Feature groups
fg_admin = folium.FeatureGroup(name="Admin Outlines (NE)", show=False)
fg_west  = folium.FeatureGroup(name="Western Rivers (IWT)", show=True)
fg_east  = folium.FeatureGroup(name="Eastern Rivers (IWT)", show=True)
fg_other = folium.FeatureGroup(name="Other Key Tributaries", show=True)
fg_dams  = folium.FeatureGroup(name="Dams / Weirs / Barrages (OSM)", show=True)
fg_res   = folium.FeatureGroup(name="Reservoirs (OSM)", show=False)
fg_canals= folium.FeatureGroup(name="Named Canals (OSM)", show=False)
fg_cur   = folium.FeatureGroup(name="Key IWT Sites (Curated)", show=True)

# Admin outlines
if not admin0.empty:
    folium.GeoJson(
        admin0.to_json(),
        style_function=lambda _f: {"color":"#666", "weight":1, "opacity":0.8, "fillOpacity":0}
    ).add_to(fg_admin)
    fg_admin.add_to(m)

# Rivers with glow + labels
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
elif kabul_fallback is not None and not kabul_fallback.empty:
    folium.GeoJson(
        kabul_fallback.to_json(),
        style_function=lambda _f: OTHER_TRIB_STYLE,
        tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["River:"])
    ).add_to(fg_other)

fg_west.add_to(m); fg_east.add_to(m); fg_other.add_to(m)

# Purple cluster style (matches legend)
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

# Dams/Weirs/Barrages clustered
cluster = MarkerCluster(icon_create_function=icon_create_function).add_to(fg_dams)
for _, r in dams_pts.iterrows():
    name = r["name"]
    url = f"https://www.openstreetmap.org/{r['osm_type']}/{r['osm_id']}" if r["osm_type"] in ("node","way","relation") else None
    html = f"""
    <div style='font-size:14px;'>
      <b>{name}</b><br/>
      <i>{r['feature_type']}</i><br/>
      Source: {r['source']}<br/>{f"<a href='{url}' target='_blank'>Open in OSM</a>" if url else ""}
      <details style='margin-top:6px;'><summary>Tags</summary>
        <pre style='max-width:280px; white-space:pre-wrap;'>{r['tags']}</pre>
      </details>
    </div>
    """
    folium.CircleMarker(
        location=[r.geometry.y, r.geometry.x],
        radius=5, color="#6a3d9a", fill=True, fill_opacity=0.9,
        tooltip=name, popup=folium.Popup(html, max_width=320)
    ).add_to(cluster)
fg_dams.add_to(m)

# Curated IWT sites (distinct color)
for site in CURATED_IWT_SITES:
    html = f"<b>{site['name']}</b><br/>{site['type']}<br/>{site['note']}"
    folium.CircleMarker(
        location=[site["lat"], site["lon"]],
        radius=6, color="#222", fill=True, fill_color="#00bcd4", fill_opacity=0.95,
        tooltip=site["name"], popup=folium.Popup(html, max_width=280)
    ).add_to(fg_cur)
fg_cur.add_to(m)

# Reservoirs (soft outline + faint fill)
if not res_polylines.empty:
    folium.GeoJson(
        res_polylines.to_json(),
        name="Reservoirs",
        style_function=lambda _f: {
            "color": "#76b1e7", "weight": 1.2, "opacity": 0.85,
            "fillColor": "#76b1e7", "fillOpacity": 0.15
        },
        tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["Reservoir:"])
    ).add_to(fg_res)
    fg_res.add_to(m)

# Canals
if not canals.empty:
    folium.GeoJson(
        canals.to_json(),
        name="Canals",
        style_function=lambda _f: {"color": "#d95f0e", "weight": 1.2, "opacity": 0.9},
        tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["Canal:"])
    ).add_to(fg_canals)
    fg_canals.add_to(m)

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
  {"<div><span style='display:inline-block;width:14px;height:3px;background:#76b1e7;margin-right:6px;vertical-align:middle'></span>Reservoir outlines (OSM)</div>" if INCLUDE_RESERVOIRS else ""}
  {"<div><span style='display:inline-block;width:14px;height:3px;background:#d95f0e;margin-right:6px;vertical-align:middle'></span>Named Canals (OSM)</div>" if INCLUDE_CANALS else ""}
  {"<div><span style='display:inline-block;width:14px;height:3px;background:#666;margin-right:6px;vertical-align:middle'></span>Admin Outlines (NE)</div>" if INCLUDE_ADMIN_OUTLINES else ""}
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
    if len(res_polylines) > 0: layers.append(res_polylines)
    if len(canals) > 0: layers.append(canals)
    if len(admin0) > 0: layers.append(admin0)
    if layers:
        merged = gpd.GeoDataFrame(pd.concat(layers, ignore_index=True),
                                  geometry="geometry", crs=4326)
        minx, miny, maxx, maxy = merged.total_bounds
        m.fit_bounds([[miny, minx], [maxy, maxx]])
except Exception:
    pass

# Save
m.save(OUTPUT_HTML)
print(f"Saved: {OUTPUT_HTML}")
