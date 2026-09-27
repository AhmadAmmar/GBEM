import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import rasterio
import matplotlib.pyplot as plt

# File paths
epc_csv = r"D:\OneDrive - Ulster University\PhD\data\20231125T143956000_visual_30_hotsat1_2023.csv"
thermal_tiff = r"D:\OneDrive - Ulster University\PhD\data\a2a9a8ac-c897-4caf-81f0-9724169a4da0\visual\20231125T143956000_visual_30_hotsat1\20231125T143956000_visual_30_hotsat1.tiff"

# Load EPC CSV file into a DataFrame and drop rows with missing coordinates
epc_df = pd.read_csv(epc_csv)
epc_df = epc_df.dropna(subset=['LATITUDE', 'LONGITUDE'])

# Create a GeoDataFrame for EPC certificates (assuming they are in EPSG:4326)
geometry = [Point(xy) for xy in zip(epc_df['LONGITUDE'], epc_df['LATITUDE'])]
epc_gdf = gpd.GeoDataFrame(epc_df, geometry=geometry, crs="EPSG:4326")

# Open the thermal TIFF image and read the first band
with rasterio.open(thermal_tiff) as src:
    thermal_image = src.read(1)  # reading the first band
    thermal_crs = src.crs
    bounds = src.bounds  # left, bottom, right, top
    transform = src.transform

# Reproject EPC points to the thermal image's CRS if needed
if epc_gdf.crs != thermal_crs:
    epc_gdf = epc_gdf.to_crs(thermal_crs)

# Prepare extent for imshow (left, right, bottom, top)
extent = (bounds.left, bounds.right, bounds.bottom, bounds.top)

# Create the plot
fig, ax = plt.subplots(figsize=(10, 10))

# Display the thermal image with a gray colormap
cax = ax.imshow(thermal_image, cmap='gray', extent=extent)
ax.set_title("Thermal Image with EPC Certificates Overlay")
ax.set_xlabel("Easting")
ax.set_ylabel("Northing")

# Overlay the EPC points
epc_gdf.plot(ax=ax, marker='o', color='red', markersize=5, label="EPC Certificates")

# Optionally, add a legend and colorbar
ax.legend()
fig.colorbar(cax, ax=ax, label="Digital Number (DN)")

plt.show()
