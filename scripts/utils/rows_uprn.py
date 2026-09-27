import os
import pandas as pd
from tqdm import tqdm

# Directory containing the subfolders with certificates.csv files
base_dir = "D:/OneDrive - Ulster University/PhD/data/all-domestic-certificates"

# Initialize counters
total_rows = 0
total_rows_with_uprn = 0

# Process all subfolders
subfolders = [f for f in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, f))]

print("Counting rows in certificates files...")
for subfolder in tqdm(subfolders, desc="Processing subfolders"):
    certificates_path = os.path.join(base_dir, subfolder, "certificates.csv")
    
    if os.path.isfile(certificates_path):
        try:
            # Load the certificates.csv file
            df = pd.read_csv(certificates_path)
            
            # Count total rows minus header
            rows_in_file = len(df)
            total_rows += rows_in_file
            
            # Count rows with a valid UPRN
            rows_with_uprn = df['UPRN'].notna().sum()
            total_rows_with_uprn += rows_with_uprn
            
            print(f"File: {certificates_path} - Total rows: {rows_in_file}, Rows with UPRN: {rows_with_uprn}")
        except Exception as e:
            print(f"Error processing {certificates_path}: {e}")

# Print the final counts
print(f"Total rows across all certificates.csv files: {total_rows}")
print(f"Total rows with UPRN across all certificates.csv files: {total_rows_with_uprn}")
