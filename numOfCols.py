import os
import pandas as pd
from tqdm import tqdm

# Directory containing the subfolders with certificates.csv files
base_dir = "D:/OneDrive - Ulster University/PhD/Data/all-domestic-certificates"

# Process all subfolders
subfolders = [f for f in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, f))]

for subfolder in subfolders:
    certificates_path = os.path.join(base_dir, subfolder, "certificates.csv")

    if os.path.isfile(certificates_path):
        try:
            # Load only the header of the current certificates.csv file
            df = pd.read_csv(certificates_path, nrows=0)
            columns_count = len(df.columns)

            # Print the number of columns
            print(columns_count)
        except Exception as e:
            print(f"Error processing {certificates_path}: {e}")
