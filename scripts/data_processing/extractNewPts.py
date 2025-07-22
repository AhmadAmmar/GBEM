import os
import geopandas as gpd
import rasterio
import numpy as np
from tqdm import tqdm

# === File Paths ===
geojson_path = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\London\london_2024_epc_matched_only.geojson"
raster_folder = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\London\Sat"
output_path = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\London\london_2024_epc_with_new_point_indices.geojson"

# === List of new indices to extract ===
new_indices = [
    "Moisture_Index", "LSWI", "BUI", "Brightness_Index",
    "SWIR_NDWI", "SAVI", "RE_NDVI", "Albedo_Proxy"
]

# === Point sampling with full tqdm (Index > Batch > Point) ===
def extract_raster_values_batched(coords, raster_path, batch_size=5000, band_name=""):
    results = []
    try:
        with rasterio.open(raster_path) as src:
            num_batches = (len(coords) + batch_size - 1) // batch_size
            for i in tqdm(range(num_batches), desc=f"   📦 Batches ({band_name})", leave=False, position=1):
                batch = coords[i*batch_size : (i+1)*batch_size]
                batch_vals = []
                for lon, lat in tqdm(batch, desc=f"      📍 Points in Batch {i+1}", leave=False, position=2):
                    try:
                        row, col = src.index(lon, lat)
                        value = src.read(1)[row, col]
                        batch_vals.append(value)
                    except:
                        batch_vals.append(np.nan)
                results.extend(batch_vals)
    except Exception as e:
        print(f"⚠️ Error reading raster {raster_path}: {e}")
        return [np.nan] * len(coords)
    return results

# === Main Logic ===
if __name__ == "__main__":
    print("📍 Loading GeoJSON...")
    gdf = gpd.read_file(geojson_path)
    coords = list(zip(gdf["LONGITUDE"], gdf["LATITUDE"]))
    existing_cols = set(gdf.columns)

    print(f"📦 Total new indices to extract: {len(new_indices)}")
    for index in tqdm(new_indices, desc="📌 Indices", position=0):
        if index in existing_cols:
            tqdm.write(f"✅ {index} already exists — skipping.")
            continue
        tif_path = os.path.join(raster_folder, f"{index}.tif")
        if not os.path.exists(tif_path):
            tqdm.write(f"⚠️ Missing file: {index}.tif — skipped.")
            continue

        tqdm.write(f"🛰️ Extracting: {index}")
        gdf[index] = extract_raster_values_batched(coords, tif_path, batch_size=5000, band_name=index)

    # Save final output
    print(f"💾 Saving to: {output_path}")
    gdf.to_file(output_path, driver="GeoJSON")
    print("✅ Done! All new point values added.")
