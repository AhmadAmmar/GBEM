import geopandas as gpd

# === File Paths ===
input_geojson = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\London\london_2024_epc_with_calculated_indices.geojson"
full_output_geojson = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\London\london_2024_epc_with_id.geojson"
light_output_geojson = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\London\london_2024_epc_id_latlon_geom.geojson"

# === Load original full EPC GeoJSON ===
print("📍 Loading original EPC file...")
gdf = gpd.read_file(input_geojson)

# === Create a new ID column ===
gdf = gdf.reset_index(drop=True)
gdf["id"] = gdf.index.astype(str)

# === Save full updated file with ID ===
print(f"💾 Saving full file with ID to: {full_output_geojson}")
gdf.to_file(full_output_geojson, driver="GeoJSON")

# === Extract minimal version for GEE ===
print("✂️ Extracting lightweight version (id + lat/lon + geometry)...")
lite_gdf = gdf[["id", "LATITUDE", "LONGITUDE", "geometry"]].copy()

# === Save minimal version ===
print(f"💾 Saving lightweight file to: {light_output_geojson}")
lite_gdf.to_file(light_output_geojson, driver="GeoJSON")

print("✅ Done!")
