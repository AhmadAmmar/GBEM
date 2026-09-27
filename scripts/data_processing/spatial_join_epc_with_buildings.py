import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

# === Paths ===
epc_path = r"D:\OneDrive - Ulster University\PhD\data\london_samples_indices_binary_2024.csv"
buildings_path = r"D:\OneDrive - Ulster University\PhD\data\london\Buildings\gis_osm_buildings_a_free_1.shp"
output_path = r"D:\OneDrive - Ulster University\PhD\data\london\london_2024_epc_matched_only.geojson"

# === Load EPC CSV and convert to GeoDataFrame ===
epc_df = pd.read_csv(epc_path)

# Convert to GeoDataFrame
epc_gdf = gpd.GeoDataFrame(
    epc_df,
    geometry=gpd.points_from_xy(epc_df['LONGITUDE'], epc_df['LATITUDE']),
    crs="EPSG:4326"
)

# Load buildings shapefile
buildings_gdf = gpd.read_file(buildings_path)

# Reproject EPC GeoDataFrame to match building CRS
epc_gdf = epc_gdf.to_crs(buildings_gdf.crs)

# Spatial join (point-in-polygon)
joined = gpd.sjoin(epc_gdf, buildings_gdf, how="left", predicate="within")

# === Filter: Keep only matched EPCs ===
matched = joined.dropna(subset=["index_right"]).copy()

# Save to GeoJSON
matched.to_file(output_path, driver="GeoJSON")

print(f"\n✅ Saved {len(matched)} matched EPC records to:\n{output_path}")
