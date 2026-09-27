import geopandas as gpd

# Path to your shapefile
shapefile_path = r"D:\OneDrive - Ulster University\PhD\data\london\Buildings\gis_osm_buildings_a_free_1.shp"

# Load shapefile
gdf = gpd.read_file(shapefile_path)

# Print all column names (i.e., feature attributes)
print("Columns in the shapefile:")
print(gdf.columns)

# Optionally, preview the first few rows
print("\nSample rows:")
print(gdf.head())
