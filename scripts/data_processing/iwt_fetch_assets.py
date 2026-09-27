"""
Step 1 — Fetch & Save All IWT Datasets (no mapping)

What this script does (one-time prep):
- Downloads Natural Earth 10m "rivers & lake centerlines" and Admin-0 countries
- Filters them to the Indus bbox and saves as GeoJSON (keeps raw ZIPs too)
- Queries OSM Overpass for:
    * Dams / weirs / barrages  → points (centroids) + lines (where available)
    * Reservoir outlines       → lines (from ways/relations)
    * (optional) Named canals  → lines
    * Kabul River fallback     → lines (if needed)
- Writes everything to a folder with a manifest.json describing file counts/paths

Run (once):
    pip install geopandas shapely requests pandas fiona pyproj rtree
    python iwt_fetch_assets.py
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from typing import Dict, List, Tuple

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import LineString, MultiLineString, Point, Polygon

# ------------------------------
# CONFIG
# ------------------------------

# Target bbox covering (south, west, north, east)
BBOX: Tuple[float, float, float, float] = (23.0, 60.0, 37.8, 80.5)

# Where to save everything
DATA_DIR = os.path.join(os.path.dirname(__file__), "data_iwt_assets")

# Toggle heavy layer
INCLUDE_CANALS = False

# Overwrite existing files? (If False, existing files are skipped)
OVERWRITE = False

# Natural Earth mirrors
NE_RIVERS_URLS = [
    "https://naciscdn.org/naturalearth/10m/physical/ne_10m_rivers_lake_centerlines.zip",
    "https://naturalearth.s3.amazonaws.com/10m_physical/ne_10m_rivers_lake_centerlines.zip",
    "https://www.naturalearthdata.com/http//www.naturalearthdata.com/download/10m/physical/ne_10m_rivers_lake_centerlines.zip",
]
NE_ADMIN0_URLS = [
    "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip",
    "https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_admin_0_countries.zip",
]

# Treaty river name sets (for filtering NE rivers quickly)
WESTERN_RIVERS = ["Indus", "Jhelum", "Chenab"]
EASTERN_RIVERS = ["Ravi", "Beas", "Sutlej"]
OTHER_KEY_TRIBUTARIES = ["Kabul", "Kabol", "Kābul", "Cabul"]

# Overpass endpoints
OVERPASS_ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]

# ------------------------------
# UTILS
# ------------------------------

def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def save_bytes(path: str, content: bytes, overwrite: bool = False) -> None:
    if os.path.exists(path) and not overwrite:
        print(f"Exists, skipping: {path}")
        return
    with open(path, "wb") as f:
        f.write(content)
    print(f"Wrote: {path}")

def save_text(path: str, text: str, overwrite: bool = False) -> None:
    if os.path.exists(path) and not overwrite:
        print(f"Exists, skipping: {path}")
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Wrote: {path}")

def bbox_str() -> str:
    s, w, n, e = BBOX
    return f"{s},{w},{n},{e}"

def bbox_poly() -> Polygon:
    s, w, n, e = BBOX
    return Polygon([(w, s), (e, s), (e, n), (w, n)])

def http_get_first_ok(urls: List[str], what: str) -> bytes:
    headers = {"User-Agent": "Mozilla/5.0 (IWT-Prep/1.0)"}
    last_err = None
    for url in urls:
        try:
            print(f"Downloading {what} from: {url}")
            r = requests.get(url, headers=headers, timeout=180)
            if r.status_code == 200 and r.content:
                print(f"✓ Downloaded {what}: {url}")
                return r.content
            last_err = RuntimeError(f"{what} fetch failed {r.status_code} {url}")
        except Exception as e:
            last_err = e
    raise RuntimeError(f"All mirrors failed for {what}: {last_err}")

def read_shp_from_zip_bytes(zip_bytes: bytes, shp_contains: str) -> gpd.GeoDataFrame:
    import tempfile
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
                raise RuntimeError(f"Could not find .shp containing '{shp_contains}'")
            gdf = gpd.read_file(shp_path)
    return gdf

def overpass_query(query: str) -> Dict:
    headers = {"User-Agent": "Mozilla/5.0 (IWT-Prep/1.0)"}
    last_err = None
    for ep in OVERPASS_ENDPOINTS:
        try:
            resp = requests.post(ep, data={"data": query}, timeout=300, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Overpass failed on all endpoints: {last_err}")

def elements_to_point_gdf(elements: List[Dict], feature_type: str) -> gpd.GeoDataFrame:
    rows = []
    for el in elements:
        t = el.get("type")
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("alt_name") or "(unnamed)"
        if t == "node":
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
        rows.append({"name": name, "feature_type": feature_type, "geometry": geom, "tags": json.dumps(tags, ensure_ascii=False)})
    return gpd.GeoDataFrame(rows, crs=4326) if rows else gpd.GeoDataFrame(columns=["name","feature_type","geometry","tags"], crs=4326)

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
        rows.append({"name": name, "feature_type": feature_type, "geometry": line, "tags": json.dumps(tags, ensure_ascii=False)})
    return gpd.GeoDataFrame(rows, crs=4326) if rows else gpd.GeoDataFrame(columns=["name","feature_type","geometry","tags"], crs=4326)

def clip_to_bbox(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.empty:
        return gdf
    poly = bbox_poly()
    gdf = gdf.to_crs(4326)
    return gdf[gdf.geometry.intersects(poly)]

# ------------------------------
# TASKS
# ------------------------------

def fetch_natural_earth(manifest: dict) -> None:
    ne_dir = os.path.join(DATA_DIR, "natural_earth_raw")
    out_dir = os.path.join(DATA_DIR, "ne_filtered")
    ensure_dir(ne_dir); ensure_dir(out_dir)

    # Rivers (download raw zip, keep it, write filtered GeoJSONs)
    rivers_zip = http_get_first_ok(NE_RIVERS_URLS, "NE Rivers")
    raw_rivers_zip_path = os.path.join(ne_dir, "ne_10m_rivers_lake_centerlines.zip")
    save_bytes(raw_rivers_zip_path, rivers_zip, overwrite=OVERWRITE)

    gdf_riv = read_shp_from_zip_bytes(rivers_zip, "rivers_lake_centerlines")
    gdf_riv = clip_to_bbox(gdf_riv)
    # Filter to treaty rivers
    keep = set(WESTERN_RIVERS + EASTERN_RIVERS + OTHER_KEY_TRIBUTARIES + ["Sindhu"])
    name_col = next((c for c in ("name","name_en","name_ru","name_de") if c in gdf_riv.columns), None)
    if name_col:
        gdf_riv = gdf_riv[gdf_riv[name_col].isin(keep)].rename(columns={name_col: "name"})
    else:
        gdf_riv["name"] = "(unnamed)"

    rivers_path = os.path.join(out_dir, "ne_iwt_rivers.geojson")
    gdf_riv[["name","geometry"]].to_file(rivers_path, driver="GeoJSON")
    print(f"Saved filtered rivers: {len(gdf_riv)} → {rivers_path}")
    manifest["ne_filtered_rivers"] = rivers_path

    # Admin-0 Countries
    admin_zip = http_get_first_ok(NE_ADMIN0_URLS, "NE Admin-0")
    raw_admin_zip_path = os.path.join(ne_dir, "ne_10m_admin_0_countries.zip")
    save_bytes(raw_admin_zip_path, admin_zip, overwrite=OVERWRITE)

    gdf_admin = read_shp_from_zip_bytes(admin_zip, "admin_0_countries")
    gdf_admin = clip_to_bbox(gdf_admin)
    admin_path = os.path.join(out_dir, "ne_admin0_bbox.geojson")
    gdf_admin[["ADMIN","geometry"]].to_file(admin_path, driver="GeoJSON")
    print(f"Saved admin outlines: {len(gdf_admin)} → {admin_path}")
    manifest["ne_admin0_bbox"] = admin_path

def fetch_overpass_layers(manifest: dict) -> None:
    osm_dir = os.path.join(DATA_DIR, "osm")
    ensure_dir(osm_dir)

    # --- Dams / Weirs / Barrages
    q_dams = """
    [out:json][timeout:300];
    (
      nwr["man_made"="dam"]({bbox});
      nwr["man_made"="weir"]({bbox});
      nwr["waterway"="weir"]({bbox});
      nwr["waterway"="dam"]({bbox});
      nwr["dam:type"="barrage"]({bbox});
      nwr["name"~"Barrage|Headworks|Head Works|Head-Works",i]({bbox});
      nwr["name"~"Tarbela|Mangla|Baglihar|Kishanganga|Ratle|Guddu|Sukkur|Kotri|Taunsa|Chashma|Qadirabad|Marala|Balloki|Ferozepur|Harike",i]({bbox});
    );
    out body geom;
    """.format(bbox=bbox_str())

    dams_raw_path = os.path.join(osm_dir, "dams_weirs_barrages_raw.json")
    if not os.path.exists(dams_raw_path) or OVERWRITE:
        dj = overpass_query(q_dams)
        save_text(dams_raw_path, json.dumps(dj), overwrite=True)
    else:
        dj = json.loads(open(dams_raw_path, "r", encoding="utf-8").read())

    dams_pts = elements_to_point_gdf(dj.get("elements", []), "Dam/Weir/Barrage")
    dams_lines = elements_to_lines_gdf(dj.get("elements", []), "Dam/Weir/Barrage")

    dams_pts_path = os.path.join(osm_dir, "dams_weirs_barrages_points.geojson")
    dams_lines_path = os.path.join(osm_dir, "dams_weirs_barrages_lines.geojson")
    dams_pts.to_file(dams_pts_path, driver="GeoJSON")
    dams_lines.to_file(dams_lines_path, driver="GeoJSON")
    print(f"Saved dams/weirs/barrages: points={len(dams_pts)}, lines={len(dams_lines)}")

    manifest["osm_dams_points"] = dams_pts_path
    manifest["osm_dams_lines"]  = dams_lines_path
    manifest["osm_dams_raw"]    = dams_raw_path

    # --- Reservoirs
    q_res = """
    [out:json][timeout:300];
    (
      nwr["natural"="water"]["water"="reservoir"]({bbox});
      nwr["landuse"="reservoir"]({bbox});
    );
    out body geom;
    """.format(bbox=bbox_str())

    res_raw_path = os.path.join(osm_dir, "reservoirs_raw.json")
    if not os.path.exists(res_raw_path) or OVERWRITE:
        rj = overpass_query(q_res)
        save_text(res_raw_path, json.dumps(rj), overwrite=True)
    else:
        rj = json.loads(open(res_raw_path, "r", encoding="utf-8").read())

    res_lines = elements_to_lines_gdf(rj.get("elements", []), "Reservoir")
    res_lines_path = os.path.join(osm_dir, "reservoirs_lines.geojson")
    res_lines.to_file(res_lines_path, driver="GeoJSON")
    print(f"Saved reservoir outlines: lines={len(res_lines)}")
    manifest["osm_reservoirs_lines"] = res_lines_path
    manifest["osm_reservoirs_raw"] = res_raw_path

    # --- Canals (optional; can be heavy)
    if INCLUDE_CANALS:
        q_canals = """
        [out:json][timeout:300];
        (
          way["waterway"="canal"]["name"]({bbox});
          relation["waterway"="canal"]["name"]({bbox});
        );
        out body geom;
        """.format(bbox=bbox_str())

        canals_raw_path = os.path.join(osm_dir, "canals_raw.json")
        if not os.path.exists(canals_raw_path) or OVERWRITE:
            cj = overpass_query(q_canals)
            save_text(canals_raw_path, json.dumps(cj), overwrite=True)
        else:
            cj = json.loads(open(canals_raw_path, "r", encoding="utf-8").read())

        canals_lines = elements_to_lines_gdf(cj.get("elements", []), "Canal")
        canals_lines_path = os.path.join(osm_dir, "canals_lines.geojson")
        canals_lines.to_file(canals_lines_path, driver="GeoJSON")
        print(f"Saved named canals: lines={len(canals_lines)}")
        manifest["osm_canals_lines"] = canals_lines_path
        manifest["osm_canals_raw"] = canals_raw_path

    # --- Kabul fallback (river line), so we have it even if NE misses it
    q_kabul = """
    [out:json][timeout:180];
    ( way["waterway"="river"]["name"~"Kabul|Kabol|Kābul|Cabul",i]({bbox}); );
    out body geom;
    """.format(bbox=bbox_str())
    kabul_raw_path = os.path.join(osm_dir, "kabul_fallback_raw.json")
    if not os.path.exists(kabul_raw_path) or OVERWRITE:
        kj = overpass_query(q_kabul)
        save_text(kabul_raw_path, json.dumps(kj), overwrite=True)
    else:
        kj = json.loads(open(kabul_raw_path, "r", encoding="utf-8").read())

    kabul_lines = elements_to_lines_gdf(kj.get("elements", []), "River (OSM)")
    kabul_lines_path = os.path.join(osm_dir, "kabul_fallback_lines.geojson")
    kabul_lines.to_file(kabul_lines_path, driver="GeoJSON")
    print(f"Saved Kabul fallback lines: {len(kabul_lines)}")
    manifest["osm_kabul_lines"] = kabul_lines_path
    manifest["osm_kabul_raw"] = kabul_raw_path

# ------------------------------
# MAIN
# ------------------------------

def main():
    ensure_dir(DATA_DIR)
    manifest = {
        "bbox": {"south": BBOX[0], "west": BBOX[1], "north": BBOX[2], "east": BBOX[3]},
        "created_by": "iwt_fetch_assets.py",
        "include_canals": INCLUDE_CANALS,
    }

    # 1) Natural Earth (rivs + admin)
    fetch_natural_earth(manifest)

    # 2) OSM Overpass layers
    fetch_overpass_layers(manifest)

    # Save manifest
    manifest_path = os.path.join(DATA_DIR, "manifest.json")
    save_text(manifest_path, json.dumps(manifest, indent=2), overwrite=True)
    print("\nAll set. Manifest:", manifest_path)

if __name__ == "__main__":
    main()
