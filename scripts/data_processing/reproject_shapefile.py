import geopandas as gpd

# File paths
input_shp = "D:/OneDrive - Ulster University/PhD/data/london/SHP/london.shp"
output_shp = "D:/OneDrive - Ulster University/PhD/data/london/SHP/london_wgs84.shp"

# Load the London shapefile
london_boundary = gpd.read_file(input_shp)

# Check the current CRS of the shapefile
print("Original CRS:", london_boundary.crs)

# Reproject to WGS 1984 (EPSG:4326)
london_boundary_wgs84 = london_boundary.to_crs(epsg=4326)

# Save the reprojected shapefile
london_boundary_wgs84.to_file(output_shp)

print(f"Reprojected shapefile saved to: {output_shp}")
print("New CRS:", london_boundary_wgs84.crs)
