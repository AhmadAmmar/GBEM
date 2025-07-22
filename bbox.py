import geopandas as gpd
import shutil
import os
from shapely.geometry import box

# Paths
input_shp = "D:/OneDrive - Ulster University/PhD/Data/London/Old SHP/london.shp"
output_folder = "D:/OneDrive - Ulster University/PhD/Data/London/Old SHP"

# Load and split shapefile into 4 tiles
gdf = gpd.read_file(input_shp)
minx, miny, maxx, maxy = gdf.total_bounds
mid_x, mid_y = (minx + maxx) / 2, (miny + maxy) / 2

tiles = [
    box(minx, mid_y, mid_x, maxy),  # Top-left
    box(mid_x, mid_y, maxx, maxy),  # Top-right
    box(minx, miny, mid_x, mid_y),  # Bottom-left
    box(mid_x, miny, maxx, mid_y),  # Bottom-right
]

for i, tile in enumerate(tiles):
    tile_gdf = gpd.GeoDataFrame(geometry=[tile], crs=gdf.crs)
    tile_name = f"london_tile_{i+1}"

    # Save each tile
    tile_path = os.path.join(output_folder, tile_name)
    os.makedirs(tile_path, exist_ok=True)
    tile_gdf.to_file(os.path.join(tile_path, f"{tile_name}.shp"))

    # Create ZIP archive
    shutil.make_archive(tile_path, 'zip', tile_path)

    # Remove the folder after zipping
    shutil.rmtree(tile_path)

print("✅ 4 Tiles Created and Compressed Successfully!")
