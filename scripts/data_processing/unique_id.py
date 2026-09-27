# slim_for_gee.py
# Make minimal GEE uploadables:
# - Points: uid, lon, lat (CSV)
# - Polygons: uid + geometry (zipped SHP)
from pathlib import Path
import pandas as pd
import geopandas as gpd
import zipfile
import tempfile

# ---- INPUTS ----
POINTS_IN    = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-epc\gee_epc_2024_points_uid_wgs84.csv"
POLYS_ZIP_IN = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-epc\gee_epc_2024_polygons_uid_wgs84.zip"

# ---- OUTPUTS ----
POINTS_OUT     = Path(POINTS_IN).with_name("gee_epc_2024_points_uid_wgs84_MIN.csv")
POLY_MIN_DIR   = Path(POLYS_ZIP_IN).with_name("gee_epc_2024_polygons_uid_wgs84_MIN_shp")
POLYS_ZIP_OUT  = Path(POLYS_ZIP_IN).with_name("gee_epc_2024_polygons_uid_wgs84_MIN.zip")
POLY_MIN_LAYER = "gee_epc_2024_polys_min"

# ------------- POINTS: keep only uid, lon, lat -------------
pts = pd.read_csv(POINTS_IN, dtype={"uid": str})
need = ["uid", "lon", "lat"]
missing = [c for c in need if c not in pts.columns]
if missing:
    raise RuntimeError(f"Missing columns in points CSV: {missing}")

pts_min = pts[need].drop_duplicates(subset=["uid"]).copy()
pts_min.to_csv(POINTS_OUT, index=False, encoding="utf-8")
print(f"Wrote minimal points → {POINTS_OUT}  (rows={pts_min['uid'].nunique():,})")

# ------------- POLYGONS: extract from ZIP, slim, re-zip -------------
# Clear / create output dir
if POLY_MIN_DIR.exists():
    for p in POLY_MIN_DIR.glob("*"):
        p.unlink()
else:
    POLY_MIN_DIR.mkdir(parents=True, exist_ok=True)

with zipfile.ZipFile(POLYS_ZIP_IN, "r") as zf, tempfile.TemporaryDirectory() as tmpdir:
    # Find the .shp inside the ZIP
    shp_names = [n for n in zf.namelist() if n.lower().endswith(".shp")]
    if not shp_names:
        raise RuntimeError("No .shp found inside the polygons ZIP.")
    shp_name = shp_names[0]                        # use the first shapefile in the ZIP
    stem = Path(shp_name).stem

    # Extract all component files for this shapefile (same stem)
    for name in zf.namelist():
        if Path(name).stem == stem:
            zf.extract(name, tmpdir)

    # Locate extracted .shp (may be inside a subfolder)
    shp_path = next(Path(tmpdir).rglob(f"{stem}.shp"))

    # Read, keep uid+geometry
    gdf = gpd.read_file(shp_path)
    if "uid" not in gdf.columns:
        raise RuntimeError("Column 'uid' not found in polygons shapefile.")
    keep = gdf[["uid", "geometry"]].copy()

    # Write slim shapefile
    shp_out = POLY_MIN_DIR / f"{POLY_MIN_LAYER}.shp"
    keep.to_file(shp_out, driver="ESRI Shapefile")

# Zip up the slim shapefile
with zipfile.ZipFile(POLYS_ZIP_OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf_out:
    for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        f = POLY_MIN_DIR / f"{POLY_MIN_LAYER}{ext}"
        if f.exists():
            zf_out.write(f, arcname=f.name)

print(f"Wrote minimal polygons → {POLYS_ZIP_OUT}  (features={len(keep):,})")
