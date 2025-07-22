import pandas as pd

# File paths
input_file = "D:/OneDrive - Ulster University/PhD/Data/reduced_merged_certificates.csv"
output_file = "D:/OneDrive - Ulster University/PhD/Data/column_data_types_new.csv"

# Chunk size for processing
chunk_size = 100000

# Dictionary to store column data types
column_types = {}

# Process the file in chunks
print("Analyzing column data types...")
with pd.read_csv(input_file, chunksize=chunk_size, low_memory=False) as reader:
    for chunk_idx, chunk in enumerate(reader):
        print(f"Processing chunk {chunk_idx + 1}...")
        for column in chunk.columns:
            # Analyze column data types if not already analyzed
            if column not in column_types:
                sample_values = chunk[column].dropna().head(10)  # Take a small sample for analysis
                detected_types = set()

                for value in sample_values:
                    if isinstance(value, (int, float)):
                        detected_types.add("numeric")
                    elif isinstance(value, str):
                        if value.isdigit():
                            detected_types.add("integer-like string")
                        elif value.replace('.', '', 1).isdigit():
                            detected_types.add("float-like string")
                        elif " " in value or len(value) > 1:
                            detected_types.add("word/string")
                        else:
                            detected_types.add("character")
                    elif isinstance(value, list):
                        detected_types.add("array")
                    elif isinstance(value, dict):
                        detected_types.add("dictionary")
                    else:
                        detected_types.add("object")

                column_types[column] = detected_types

# Prepare results as a DataFrame
results = pd.DataFrame(
    [{"Column": col, "Detected Types": ", ".join(types)} for col, types in column_types.items()]
)

# Save the column data types to a CSV file
results.to_csv(output_file, index=False)
print(f"Column data types saved to: {output_file}")
