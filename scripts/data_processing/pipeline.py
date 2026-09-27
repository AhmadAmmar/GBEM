# -*- coding: utf-8 -*-
"""
Prepare 2024 EPC targets for GEE (tz-safe, CRS-safe, merge-free polygon export):
- Composite event_dt from multiple date cols (UK-first parsing, UTC, tz-stripped)
- Filter to 2024 + UPRN + XY + polygon pairing (within→nearest)
- Vectorized dedupe per (UPRN_key, poly_id): prefer top-most storey, else highest level, else latest date
- Outputs:
    1) gee_epc_2024_points_uid_wgs84.csv
    2) gee_epc_2024_polygons_uid_wgs84.zip
    3) gee_epc_2024_uid_mapping.csv
"""

from pathlib import Path
import re, uuid, zipfile
import numpy as np
import pandas as pd
import geopandas as gpd

# ------------ CONFIG ------------
EPC_IN  = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-epc\NI_Domestic_Master_to_01_2025_with_XY_v2_in_footprints.csv"
FOOT_SHP = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-buildings\Belfast_Building_Footprints.shp"

EPC_CRS = "EPSG:29902"   # Irish Grid (Pointer NI)
OUT_CRS = "EPSG:4326"    # WGS84 for GEE

# Date precedence to build composite event_dt
DATE_PRIORITY = [
    "INSPECTION_DATE",
    "LODGEMENT_DATE",
    "REGISTRATION_DATE",
    "DATE_REGISTERED",
    "DATE_OF_ASSESSMENT",
    "DATE"
]

# Storey preference fields
STOREY_FLAG_COL = "FLAT_TOP_STOREY"
LEVEL_COLS = ["FLOOR_LEVEL", "FLAT_STOREY_COUNT"]

# Outputs
OUT_DIR      = Path(EPC_IN).parent
POINTS_CSV   = OUT_DIR / "gee_epc_2024_points_uid_wgs84.csv"
POLY_DIR     = OUT_DIR / "gee_epc_2024_polygons_uid_wgs84_shp"
POLY_ZIP     = OUT_DIR / "gee_epc_2024_polygons_uid_wgs84.zip"
UID_MAP_CSV  = OUT_DIR / "gee_epc_2024_uid_mapping.csv"

# Deterministic UUIDv5 namespace
UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://ulster-epc-project/uid-2024")
# --------------------------------


# ---------- helpers ----------
def canonical_uprn(v):
    if pd.isna(v): return None
    s = str(v).strip().replace("UPRN-","").replace("uprn-","")
    s = re.sub(r"\D","", s)
    if not s: return None
    try: return str(int(s))
    except ValueError: return None

def parse_yes(val):
    if pd.isna(val): return False
    s = str(val).strip().lower()
    return s in {"y","yes","true","t","1","top","top_storey"}

def parse_datetime_utc(series: pd.Series) -> pd.Series:
    """
    UK-first parse (dayfirst=True), then fallback; parse as UTC and strip tz to naive.
    This minimizes mis-parsing UK-style dates while still catching ISO stamps.
    """
    # pass 1: UK style first
    dt = pd.to_datetime(series, errors="coerce", utc=True, dayfirst=True)
    # pass 2: fallback (non day-first) where still NaT
    mask = dt.isna() & series.notna()
    if mask.any():
        dt2 = pd.to_datetime(series[mask], errors="coerce", utc=True, dayfirst=False)
        dt = dt.copy()
        dt.loc[mask] = dt2
    return dt.dt.tz_localize(None)

def pick_event_dt(df: pd.DataFrame):
    """Build composite event_dt + source using DATE_PRIORITY."""
    event_dt = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    source   = pd.Series(pd.NA, index=df.index, dtype="object")
    for col in DATE_PRIORITY:
        if col in df.columns:
            dt = parse_datetime_utc(df[col])
            fill = event_dt.isna() & dt.notna()
            if fill.any():
                event_dt.loc[fill] = dt.loc[fill]
                source.loc[fill]   = col
    df["event_dt"] = event_dt
    df["event_dt_source"] = source.fillna("none")
    return df

def nearest_polygon(epc_gdf: gpd.GeoDataFrame, foot_gdf: gpd.GeoDataFrame, poly_id_col: str):
    """Prefer within; fallback to nearest."""
    j = gpd.sjoin(epc_gdf, foot_gdf[[poly_id_col,"geometry"]], how="left", predicate="within")
    ok = j[poly_id_col].notna()
    res = j.loc[ok, [poly_id_col]].copy()
    need = j.loc[~ok].drop(columns=[poly_id_col], errors="ignore")
    if not need.empty:
        near = gpd.sjoin_nearest(need, foot_gdf[[poly_id_col,"geometry"]], how="left", distance_col="dist_m")[[poly_id_col]]
        res = pd.concat([res, near], axis=0)
    return res.reindex(epc_gdf.index)

def write_shapefile_zipped(gdf: gpd.GeoDataFrame, out_dir: Path, out_zip: Path, layer="gee_epc_2024_polys"):
    if out_dir.exists():
        for p in out_dir.glob("*"): p.unlink()
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
    shp = out_dir / f"{layer}.shp"
    gdf.to_file(shp, driver="ESRI Shapefile")
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for ext in (".shp",".shx",".dbf",".prj",".cpg"):
            f = out_dir / f"{layer}{ext}"
            if f.exists(): zf.write(f, arcname=f.name)
    return shp, out_zip

def build_uid(up, pid, lon, lat, dt):
    lon6 = round(lon, 6)
    lat6 = round(lat, 6)
    d = "nodate" if pd.isna(dt) else pd.Timestamp(dt).strftime("%Y%m%d")
    key = f"{up or 'nouprn'}|{pid}|{lon6}|{lat6}|{d}"
    return str(uuid.uuid5(UUID_NAMESPACE, key))


# ---------- main pipeline ----------
def main():
    # Footprints
    foot = gpd.read_file(FOOT_SHP)
    if foot.crs is None:
        raise ValueError("Footprints CRS is missing; please define .prj.")
    foot = foot.reset_index(drop=True)
    poly_id_col = next((c for c in ["poly_id","POLY_ID","OBJECTID","OBJECTID_1","FID","ID","id"] if c in foot.columns), None)
    if poly_id_col is None:
        poly_id_col = "poly_id"
        foot[poly_id_col] = np.arange(1, len(foot)+1, dtype=int)
    foot_29902 = foot.to_crs(EPC_CRS)

    # EPC CSV
    df = pd.read_csv(EPC_IN, dtype=str, low_memory=False)
    total_in = len(df)

    # UPRN + XY
    uprn_col = next((c for c in df.columns if "uprn" in c.lower()), None)
    if uprn_col is None:
        raise ValueError("UPRN column not found in EPC CSV.")
    df["UPRN_key"] = df[uprn_col].map(canonical_uprn)
    df["_X"] = pd.to_numeric(df.get("X_COR"), errors="coerce")
    df["_Y"] = pd.to_numeric(df.get("Y_COR"), errors="coerce")
    df = df.dropna(subset=["UPRN_key","_X","_Y"]).copy()

    # Composite event date + 2024 filter
    df = pick_event_dt(df)
    df = df[df["event_dt"].notna()].copy()
    df["year"] = df["event_dt"].dt.year
    df_2024 = df[df["year"] == 2024].copy()
    kept_2024 = len(df_2024)

    # Points (29902)
    pts = gpd.GeoDataFrame(df_2024, geometry=gpd.points_from_xy(df_2024["_X"], df_2024["_Y"]), crs=EPC_CRS)

    # Pair to polygon: within → nearest
    poly_map = nearest_polygon(pts, foot_29902, poly_id_col)
    pts["poly_id"] = poly_map[poly_id_col].astype("Int64")
    pts = pts.dropna(subset=["poly_id"]).copy()
    pts["poly_id"] = pts["poly_id"].astype(str)
    paired = len(pts)

    # -------- Vectorized dedupe per (UPRN_key, poly_id) --------
    # Rank by: is_top (True>False), level_val (higher>lower), event_dt (later>earlier)
    top_flag = pts.get(STOREY_FLAG_COL)
    pts["rank_is_top"] = top_flag.map(parse_yes).astype(int) if top_flag is not None else 0

    # level rank (combine numeric candidates)
    lvl = None
    for c in LEVEL_COLS:
        if c in pts.columns:
            s = pd.to_numeric(pts[c], errors="coerce")
            lvl = s if lvl is None else lvl.fillna(s)
    if lvl is None:
        lvl = pd.Series(np.nan, index=pts.index)
    pts["rank_level"] = lvl.fillna(-1e12)  # NaN lowest

    pts["rank_dt"] = pts["event_dt"]

    # Sort then take the last row per group (best ranking)
    sort_cols = ["UPRN_key","poly_id","rank_is_top","rank_level","rank_dt"]
    pts_sorted = pts.sort_values(sort_cols)
    chosen_df = pts_sorted.groupby(["UPRN_key","poly_id"], as_index=False).tail(1).copy()

    # Re-wrap as GeoDataFrame in EPC_CRS
    chosen = gpd.GeoDataFrame(chosen_df, geometry="geometry", crs=EPC_CRS)
    after_dedupe = len(chosen)

    # Reproject to WGS84 + lon/lat
    chosen_wgs = chosen.to_crs(OUT_CRS)
    chosen_wgs["lon"] = chosen_wgs.geometry.x
    chosen_wgs["lat"] = chosen_wgs.geometry.y

    # Deterministic uid (on WGS84)
    chosen_wgs["uid"] = [
        build_uid(up, pid, lo, la, dt)
        for up, pid, lo, la, dt in zip(
            chosen_wgs["UPRN_key"], chosen_wgs["poly_id"],
            chosen_wgs["lon"], chosen_wgs["lat"], chosen_wgs["event_dt"]
        )
    ]
    # Copy uid back to the 29902 frame so polygons can use it
    chosen = chosen.assign(uid=chosen_wgs["uid"].values)

    # ---------- Outputs ----------
    # 1) Points CSV (keep all date fields + storey hints + a few EPC attrs)
    keep_dates   = [c for c in DATE_PRIORITY + ["LODGEMENT_DATETIME"] if c in chosen_wgs.columns]
    keep_storey  = [c for c in ["FLOOR_LEVEL","FLAT_STOREY_COUNT","FLAT_TOP_STOREY"] if c in chosen_wgs.columns]
    keep_epc     = [c for c in ["EPC_RATING","CURRENT_ENERGY_RATING","PROPERTY_TYPE","BUILT_FORM","TOTAL_FLOOR_AREA"] if c in chosen_wgs.columns]

    pt_cols = ["uid","lon","lat","UPRN_key","event_dt","event_dt_source"] + keep_dates + keep_storey + keep_epc
    points_out = chosen_wgs[pt_cols].drop_duplicates(subset=["uid"]).copy()
    points_out.to_csv(POINTS_CSV, index=False, encoding="utf-8")

    # 2) Polygons shapefile (WGS84) — merge-free build to avoid name collisions
    #    Map poly_id -> geometry, then attach to chosen rows
    poly_sel = foot_29902[[poly_id_col, "geometry"]].copy()
    poly_sel[poly_id_col] = poly_sel[poly_id_col].astype(str)
    geom_map = poly_sel.set_index(poly_id_col)["geometry"]

    if "poly_id" not in chosen.columns:
        raise RuntimeError("poly_id missing on chosen.")
    if "uid" not in chosen.columns:
        raise RuntimeError("uid missing on chosen.")

    polys_df = chosen[["uid", "poly_id"]].copy()
    polys_df["geometry"] = polys_df["poly_id"].map(geom_map)

    missing = polys_df["geometry"].isna().sum()
    if missing:
        print(f"[warn] {missing} chosen rows have no matching footprint geometry by poly_id.")

    polys = gpd.GeoDataFrame(polys_df, geometry="geometry", crs=EPC_CRS).to_crs(OUT_CRS)
    polys = polys[["uid", "poly_id", "geometry"]]
    _shp, _zip = write_shapefile_zipped(polys, POLY_DIR, POLY_ZIP, layer="gee_epc_2024_polys")

    # 3) UID mapping CSV
    chosen_wgs[["uid","UPRN_key","poly_id"]].to_csv(UID_MAP_CSV, index=False, encoding="utf-8")

    # ---------- Stats ----------
    print("\n=== GEE 2024 target build (final) ===")
    print(f"Input EPC (in-footprints) rows:        {total_in:,}")
    print(f"Rows with UPRN+XY+date (any):          {len(df):,}")
    print(f"Rows in 2024 (by composite event_dt):  {kept_2024:,}")
    print(f"Rows paired to footprints:             {paired:,}")
    print(f"After dedupe (UPRN_key, poly_id):      {after_dedupe:,}")
    print(f"Unique UIDs:                           {points_out['uid'].nunique():,}")
    print(f"\nPoints CSV:    {POINTS_CSV}")
    print(f"Polygons ZIP:  {POLY_ZIP}")
    print(f"UID mapping:   {UID_MAP_CSV}")

if __name__ == "__main__":
    main()
