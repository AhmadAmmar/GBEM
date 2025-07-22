import pandas as pd

# File path
input_file = "D:/OneDrive - Ulster University/PhD/Data/reduced_merged_certificates.csv"

# Column to inspect
column_to_inspect = "SHEATING_ENERGY_EFF"

# Chunk size for processing
chunk_size = 100000

# Set to store unique values
unique_values = set()

# Process the file in chunks
print(f"Extracting unique values from column '{column_to_inspect}'...")
with pd.read_csv(input_file, usecols=[column_to_inspect], chunksize=chunk_size, low_memory=False) as reader:
    for chunk_idx, chunk in enumerate(reader):
        print(f"Processing chunk {chunk_idx + 1}...")
        unique_values.update(chunk[column_to_inspect].dropna().unique())

# Print unique values
print("\nUnique values in column 'SHEATING_ENERGY_EFF':")
for value in sorted(unique_values):
    print(value)
