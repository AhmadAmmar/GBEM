import geopandas as gpd

# Path to your matched EPC GeoJSON
geojson_path = r"D:\OneDrive - Ulster University\PhD\data\london\london_2024_epc_with_id.geojson"

# Load the GeoJSON
gdf = gpd.read_file(geojson_path)

# Print number of rows and column names
print(f"✅ Number of matched EPC rows: {len(gdf)}\n")
print("📋 Columns in the GeoDataFrame:")
for col in gdf.columns:
    print(f" - {col}")
