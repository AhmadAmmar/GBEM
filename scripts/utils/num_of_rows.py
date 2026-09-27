import fiona

# File path to the filtered buildings file
filtered_buildings_file = "D:/OneDrive - Ulster University/PhD/data/filtered_buildings.fgb"

# Get metadata
with fiona.open(filtered_buildings_file, "r") as source:
    metadata = source.meta
    total_features = len(source)  # Total number of features if available

print(f"Total number of buildings in {filtered_buildings_file}: {total_features}")
