import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from tqdm import tqdm
import dask_geopandas as dgpd

# File paths
certificates_file = "D:/OneDrive - Ulster University/PhD/Data/reduced_merged_certificates.csv"
filtered_buildings_file = "D:/OneDrive - Ulster University/PhD/Data/filtered_buildings.fgb"
output_file = "D:/OneDrive - Ulster University/PhD/Data/certificates_with_buildings.fgb"

# Chunk size for processing certificates
chunk_size = 100000

# Load buildings as a Dask GeoDataFrame
print("Loading filtered buildings using Dask...")
buildings_dask = dgpd.read_file(filtered_buildings_file, npartitions=4)
print("Filtered building polygons loaded as Dask GeoDataFrame.")

# Global state to track assigned rows for each building
global_building_assignments = {}

# Function to process a single chunk
def process_chunk(chunk, buildings_dask):
    # Create a GeoDataFrame from the LATITUDE and LONGITUDE columns
    chunk_gdf = gpd.GeoDataFrame(
        chunk,
        geometry=gpd.points_from_xy(chunk['LONGITUDE'], chunk['LATITUDE']),
        crs="EPSG:4326"
    )

    # Perform a spatial join (point-in-polygon)
    print("Performing spatial join...")
    matched = dgpd.sjoin(chunk_gdf, buildings_dask, how="inner", predicate="within")

    # Return the matched rows as a Pandas DataFrame
    return matched.compute()

# Process certificates in chunks and store results in global state
print("Processing certificates and matching with buildings...")
with pd.read_csv(certificates_file, chunksize=chunk_size) as reader:
    for i, chunk in enumerate(tqdm(reader, desc="Processing chunks")):
        print(f"Processing chunk {i + 1}...")
        matched_chunk = process_chunk(chunk, buildings_dask)

        # Consolidate results into the global dictionary
        for building_id, group in matched_chunk.groupby("index_right"):
            if building_id in global_building_assignments:
                global_building_assignments[building_id] = pd.concat(
                    [global_building_assignments[building_id], group]
                )
            else:
                global_building_assignments[building_id] = group

# Apply FLAT_TOP_STOREY logic globally
print("Applying FLAT_TOP_STOREY logic globally...")
final_results = []
for building_id, group in global_building_assignments.items():
    if 'Y' in group['FLAT_TOP_STOREY'].values:
        final_results.append(group[group['FLAT_TOP_STOREY'] == 'Y'].iloc[0])
    else:
        final_results.append(group.iloc[0])

# Convert final results to a GeoDataFrame
final_gdf = gpd.GeoDataFrame(final_results, crs="EPSG:4326")

# Save the consolidated results
print(f"Saving final results to {output_file}...")
final_gdf.to_file(output_file, driver="FlatGeobuf")
print(f"Matching completed. Results saved to: {output_file}")
