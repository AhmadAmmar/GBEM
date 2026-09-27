import pandas as pd
import numpy as np

# File paths
input_file = "D:/OneDrive - Ulster University/PhD/data/reduced_merged_certificates.csv"
output_file = "D:/OneDrive - Ulster University/PhD/data/column_summary.csv"

# Load the dataset in chunks to handle large files
chunk_size = 100000
column_summary = {}

print("Processing file in chunks...")
with pd.read_csv(input_file, chunksize=chunk_size, low_memory=False) as reader:
    for chunk_idx, chunk in enumerate(reader):
        print(f"Processing chunk {chunk_idx + 1}...")
        for column in chunk.columns:
            if column not in column_summary:
                column_summary[column] = {"values": set() if chunk[column].dtype == 'object' else None}

            try:
                if pd.api.types.is_numeric_dtype(chunk[column]):
                    # For numeric columns, compute stats incrementally
                    if column_summary[column]["values"] is None:
                        column_summary[column]["values"] = {
                            "min": chunk[column].min(skipna=True),
                            "max": chunk[column].max(skipna=True),
                            "mean": chunk[column].mean(skipna=True),
                            "median": chunk[column].median(skipna=True),
                            "count": chunk[column].count(),
                            "mode": chunk[column].mode().iloc[0] if not chunk[column].mode().empty else None,
                        }
                    else:
                        # Update stats
                        current_stats = column_summary[column]["values"]
                        current_stats["min"] = min(current_stats["min"], chunk[column].min(skipna=True))
                        current_stats["max"] = max(current_stats["max"], chunk[column].max(skipna=True))
                        current_stats["mean"] = (
                            current_stats["mean"] * current_stats["count"] +
                            chunk[column].mean(skipna=True) * chunk[column].count()
                        ) / (current_stats["count"] + chunk[column].count())
                        current_stats["median"] = None  # Cannot compute median across chunks
                        current_stats["count"] += chunk[column].count()
                        mode_value = chunk[column].mode()
                        if not mode_value.empty:
                            current_stats["mode"] = mode_value.iloc[0]

                else:
                    # For non-numeric columns, collect unique values
                    column_summary[column]["values"].update(chunk[column].dropna().astype(str).unique())

            except Exception as e:
                print(f"Error processing column {column}: {e}")

# Convert results into a DataFrame
summary_rows = []
for column, summary in column_summary.items():
    if summary["values"] is not None:
        if isinstance(summary["values"], dict):  # Numeric stats
            summary_rows.append({
                "Column": column,
                **summary["values"]
            })
        else:  # Categorical unique values
            summary_rows.append({
                "Column": column,
                "Unique Values": list(summary["values"]),
                "Type": "categorical"
            })

summary_df = pd.DataFrame(summary_rows)

# Save summary to a file
summary_df.to_csv(output_file, index=False)
print(f"Column summary saved to: {output_file}")
