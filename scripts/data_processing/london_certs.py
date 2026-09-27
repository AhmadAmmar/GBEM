import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from tqdm import tqdm

# File paths
csv_file = "D:/OneDrive - Ulster University/PhD/data/merged_certificates_with_latlon.csv"
shp_file = "D:/OneDrive - Ulster University/PhD/data/london/SHP/london.shp"
output_csv = "D:/OneDrive - Ulster University/PhD/data/london_filtered.csv"

# Load the London shapefile
london_boundary = gpd.read_file(shp_file)

# Ensure the shapefile has a consistent CRS
london_boundary = london_boundary.to_crs(epsg=4326)

# Chunk size for processing the CSV file
chunk_size = 50000  # Adjust for memory usage

# Columns to export
columns_to_export = [
    "LATITUDE",
    "LONGITUDE",
    "CURRENT_ENERGY_RATING",
    "CURRENT_ENERGY_EFFICIENCY",
    "CO2_EMISSIONS_CURRENT",
    "CO2_EMISS_CURR_PER_FLOOR_AREA",
    "ENVIRONMENT_IMPACT_CURRENT",
    "ENERGY_CONSUMPTION_CURRENT",
    "HEATING_COST_CURRENT",
    "LIGHTING_COST_CURRENT",
    "HOT_WATER_COST_CURRENT",
    "TOTAL_FLOOR_AREA",
    "WALLS_ENERGY_EFF",
    "ROOF_ENERGY_EFF",
    "FLOOR_ENERGY_EFF",
    "WINDOWS_ENERGY_EFF",
    "MAINHEAT_ENERGY_EFF",
    "HOT_WATER_ENERGY_EFF",
    "LIGHTING_ENERGY_EFF",
    "FLOOR_LEVEL",
    "FLAT_TOP_STOREY",
    "FLAT_STOREY_COUNT",
    "PROPERTY_TYPE",
    "BUILT_FORM",
    "NUMBER_HABITABLE_ROOMS",
    "TENURE",
    "MAIN_FUEL",
    "INSPECTION_DATE",
    "CONSTRUCTION_AGE_BAND"
]

# Function to process each chunk and filter rows within the London boundary
def filter_chunk(chunk, london_boundary):
    # Filter out rows with missing LATITUDE/LONGITUDE
    chunk = chunk.dropna(subset=["LATITUDE", "LONGITUDE"])
    # Create a GeoDataFrame from the chunk using LATITUDE and LONGITUDE columns
    chunk['geometry'] = [Point(xy) for xy in zip(chunk["LONGITUDE"], chunk["LATITUDE"])]
    gdf = gpd.GeoDataFrame(chunk, geometry='geometry', crs="EPSG:4326")

    # Spatial join to keep only rows within the London boundary
    gdf_within_london = gdf[gdf.geometry.within(london_boundary.unary_union)]

    # Drop the geometry column before returning
    return gdf_within_london.drop(columns='geometry')

# Process the CSV file in chunks and write filtered rows to a new CSV
print("Filtering rows within the London boundary...")
is_first_chunk = True  # Track whether to write headers to the output file

# Calculate the number of chunks for tqdm progress bar
total_rows = sum(1 for _ in open(csv_file)) - 1  # Subtract header row
num_chunks = (total_rows // chunk_size) + 1

with pd.read_csv(csv_file, chunksize=chunk_size, usecols=columns_to_export) as reader:
    for chunk in tqdm(reader, desc="Processing chunks", total=num_chunks):
        # Filter the current chunk
        filtered_chunk = filter_chunk(chunk, london_boundary)

        # Append the filtered chunk to the output file
        filtered_chunk.to_csv(output_csv, mode='a', index=False, header=is_first_chunk)
        is_first_chunk = False  # After the first chunk, do not write headers

print(f"Filtered rows saved to: {output_csv}")
