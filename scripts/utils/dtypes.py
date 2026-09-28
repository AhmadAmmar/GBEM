import pandas as pd

# File paths
input_file = "D:/OneDrive - Ulster University/PhD/data/reduced_merged_certificates.csv"
output_file = "D:/OneDrive - Ulster University/PhD/data/column_datatypes.csv"

# Columns to analyze: read from the file's own header instead of a fixed
# list, so this stays correct if the reduction recipe upstream ever adds,
# drops, or renames columns.
columns_to_check = list(pd.read_csv(input_file, nrows=0).columns)

# Initialize data types dictionary
column_datatypes = {col: None for col in columns_to_check}

# Chunk size for processing
chunk_size = 100000

# Process the file in chunks
print("Processing file in chunks...")
with pd.read_csv(input_file, usecols=columns_to_check, chunksize=chunk_size, low_memory=False) as reader:
    for chunk_idx, chunk in enumerate(reader):
        print(f"Processing chunk {chunk_idx + 1}...")
        for col in columns_to_check:
            try:
                inferred_dtype = pd.api.types.infer_dtype(chunk[col], skipna=True)
                if column_datatypes[col] is None:
                    column_datatypes[col] = inferred_dtype
                elif column_datatypes[col] != inferred_dtype:
                    column_datatypes[col] = "mixed"
            except Exception as e:
                print(f"Error processing column {col}: {e}")
                column_datatypes[col] = "error"

# Save results to a file
print("Saving results...")
dtype_df = pd.DataFrame.from_dict(column_datatypes, orient="index", columns=["DataType"])
dtype_df.index.name = "Column"
dtype_df.reset_index(inplace=True)
dtype_df.to_csv(output_file, index=False)

print(f"Column datatypes saved to: {output_file}")
