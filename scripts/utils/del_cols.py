import pandas as pd

# Paths to the input and output files
input_file = "D:/OneDrive - Ulster University/PhD/data/merged_certificates_with_latlon.csv"
output_file = "D:/OneDrive - Ulster University/PhD/data/reduced_merged_certificates.csv"

# Columns to drop
columns_to_drop = [
    "ADDRESS1", "ADDRESS2", "ADDRESS3", "POSTCODE", "ADDRESS",
    "UPRN", "UPRN_SOURCE", "INSPECTION_DATE", "LODGEMENT_DATE", "LODGEMENT_DATETIME",
    "CONSTITUENCY_LABEL", "LOCAL_AUTHORITY_LABEL", "POSTTOWN",
    "LOCAL_AUTHORITY", "CONSTITUENCY", "COUNTY"
]

# Process the file in chunks
chunk_size = 100000  # Number of rows per chunk
try:
    with pd.read_csv(input_file, chunksize=chunk_size) as reader:
        for i, chunk in enumerate(reader):
            # Drop the specified columns
            reduced_chunk = chunk.drop(columns=columns_to_drop, errors='ignore')

            # Write to the output file (append mode after the first chunk)
            mode = 'w' if i == 0 else 'a'
            header = i == 0  # Write header only for the first chunk
            reduced_chunk.to_csv(output_file, mode=mode, index=False, header=header)
            print(f"Processed chunk {i + 1}")
    
    print(f"The reduced file has been saved to: {output_file}")
except Exception as e:
    print(f"An error occurred: {e}")
