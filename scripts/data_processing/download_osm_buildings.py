import geopandas as gpd
import osmnx as ox

# File paths
shp_file = "D:/OneDrive - Ulster University/PhD/data/London SHP/london.shp"
output_file = "D:/OneDrive - Ulster University/PhD/data/london_osm_buildings.geojson"

# Load the London shapefile
london_boundary = gpd.read_file(shp_file)

# Ensure the shapefile has a consistent CRS
london_boundary = london_boundary.to_crs(epsg=4326)

# Convert the shapefile boundary to a GeoJSON-like dictionary
london_polygon = london_boundary.geometry.unary_union

# Download OSM building footprints within the area of interest
print("Downloading OSM building features...")
buildings = ox.geometries.geometries_from_polygon(
    london_polygon, tags={"building": True}
)

# Save the results to a GeoJSON file
print("Saving OSM building features...")
buildings.to_file(output_file, driver="GeoJSON")

print(f"OSM building features saved to: {output_file}")
