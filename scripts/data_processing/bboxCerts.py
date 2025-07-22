import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, box
from tqdm import tqdm

# File paths
csv_file = "C:/Users/B00996107/OneDrive - Ulster University/PhD/Data/merged_certificates_with_latlon.csv"
output_csv = "C:/Users/B00996107/OneDrive - Ulster University/PhD/Data/20231125T143956000_visual_30_hotsat1.csv"

# Define the bounding box from the Hotsat-1 metadata
# BBOX: [min_longitude, min_latitude, max_longitude, max_latitude]
bbox_polygon = box(-2.8452404837960463,53.28043859845512,-2.6825848115109543,53.355410736715)

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

# Function to process each chunk and filter rows within the bbox
def filter_chunk(chunk, bbox_polygon):
    # Filter out rows with missing LATITUDE/LONGITUDE values
    chunk = chunk.dropna(subset=["LATITUDE", "LONGITUDE"])
    # Create a geometry column from the LATITUDE and LONGITUDE columns
    chunk['geometry'] = [Point(xy) for xy in zip(chunk["LONGITUDE"], chunk["LATITUDE"])]
    gdf = gpd.GeoDataFrame(chunk, geometry='geometry', crs="EPSG:4326")
    
    # Filter rows where the point lies within the defined bounding box
    gdf_within_bbox = gdf[gdf.geometry.within(bbox_polygon)]
    
    # Drop the geometry column before returning the result
    return gdf_within_bbox.drop(columns='geometry')

print("Filtering EPC certificates within the specified bbox...")

is_first_chunk = True  # Track whether to write headers to the output file

# Calculate the total number of rows for the tqdm progress bar
total_rows = sum(1 for _ in open(csv_file)) - 1  # Subtract the header row
num_chunks = (total_rows // chunk_size) + 1

with pd.read_csv(csv_file, chunksize=chunk_size, usecols=columns_to_export) as reader:
    for chunk in tqdm(reader, desc="Processing chunks", total=num_chunks):
        # Process and filter the current chunk
        filtered_chunk = filter_chunk(chunk, bbox_polygon)
        # Append the filtered chunk to the output CSV file
        filtered_chunk.to_csv(output_csv, mode='a', index=False, header=is_first_chunk)
        is_first_chunk = False  # After the first chunk, do not write headers

print(f"Filtered rows saved to: {output_csv}")
