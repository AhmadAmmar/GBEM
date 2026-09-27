import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

# Load files
epc = gpd.read_file(r"D:\OneDrive - Ulster University\PhD\data\london\london_2024_epc_with_id.geojson")
buildings = gpd.read_file(r"D:\OneDrive - Ulster University\PhD\data\london\Buildings\gis_osm_buildings_a_free_1.shp")

# Keep only relevant columns (osm_id + geometry)
buildings_subset = buildings[["osm_id", "geometry"]].copy()

# Merge based on osm_id (this replaces point with polygon)
merged = epc.merge(buildings_subset, on="osm_id", how="left", suffixes=("", "_poly"))

# Replace point geometry with polygon geometry
merged["geometry"] = merged["geometry_poly"]
merged = merged.drop(columns=["geometry_poly"])

# Save output
output_path = r"D:\OneDrive - Ulster University\PhD\data\london\london_2024_epc_with_polygons.geojson"
merged.to_file(output_path, driver="GeoJSON")
print(f"✅ Polygon geometries added and saved to:\n{output_path}")
