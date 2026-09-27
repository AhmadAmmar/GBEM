import pandas as pd
import numpy as np
from tqdm import tqdm

# File paths
input_file = "D:/OneDrive - Ulster University/PhD/data/reduced_merged_certificates.csv"
output_file = "D:/OneDrive - Ulster University/PhD/data/column_statistics_with_all_unique_fixed.csv"
unique_values_output = "D:/OneDrive - Ulster University/PhD/data/column_unique_values_fixed.csv"

# Function to calculate stats for numeric data across chunks
def update_numeric_stats(chunk, stats):
    chunk = chunk.dropna()
    stats["Min"] = min(stats["Min"], chunk.min()) if stats["Min"] is not None else chunk.min()
    stats["Max"] = max(stats["Max"], chunk.max()) if stats["Max"] is not None else chunk.max()
    stats["Sum"] += chunk.sum()
    stats["Count"] += len(chunk)
    stats["Values"].extend(chunk.tolist())

# Function to finalize numeric stats
def finalize_numeric_stats(stats):
    if stats["Count"] > 0:
        stats["Mean"] = stats["Sum"] / stats["Count"]
        stats["Median"] = np.median(stats["Values"])
        stats["Mode"] = pd.Series(stats["Values"]).mode().iloc[0] if stats["Values"] else None
    else:
        stats["Mean"], stats["Median"], stats["Mode"] = None, None, None
    stats.pop("Values")  # Remove raw values to save space
    stats.pop("Sum")  # Remove the sum as it's no longer needed
    stats.pop("Count")  # Remove the count

# Initialize results
results = []
unique_values_records = []

# Fetch column names
print("Fetching column names...")
columns = pd.read_csv(input_file, nrows=0).columns.tolist()

# Process each column individually
for column in tqdm(columns, desc="Processing columns"):
    print(f"Processing column: {column}...")
    is_numeric = True  # Assume numeric unless proven otherwise
    numeric_stats = {"Min": None, "Max": None, "Sum": 0, "Count": 0, "Values": []}
    unique_values = set()

    # Process the column in chunks
    for chunk in tqdm(
        pd.read_csv(input_file, usecols=[column], chunksize=100000, low_memory=False),
        desc=f"Processing column {column}",
        leave=False
    ):
        chunk_data = chunk[column]
        if pd.api.types.is_numeric_dtype(chunk_data):
            # Update stats for numeric columns
            update_numeric_stats(chunk_data, numeric_stats)
        else:
            # Collect unique values for non-numeric or mixed columns
            is_numeric = False
            unique_values.update(chunk_data.dropna().unique())

    if is_numeric:
        # Finalize stats for numeric columns
        finalize_numeric_stats(numeric_stats)
        numeric_stats["Column"] = column
        numeric_stats["Type"] = "Numeric"
        numeric_stats["Unique Values"] = None
        results.append(numeric_stats)

        # Print stats for numeric columns
        print(f"Column: {column}, Type: Numeric")
        print(f"  Min: {numeric_stats['Min']}, Max: {numeric_stats['Max']}")
        print(f"  Mean: {numeric_stats['Mean']}, Median: {numeric_stats['Median']}")
        print(f"  Mode: {numeric_stats['Mode']}\n")
    else:
        # Save unique values as separate rows
        for value in unique_values:
            unique_values_records.append({"Column": column, "Unique Value": value})

        # Add a summary record for non-numeric columns
        results.append({
            "Column": column,
            "Type": "Non-Numeric",
            "Min": None,
            "Max": None,
            "Mean": None,
            "Median": None,
            "Mode": None,
            "Unique Values": len(unique_values)  # Store the count of unique values
        })

        # Print unique values for non-numeric columns
        print(f"Column: {column}, Type: Non-Numeric")
        print(f"  Number of Unique Values: {len(unique_values)}\n")

# Convert results to a DataFrame
results_df = pd.DataFrame(results)

# Save results to a CSV file
results_df.to_csv(output_file, index=False, encoding="utf-8")
print(f"Column statistics saved to: {output_file}")

# Save unique values to a separate CSV file
unique_values_df = pd.DataFrame(unique_values_records)
unique_values_df.to_csv(unique_values_output, index=False, encoding="utf-8", sep="|")  # Use '|' as delimiter
print(f"Unique values saved to: {unique_values_output}")
