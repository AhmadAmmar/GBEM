import geopandas as gpd

# Load your GeoJSON
input_geojson = r"D:\OneDrive - Ulster University\PhD\data\london\gee_upload_epc_polygons.geojson"
output_shp_folder = r"D:\OneDrive - Ulster University\PhD\data\london\shapefile_export"

# Read GeoJSON
gdf = gpd.read_file(input_geojson)

# Save as Shapefile (creates multiple files in a folder)
gdf.to_file(output_shp_folder, driver="ESRI Shapefile")

print("✅ Exported as Shapefile. Now zip the folder to upload to GEE.")
