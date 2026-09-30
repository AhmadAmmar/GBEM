"""Report the number of rows in every data file (CSV, Parquet, GeoJSON, GeoPackage, FlatGeobuf, pickle) in the data folder."""
import os
import pandas as pd
import geopandas as gpd
import pyarrow.parquet as pq
import pickle
import json
import fiona

folder_path = r"D:\OneDrive - Ulster University\PhD\data"
extensions = ['.parquet', '.pkl', '.fgb', '.pbf', '.json', '.geojson', '.csv', '.gpkg']

def get_row_count(filepath, ext):
    try:
        if ext == '.csv':
            return sum(1 for _ in open(filepath, encoding='utf-8')) - 1  # subtract header

        elif ext == '.parquet':
            return pq.ParquetFile(filepath).metadata.num_rows

        elif ext in ['.json', '.geojson']:
            with open(filepath, encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    if 'features' in data:  # GeoJSON
                        return len(data['features'])
                    else:  # JSON dictionary
                        return len(data)
                elif isinstance(data, list):
                    return len(data)
                else:
                    return 0

        elif ext == '.gpkg' or ext == '.fgb':
            with fiona.open(filepath) as layer:
                return len(layer)

        elif ext == '.pkl':
            with open(filepath, 'rb') as f:
                obj = pickle.load(f)
                return len(obj) if hasattr(obj, '__len__') else 0

        elif ext == '.pbf':
            with fiona.open(filepath, driver='MVT') as layer:
                return len(layer)

    except Exception as e:
        print(f"Error reading {os.path.basename(filepath)}: {e}")
        return 0

file_counts = []

for file in os.listdir(folder_path):
    _, ext = os.path.splitext(file.lower())
    if ext in extensions:
        path = os.path.join(folder_path, file)
        count = get_row_count(path, ext)
        file_counts.append((file, count))
        print(f"{file}: {count:,} rows")

# Sort and print summary
file_counts.sort(key=lambda x: x[1], reverse=True)

print("\n=== Sorted File Summary ===")
for file, count in file_counts:
    print(f"{file}: {count:,} rows")
