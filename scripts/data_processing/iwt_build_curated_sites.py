from __future__ import annotations
import os, json, re, warnings
from typing import Dict, List, Tuple

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from shapely.ops import unary_union

# Optional helpers
try:
    from unidecode import unidecode
except Exception:
    def unidecode(x): return x

try:
    from rapidfuzz.fuzz import token_set_ratio
    HAVE_FUZZ = True
except Exception:
    HAVE_FUZZ = False

# -------------------------
# Paths
# -------------------------
SCRIPT_DIR = os.path.dirname(__file__)
DATA_DIR   = os.path.join(SCRIPT_DIR, "data_iwt_assets")
MANIFEST   = os.path.join(DATA_DIR, "manifest.json")
OUT_DIR    = os.path.join(DATA_DIR, "curated")
os.makedirs(OUT_DIR, exist_ok=True)

# -------------------------
# Load
# -------------------------
def safe_read(p):
    if p and os.path.exists(p):
        return gpd.read_file(p).to_crs(4326)
    return gpd.GeoDataFrame(geometry=[], crs=4326)

if not os.path.exists(MANIFEST):
    raise FileNotFoundError("manifest.json not found; run iwt_fetch_assets.py first.")

with open(MANIFEST, "r", encoding="utf-8") as f:
    manifest = json.load(f)

rivers_path    = manifest["ne_filtered_rivers"]
res_lines_path = manifest.get("osm_reservoirs_lines")
kabul_fb_path  = manifest.get("osm_kabul_lines")
dams_pts_path  = manifest.get("osm_dams_points")

ne_riv   = safe_read(rivers_path)
res_lines= safe_read(res_lines_path)
kabul_fb = safe_read(kabul_fb_path)
osm_pts  = safe_read(dams_pts_path)

if osm_pts.empty:
    raise RuntimeError("No OSM dams/weirs/barrages points found. Run the fetcher first.")

# -------------------------
# Name & tag hygiene
# -------------------------
POS_KEYS = {"dam","barrage","headworks","head works","weir","hydel","power","power station","power plant","project","reservoir"}
NEG_KEYS = {"road","rd","bridge","flyover","service area","office","authority","colony","society","gate","park","market","masjid","school","university","hospital"}

NAME_CLEAN_RX = re.compile(r"\b(dam|barrage|head\s*works?|weir|hydel|power\s*(station|plant)?|project|reservoir)\b", re.I)

def parse_tags(val) -> Dict:
    if isinstance(val, dict): return val
    if isinstance(val, str):
        try: return json.loads(val)
        except Exception: return {}
    return {}

def best_name(tags: Dict, fallback: str) -> str:
    # try English/romanized first
    for k in ("name:en","official_name:en","alt_name:en","short_name:en","int_name"):
        if tags.get(k): return str(tags[k])
    # then generic name/official/alt
    for k in ("name","official_name","alt_name","short_name"):
        if tags.get(k): return str(tags[k])
    return fallback or ""

def normalize_name(n: str) -> str:
    if not n: return ""
    n = unidecode(n)  # transliterate Urdu/Arabic etc.
    n = NAME_CLEAN_RX.sub("", n.lower())
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n

def looks_positive(name: str, tags: Dict) -> bool:
    nlow = (unidecode(name) or "").lower()
    if any(k in nlow for k in POS_KEYS): return True
    if tags.get("dam:type") == "barrage": return True
    if tags.get("man_made") in ("dam","weir"): return True
    if tags.get("waterway") in ("dam","weir"): return True
    if "generator:output:electricity" in tags or "plant:output:electricity" in tags: return True
    return False

def looks_noise(name: str, tags: Dict) -> bool:
    nlow = (unidecode(name) or "").lower()
    if any(k in nlow for k in NEG_KEYS): return True
    if tags.get("highway"): return True
    if tags.get("bridge") == "yes": return True
    return False

# -------------------------
# Build a water buffer (5 km) to keep only near-water features
# -------------------------
def build_water_buffer(meters=5000):
    pieces = []
    for g in (ne_riv, res_lines, kabul_fb):
        if len(g) > 0: pieces.append(g)
    if not pieces: return None
    allg = gpd.GeoDataFrame(pd.concat(pieces, ignore_index=True), geometry="geometry", crs=4326)
    allg_3857 = allg.to_crs(3857)
    buff = allg_3857.buffer(meters).unary_union
    return gpd.GeoDataFrame(geometry=[buff], crs=3857).to_crs(4326)

water_buf = build_water_buffer(5000)

# -------------------------
# Candidate filtering
# -------------------------
df = osm_pts.copy()
df["tags_dict"] = df["tags"].apply(parse_tags)
df["name_best"] = [best_name(t, nm) for t, nm in zip(df["tags_dict"], df.get("name",""))]

# drop empty names after transliteration
df["name_best"] = df["name_best"].fillna("")
df = df[df["name_best"] != ""]

# remove obvious noise by name/tags
df = df[[not looks_noise(n, t) for n, t in zip(df["name_best"], df["tags_dict"])]]

# keep positives (by tags/keywords) OR (near water)
mask_pos = pd.Series([looks_positive(n, t) for n, t in zip(df["name_best"], df["tags_dict"])], index=df.index)
if water_buf is not None:
    joined = gpd.sjoin(df, water_buf, how="left", predicate="intersects")
    near_water = ~joined["index_right"].isna()
    df = df[mask_pos | near_water]
else:
    df = df[mask_pos]

if df.empty:
    warnings.warn("After filtering, no candidates remained. Relax filters?")
    out = gpd.GeoDataFrame(columns=["name","kind","score","dedup_count","geometry"], crs=4326)
    out.to_file(os.path.join(OUT_DIR, "curated_sites.geojson"), driver="GeoJSON")
    print("Saved curated_sites.geojson (empty).")
    raise SystemExit

# -------------------------
# Deduplicate by name + proximity
# -------------------------
def classify_kind(name: str, tags: Dict) -> str:
    n = (unidecode(name) or "").lower()
    if tags.get("dam:type") == "barrage" or "barrage" in n or "headworks" in n or "head works" in n:
        return "Barrage/Headworks"
    if "weir" in n or tags.get("man_made") == "weir" or tags.get("waterway") == "weir":
        return "Weir"
    if "dam" in n or tags.get("man_made") == "dam" or tags.get("waterway") == "dam":
        return "Dam"
    if "hydel" in n or "power" in n:
        return "Hydel"
    return "Dam/Weir/Barrage"

def feature_score(tags: Dict, osm_type: str, kind: str) -> int:
    s = 0
    if kind == "Barrage/Headworks": s += 12
    if kind == "Dam": s += 10
    if kind == "Hydel": s += 8
    if kind == "Weir": s += 6
    if tags.get("wikidata"): s += 5
    if tags.get("wikipedia"): s += 4
    if "height" in tags or "reservoir:capacity" in tags: s += 3
    s += {"relation":3, "way":2, "node":1}.get(osm_type, 0)
    return s

def groups_by_name(df: gpd.GeoDataFrame) -> Dict[str, pd.Index]:
    # normalized (transliterated) names for grouping
    norm = df["name_best"].apply(normalize_name)
    # Fallback: if empty after normalization, fall back to original transliterated
    norm = norm.mask(norm == "", df["name_best"].apply(lambda x: unidecode(x).lower()))
    df = df.assign(norm_name=norm)
    # Optional fuzzy merge: map near-identical names together
    if HAVE_FUZZ:
        names = df["norm_name"].unique().tolist()
        parent = {n: n for n in names}
        for i, a in enumerate(names):
            for b in names[i+1:]:
                if token_set_ratio(a, b) >= 90:
                    parent[b] = parent[a]
        df["norm_name"] = df["norm_name"].map(parent)
    return {k: v.index for k, v in df.groupby("norm_name")}

def dedupe(df0: gpd.GeoDataFrame, distance_m=800) -> gpd.GeoDataFrame:
    if df0.empty: return df0
    df0 = df0.copy()
    df0["kind"] = [classify_kind(n, t) for n, t in zip(df0["name_best"], df0["tags_dict"])]
    df0["score"] = [feature_score(t, df0.get("osm_type","node").iloc[i] if "osm_type" in df0 else "node", k)
                    for i, (t, k) in enumerate(zip(df0["tags_dict"], df0["kind"]))]

    gmap = groups_by_name(df0)
    out_rows = []
    for _, idx in gmap.items():
        g = df0.loc[idx]
        # cluster by proximity in meters
        g3857 = g.to_crs(3857)
        buffers = g3857.buffer(distance_m)
        clusters = gpd.GeoSeries(buffers.unary_union, crs=3857).explode(index_parts=False)
        clusters = gpd.GeoDataFrame(geometry=clusters, crs=3857).reset_index(drop=True)
        joined = gpd.sjoin(g3857, clusters, how="left", predicate="intersects").rename(columns={"index_right":"cluster_id"})
        for cid, sub in joined.groupby("cluster_id"):
            orig = g.loc[sub.index]
            best_idx = orig["score"].idxmax()
            best = orig.loc[best_idx].copy()
            centroid = unary_union(list(sub.geometry)).centroid
            centroid4326 = gpd.GeoSeries([centroid], crs=3857).to_crs(4326).iloc[0]
            out_rows.append({
                "name": best["name_best"],
                "kind": best["kind"],
                "score": int(best["score"]),
                "dedup_count": int(len(sub)),
                "tags": json.dumps(best["tags_dict"], ensure_ascii=False),
                "geometry": Point(centroid4326.x, centroid4326.y),
            })
    return gpd.GeoDataFrame(out_rows, geometry="geometry", crs=4326)

curated = dedupe(df, distance_m=800)

# Rank for labeling
if not curated.empty:
    curated["label_rank"] = (-curated["score"]).rank(method="dense").astype(int)
    curated = curated.sort_values(["score","dedup_count"], ascending=[False, False])

# Save
out_path = os.path.join(OUT_DIR, "curated_sites.geojson")
curated[["name","kind","score","dedup_count","label_rank","tags","geometry"]].to_file(out_path, driver="GeoJSON")
print(f"Saved curated sites: {len(curated)} → {out_path}")
