import geopandas as gpd

# === File Paths ===
input_geojson = r"D:\OneDrive - Ulster University\PhD\data\london\london_2024_epc_with_calculated_indices.geojson"
output_csv = r"D:\OneDrive - Ulster University\PhD\data\london\epc_sample_first_11.csv"

# === Load GeoJSON ===
print("📍 Loading GeoJSON...")
gdf = gpd.read_file(input_geojson)

# === Extract first 11 rows ===
gdf_first_11 = gdf.head(11)

# === Save to CSV (drop geometry to avoid export issues) ===
gdf_first_11.drop(columns=["geometry"]).to_csv(output_csv, index=False)

print(f"✅ First 11 rows exported to CSV: {output_csv}")
