import geopandas as gpd
import pandas as pd
import dask_geopandas as dgpd
import matplotlib.pyplot as plt
import pickle
import os
from osgeo import ogr
from tqdm import tqdm

# Paths to directories and files
base_dir = "D:/OneDrive - Ulster University/PhD/Data/all-domestic-certificates"
uprn_file_path = "D:/OneDrive - Ulster University/PhD/Data/osopenuprn_202412_csv/osopenuprn_202412.csv"

# Load the UPRN dataset
uprn_data = pd.read_csv(uprn_file_path)
uprn_data = uprn_data.set_index("UPRN")  # Set UPRN as the index for faster lookups

# Function to update LATITUDE and LONGITUDE in certificates.csv files
def update_certificates_file(file_path):
    # Load the certificates.csv file
    certificates = pd.read_csv(file_path)

    # Check if UPRN column exists
    if "UPRN" in certificates.columns:
        # Map LATITUDE and LONGITUDE from the UPRN dataset
        certificates["LATITUDE"] = certificates["UPRN"].map(uprn_data["LATITUDE"])
        certificates["LONGITUDE"] = certificates["UPRN"].map(uprn_data["LONGITUDE"])

        # Save the updated certificates.csv file
        certificates.to_csv(file_path, index=False)

# Traverse all subfolders and process certificates.csv files
subfolders = [f for f in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, f))]

print("Processing certificates files...")
for subfolder in tqdm(subfolders, desc="Processing subfolders"):
    certificates_path = os.path.join(base_dir, subfolder, "certificates.csv")

    if os.path.isfile(certificates_path):
        try:
            update_certificates_file(certificates_path)
        except Exception as e:
            print(f"Error processing {certificates_path}: {e}")

print("All certificates files processed.")