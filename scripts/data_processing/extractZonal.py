import os
import geopandas as gpd
from rasterstats import zonal_stats
from tqdm import tqdm
import warnings

warnings.filterwarnings("ignore", category=UserWarning)

# === File Paths ===
geojson_path = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\London\london_2024_epc_with_calculated_indices.geojson"
raster_folder = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\London\Sat"
output_geojson = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\London\london_2024_epc_with_zonal_means.geojson"

# === Parameters ===
batch_size = 10000

# === Load GeoDataFrame ===
print("📍 Loading building polygons...")
gdf = gpd.read_file(geojson_path)
geometries = gdf["geometry"]
print(f"🏘️ Total polygons: {len(gdf)}")

# === Get list of raster files ===
raster_files = [f for f in os.listdir(raster_folder) if f.endswith(".tif")]
raster_paths = [(os.path.splitext(f)[0], os.path.join(raster_folder, f)) for f in raster_files]
print(f"🛰️ Total rasters to process: {len(raster_paths)}")

# === Main Loop: Process one raster at a time ===
for band_name, tif_path in tqdm(raster_paths, desc="📡 Processing Rasters", position=0):
    print(f"\n🔄 Now processing: {band_name}")

    zonal_means = []

    total_batches = (len(geometries) + batch_size - 1) // batch_size

    for batch_idx in tqdm(range(total_batches), desc=f"📦 Batches ({band_name})", position=1, leave=False):
        batch_start = batch_idx * batch_size
        batch_end = min((batch_idx + 1) * batch_size, len(geometries))
        batch_geoms = geometries.iloc[batch_start:batch_end]

        # Inner tqdm to simulate polygon-wise progress (note: zonal_stats processes all at once)
        _ = [
            _ for _ in tqdm(batch_geoms, desc=f"   🧱 Polygons {batch_start}-{batch_end}", position=2, leave=False)
        ]

        try:
            batch_stats = zonal_stats(batch_geoms, tif_path, stats=["mean"], nodata=None)
            batch_means = [s["mean"] if s else None for s in batch_stats]
            zonal_means.extend(batch_means)
        except Exception as e:
            print(f"⚠️ Error in batch {batch_idx+1} for {band_name}: {e}")
            zonal_means.extend([None] * len(batch_geoms))

    # Assign the complete series to new column
    gdf[f"{band_name}_avg"] = zonal_means

# === Save the updated GeoJSON ===
print(f"\n💾 Saving updated GeoJSON: {output_geojson}")
gdf.to_file(output_geojson, driver="GeoJSON")
print("✅ Done! Zonal means added for all rasters.")
