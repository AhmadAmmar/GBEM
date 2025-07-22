import geopandas as gpd
from tqdm import tqdm

# File paths
osm_buildings_file = "D:/OneDrive - Ulster University/PhD/Data/England Buildings/gis_osm_buildings_a_free_1.shp"
london_shp_file = "D:/OneDrive - Ulster University/PhD/Data/London SHP/london.shp"
output_file = "D:/OneDrive - Ulster University/PhD/Data/london_osm_buildings.shp"

# Load the London shapefile
print("Loading London shapefile...")
london_boundary = gpd.read_file(london_shp_file)

# Ensure the shapefile has a consistent CRS
london_boundary = london_boundary.to_crs(epsg=4326)

# Load the OSM buildings dataset
print("Loading OSM buildings dataset...")
osm_buildings = gpd.read_file(osm_buildings_file)

# Ensure the OSM buildings have the same CRS as the London boundary
osm_buildings = osm_buildings.to_crs(epsg=4326)

# Filter OSM buildings within the London boundary
print("Filtering buildings within London boundary...")
osm_buildings_within_london = osm_buildings[
    osm_buildings.geometry.within(london_boundary.unary_union)
]

# Save the filtered buildings to a new shapefile
print("Saving filtered buildings to a new file...")
osm_buildings_within_london.to_file(output_file, driver="ESRI Shapefile")

print(f"Filtered buildings saved to: {output_file}")