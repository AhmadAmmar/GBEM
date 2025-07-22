import pandas as pd

# File paths
input_file = "D:/OneDrive - Ulster University/PhD/Data/reduced_merged_certificates.csv"
output_file = "D:/OneDrive - Ulster University/PhD/Data/unique_counties.csv"

# Column to inspect
column_to_inspect = "COUNTY"

# Chunk size for processing
chunk_size = 100000

# Set to store unique values
unique_values = set()

# Process the file in chunks
print(f"Extracting unique values from column '{column_to_inspect}'...")
with pd.read_csv(input_file, usecols=[column_to_inspect], chunksize=chunk_size, low_memory=False) as reader:
    for chunk_idx, chunk in enumerate(reader):
        print(f"Processing chunk {chunk_idx + 1}...")
        # Update the set with unique values from the current chunk
        unique_values.update(chunk[column_to_inspect].dropna().unique())

# Convert the set of unique values to a DataFrame
unique_values_df = pd.DataFrame(sorted(unique_values), columns=[column_to_inspect])

# Save the unique values to a CSV file
unique_values_df.to_csv(output_file, index=False)
print(f"Unique values in column '{column_to_inspect}' saved to: {output_file}")
