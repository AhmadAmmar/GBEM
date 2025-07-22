import pandas as pd
import os

# Directory containing the files
data_dir = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data"

# List of input CSV filenames
input_files = [
    "london_filtered.csv"
]

# Define target years
target_years = [2022, 2023, 2024]

# Process each file individually
for input_file in input_files:
    input_path = os.path.join(data_dir, input_file)
    # Read the CSV file
    df = pd.read_csv(input_path)
    
    # Convert the INSPECTION_DATE column to datetime (ignoring errors)
    df["INSPECTION_DATE"] = pd.to_datetime(df["INSPECTION_DATE"], errors="coerce")
    
    # Initialize an empty DataFrame for combined data
    combined_df = pd.DataFrame()
    
    # Filter and save for each target year
    for year in target_years:
        df_year = df[df["INSPECTION_DATE"].dt.year == year]
        combined_df = pd.concat([combined_df, df_year], ignore_index=True)
        output_filename = f"{os.path.splitext(input_file)[0]}_{year}.csv"
        output_path = os.path.join(data_dir, output_filename)
        df_year.to_csv(output_path, index=False)
        print(f"Saved {output_filename} with {len(df_year)} records")
    
    # Save the combined file (all three years)
    output_filename_combined = f"{os.path.splitext(input_file)[0]}_2022-2024.csv"
    output_path_combined = os.path.join(data_dir, output_filename_combined)
    combined_df.to_csv(output_path_combined, index=False)
    print(f"Saved {output_filename_combined} with {len(combined_df)} records")
