import geopandas as gpd
import pandas as pd
import dask_geopandas as dgpd
import matplotlib.pyplot as plt
import pickle
import os
from osgeo import ogr
from tqdm import tqdm

# Directory containing the subfolders with certificates.csv files
base_dir = "D:/OneDrive - Ulster University/PhD/data/all-domestic-certificates"

# Path to save the merged certificates file
output_file = "D:/OneDrive - Ulster University/PhD/data/merged_certificates.csv"

# Initialize the output file
is_first_file = True

# Process all subfolders
subfolders = [f for f in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, f))]

print("Merging certificates files incrementally...")
for subfolder in tqdm(subfolders, desc="Processing subfolders"):
    certificates_path = os.path.join(base_dir, subfolder, "certificates.csv")
    
    if os.path.isfile(certificates_path):
        try:
            # Load the current certificates.csv file
            df = pd.read_csv(certificates_path)
            
            # Append to the output file
            df.to_csv(output_file, mode='w' if is_first_file else 'a', index=False, header=is_first_file)
            
            # After the first file is written, skip writing the header for subsequent files
            is_first_file = False
        except Exception as e:
            print(f"Error processing {certificates_path}: {e}")

print(f"All certificates files merged into: {output_file}")
