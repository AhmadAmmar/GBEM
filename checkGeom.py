import geopandas as gpd

# Path to the shapefile
shapefile_path = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\London\shapefile_export\only_polygons\london_2024_epc_id_polygononly.shp"

# Load shapefile
gdf = gpd.read_file(shapefile_path)

# Print first few rows with geometry type
print("📋 First few geometry types:")
print(gdf.geometry[:5].geom_type)

# Count geometry types
geometry_counts = gdf.geom_type.value_counts()
print("\n📊 Geometry type counts in the shapefile:")
print(geometry_counts)
