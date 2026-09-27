import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import rasterio
import numpy as np
import matplotlib.pyplot as plt

# File paths
epc_csv = r"D:\OneDrive - Ulster University\PhD\data\20231125T143956000_visual_30_hotsat1_2022-2024.csv"
thermal_tiff = r"D:\OneDrive - Ulster University\PhD\data\a2a9a8ac-c897-4caf-81f0-9724169a4da0\visual\20231125T143956000_visual_30_hotsat1\20231125T143956000_visual_30_hotsat1.tiff"
output_excel = r"D:\OneDrive - Ulster University\PhD\data\epc_thermal_samples.xlsx"

# Load the EPC CSV file into a DataFrame
epc_df = pd.read_csv(epc_csv)

# Drop rows with missing latitude/longitude
epc_df = epc_df.dropna(subset=['LATITUDE', 'LONGITUDE'])

# Create a GeoDataFrame from the EPC data (assuming the coordinates are in EPSG:4326)
geometry = [Point(xy) for xy in zip(epc_df['LONGITUDE'], epc_df['LATITUDE'])]
epc_gdf = gpd.GeoDataFrame(epc_df, geometry=geometry, crs="EPSG:4326")

# Open the thermal TIFF and sample the pixel values at the certificate locations
with rasterio.open(thermal_tiff) as src:
    # Reproject EPC data to match the TIFF's CRS if necessary
    if src.crs != epc_gdf.crs:
        epc_gdf = epc_gdf.to_crs(src.crs)
    
    # Sample the raster at each point location (assuming a single-band image)
    thermal_vals = []
    for geom in epc_gdf.geometry:
        try:
            for val in src.sample([(geom.x, geom.y)]):
                thermal_vals.append(val[0])
        except Exception:
            thermal_vals.append(np.nan)
    
    # Add the sampled thermal DN values to the GeoDataFrame
    epc_gdf['thermal_dn'] = thermal_vals

# Exclude points with thermal DN == 0
epc_gdf = epc_gdf[epc_gdf['thermal_dn'] != 0]

# Map EPC ratings (assumed to be letters) to numerical values
# Adjust the mapping as needed; here A is best (7) and G is worst (1)
epc_mapping = {'A': 7, 'B': 6, 'C': 5, 'D': 4, 'E': 3, 'F': 2, 'G': 1}
epc_gdf['epc_numeric'] = epc_gdf['CURRENT_ENERGY_RATING'].map(epc_mapping)

# Drop rows with missing thermal values or missing numeric EPC ratings
epc_gdf = epc_gdf.dropna(subset=['thermal_dn', 'epc_numeric'])

# Compute the correlation for the numeric EPC rating column
corr_epc = epc_gdf['thermal_dn'].corr(epc_gdf['epc_numeric'])
print("Correlation between thermal DN and numeric EPC rating:", corr_epc)

# Optionally, plot the relationship for EPC rating
plt.figure(figsize=(8,6))
plt.scatter(epc_gdf['thermal_dn'], epc_gdf['epc_numeric'], alpha=0.5)
plt.xlabel("Thermal DN (uncalibrated)")
plt.ylabel("Numeric EPC Rating")
plt.title("Thermal DN vs. Numeric EPC Rating")
plt.show()

# Now, iteratively compute correlations for all other fields
correlations = {}
for col in epc_gdf.columns:
    # Skip non-relevant columns
    if col in ['thermal_dn', 'geometry']:
        continue
    # Try to convert the column to numeric values
    numeric_series = pd.to_numeric(epc_gdf[col], errors='coerce')
    valid = numeric_series.notna() & epc_gdf['thermal_dn'].notna()
    if valid.sum() > 10:  # Ensure a reasonable number of valid points
        corr_val = epc_gdf.loc[valid, 'thermal_dn'].corr(numeric_series[valid])
        correlations[col] = corr_val

# Sort correlations by the absolute correlation value (descending)
sorted_corr = sorted(correlations.items(), key=lambda x: abs(x[1]), reverse=True)

print("\nCorrelation values between thermal DN and all numeric fields:")
for col, corr in sorted_corr:
    print(f"{col}: {corr}")

# ------------------------------------------------------
# Save the sampled data to Excel
# Reproject back to EPSG:4326 if you want lat/lon in geographic coords
epc_gdf = epc_gdf.to_crs(epsg=4326)
epc_gdf['latitude'] = epc_gdf.geometry.y
epc_gdf['longitude'] = epc_gdf.geometry.x

# Choose the columns you want to save
df_to_save = epc_gdf[['CURRENT_ENERGY_RATING', 'epc_numeric', 'thermal_dn', 'latitude', 'longitude']].copy()
df_to_save.to_excel(output_excel, index=False)
print(f"\nSaved sampled data to: {output_excel}")
