import pandas as pd
import os

# Paths to the merged certificates files
merged_file = "D:\OneDrive - Ulster University\PhD\data\london\Certs\certificates_london.csv"
latlon_file = "D:/OneDrive - Ulster University/PhD/data/reduced_merged_certificates_london_filtered.csv"

# Function to count rows in a file
def count_rows(file_path, file_description):
    if os.path.exists(file_path):
        try:
            # Load the file in chunks to avoid memory issues if files are large
            total_rows = sum(1 for _ in open(file_path)) - 1  # Subtract 1 for header
            print(f"Number of rows in {file_description}: {total_rows}")
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
    else:
        print(f"{file_description} does not exist at path: {file_path}")

# Count rows in merged_certificates.csv
count_rows(merged_file, "reduced_merged_certificates_london_filtered1.csv")

# Count rows in merged_certificates_with_latlon.csv
count_rows(latlon_file, "reduced_merged_certificates_london_filtered.csv")
