import geopandas as gpd
import numpy as np

# === File paths ===
input_path = r"D:\OneDrive - Ulster University\PhD\data\london\london_2024_epc_matched_only.geojson"
output_path = r"D:\OneDrive - Ulster University\PhD\data\london\london_2024_epc_with_calculated_indices.geojson"

# === Load GeoDataFrame ===
print("📍 Loading GeoJSON...")
gdf = gpd.read_file(input_path)

# === Define index calculations ===
def safe_divide(numerator, denominator):
    return np.where((denominator == 0) | (np.isnan(denominator)), np.nan, numerator / denominator)

print("🧮 Calculating new indices...")

# Moisture Index (e.g., NDMI): (B8 - B11) / (B8 + B11)
gdf["Moisture_Index"] = safe_divide(gdf["B8"] - gdf["B11"], gdf["B8"] + gdf["B11"])

# LSWI = (B8 - B11) / (B8 + B11) — same as Moisture Index (can keep both for naming consistency)
gdf["LSWI"] = gdf["Moisture_Index"]

# BUI = (B11 - B5) / (B11 + B5)
gdf["BUI"] = safe_divide(gdf["B11"] - gdf["B5"], gdf["B11"] + gdf["B5"])

# Brightness Index = sqrt((B11² + B12²) / 2)
gdf["Brightness_Index"] = np.sqrt((gdf["B11"]**2 + gdf["B12"]**2) / 2)

# SWIR_NDWI = (B3 - B11) / (B3 + B11)
gdf["SWIR_NDWI"] = safe_divide(gdf["B3"] - gdf["B11"], gdf["B3"] + gdf["B11"])

# SAVI = (1.5 * (B8 - B4)) / (B8 + B4 + 0.5)
gdf["SAVI"] = safe_divide(1.5 * (gdf["B8"] - gdf["B4"]), gdf["B8"] + gdf["B4"] + 0.5)

# RE_NDVI = (B8A - B5) / (B8A + B5)
gdf["RE_NDVI"] = safe_divide(gdf["B8A"] - gdf["B5"], gdf["B8A"] + gdf["B5"])

# Albedo Proxy = (B2 + B4 + B5 + B6 + B7) / 5
gdf["Albedo_Proxy"] = (gdf["B2"] + gdf["B4"] + gdf["B5"] + gdf["B6"] + gdf["B7"]) / 5

# === Save the updated GeoJSON ===
print(f"💾 Saving to: {output_path}")
gdf.to_file(output_path, driver="GeoJSON")
print("✅ Done! Indices added: Moisture_Index, LSWI, BUI, Brightness_Index, SWIR_NDWI, SAVI, RE_NDVI, Albedo_Proxy")
