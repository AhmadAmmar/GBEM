import geopandas as gpd
import os
from shapely.geometry import Polygon

# Paths
input_path = r"D:\OneDrive - Ulster University\PhD\data\london\shapefile_export\london_2024_epc_id_poly_geom.shp"
output_dir = r"D:\OneDrive - Ulster University\PhD\data\london\shapefile_export\polygon_clean_final_upload"
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, "london_2024_epc_id_polygononly_final_upload.shp")

# Load
gdf = gpd.read_file(input_path)

# Filter only Polygons
gdf = gdf[gdf.geometry.type == "Polygon"].copy()

# Drop empty geometries
gdf = gdf[~gdf.is_empty & gdf.geometry.notnull()].copy()

# Save again
gdf.to_file(output_path)
print(f"✅ Final clean export done to:\n{output_path}")
