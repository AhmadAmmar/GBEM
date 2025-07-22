import os
import pandas as pd
from tqdm import tqdm

# Directory containing the subfolders with certificates.csv files
base_dir = "D:/OneDrive - Ulster University/PhD/Data/all-domestic-certificates"

# Initialize variables
expected_columns = None
mismatch_found = False

# List to store column names for the first, second, and last file
first_file_columns = None
second_file_columns = None
last_file_columns = None

# Process all subfolders
subfolders = [f for f in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, f))]

print("Verifying column names and order in certificates.csv files...")
for idx, subfolder in enumerate(tqdm(subfolders, desc="Processing subfolders")):
    certificates_path = os.path.join(base_dir, subfolder, "certificates.csv")
    
    if os.path.isfile(certificates_path):
        try:
            # Load the current certificates.csv file
            df = pd.read_csv(certificates_path, nrows=0)  # Only read the header
            columns = df.columns.tolist()

            # Save columns for first, second, and last files for comparison
            if idx == 0:
                first_file_columns = columns
            elif idx == 1:
                second_file_columns = columns
            last_file_columns = columns
            
            if expected_columns is None:
                # Set the first file's columns as the expected columns
                expected_columns = columns
                print(f"Expected columns set from: {certificates_path}")
            else:
                # Compare current file's columns with the expected columns
                if columns != expected_columns:
                    mismatch_found = True
                    print(f"Column mismatch in {certificates_path}")
                    print(f"Expected: {expected_columns}")
                    print(f"Found:    {columns}")
        except Exception as e:
            print(f"Error processing {certificates_path}: {e}")

if not mismatch_found:
    print("All certificates.csv files have consistent column names and order.")
else:
    print("Some certificates.csv files have mismatched column names or order.")

# Print comparison of first, second, and last file columns
print("\nComparison of column names across files:")
if first_file_columns:
    print("\nFirst file columns:")
    print(first_file_columns)

if second_file_columns:
    print("\nSecond file columns:")
    print(second_file_columns)

if last_file_columns:
    print("\nLast file columns:")
    print(last_file_columns)
