import geopandas as gpd

# === Input file (with polygon geometry and lat/lon columns) ===
input_path = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\London\london_2024_epc_with_polygons.geojson"

# === Output for GEE ===
output_path = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\London\gee_upload_epc_polygons.geojson"

# === Load the full GeoJSON ===
gdf = gpd.read_file(input_path)

# === Keep only relevant columns ===
columns_to_keep = ["id", "LATITUDE", "LONGITUDE", "geometry"]
gdf_subset = gdf[columns_to_keep].copy()

# === Confirm geometry is polygon ===
gdf_subset = gdf_subset[gdf_subset.geometry.type.isin(["Polygon", "MultiPolygon"])]

# === Save to GeoJSON ===
gdf_subset.to_file(output_path, driver="GeoJSON")

print(f"✅ Exported for GEE upload:\n{output_path}")
print(f"🧮 Total features exported: {len(gdf_subset)}")
