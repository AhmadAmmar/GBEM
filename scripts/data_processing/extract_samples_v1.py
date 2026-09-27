import os
import geopandas as gpd
import pandas as pd
import rasterio
from rasterstats import zonal_stats
from multiprocessing import Pool, cpu_count
from tqdm import tqdm

# === File Paths ===
geojson_path = r"D:\OneDrive - Ulster University\PhD\data\london\london_2024_epc_matched_only.geojson"
raster_folder = r"D:\OneDrive - Ulster University\PhD\data\london\Sat"
output_path = r"D:\OneDrive - Ulster University\PhD\data\london\london_2024_epc_with_indices.geojson"

# === Point Sampling Function (Parallel) ===
def process_point_raster(args):
    band_name, raster_file, coords = args
    values = []
    try:
        with rasterio.open(raster_file) as src:
            for lon, lat in coords:
                try:
                    row, col = src.index(lon, lat)
                    value = src.read(1)[row, col]
                    values.append(value)
                except:
                    values.append(float('nan'))
    except Exception as e:
        print(f"⚠️ {band_name} point extraction failed: {e}")
        return band_name, [float('nan')] * len(coords)
    return band_name, values

# === Main Workflow ===
if __name__ == "__main__":
    # --- Load Data ---
    print("📍 Loading EPC dataset with building polygons...")
    gdf = gpd.read_file(geojson_path)
    existing_cols = set(gdf.columns)

    # --- Get (lon, lat) coordinates for EPCs ---
    coords = list(zip(gdf["LONGITUDE"], gdf["LATITUDE"]))

    # --- Gather raster files ---
    raster_files = {
        os.path.splitext(f)[0]: os.path.join(raster_folder, f)
        for f in os.listdir(raster_folder) if f.endswith(".tif")
    }

    print(f"🛰️ Found {len(raster_files)} raster files.")

    # === POINT VALUE EXTRACTION (EPC centroids) ===
    print("⚙️ Extracting raster values at EPC centroid points (parallel)...")
    args_list = [(band, path, coords) for band, path in raster_files.items()]
    with Pool(cpu_count() - 1) as pool:
        results = list(tqdm(pool.imap(process_point_raster, args_list), total=len(args_list), desc="📌 Point Sampling"))

    # Add extracted point values to GeoDataFrame
    for band_name, values in results:
        if band_name not in gdf.columns:
            gdf[band_name] = values

    # === ZONAL MEAN VALUE EXTRACTION (Buildings) ===
    print("🏛️ Extracting zonal mean raster values from building polygons...")
    for band_name, raster_path in tqdm(raster_files.items(), desc="🏗️ Zonal Sampling", unit="raster"):
        colname = f"{band_name}_avg"
        try:
            zs = zonal_stats(gdf.geometry, raster_path, stats=["mean"], nodata=None)
            gdf[colname] = [z["mean"] if z else None for z in zs]
        except Exception as e:
            print(f"⚠️ Zonal mean failed for {band_name}: {e}")

    # === Save final output ===
    print(f"💾 Saving GeoJSON with added indices: {output_path}")
    gdf.to_file(output_path, driver="GeoJSON")
    print("✅ Done! GeoJSON updated with point & zonal index values.")
