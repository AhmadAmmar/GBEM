import pandas as pd
import os

# Path to the merged certificates file
file_path = "D:/OneDrive - Ulster University/PhD/data/merged_certificates_with_latlon.csv"

try:
    # Read the first three rows
    first_three_rows = pd.read_csv(file_path, nrows=3)
    
    # Read the last three rows efficiently
    with open(file_path, 'rb') as f:
        f.seek(-2, os.SEEK_END)  # Move to the end of the file
        while f.read(1) != b'\n':  # Move backward to find the last newline
            f.seek(-2, os.SEEK_CUR)
        last_three_lines = []
        while len(last_three_lines) < 3:  # Collect the last three lines
            f.seek(-2, os.SEEK_CUR)
            if f.read(1) == b'\n':
                last_three_lines.append(f.readline().decode().strip())
        last_three_lines = last_three_lines[::-1]  # Reverse for correct order

    # Extract column names
    with open(file_path, 'r') as f:
        header = f.readline().strip().split(',')

    # Parse last three lines into DataFrames
    last_three_rows = pd.DataFrame([line.split(',') for line in last_three_lines], columns=header)

    # Print the number of fields in each row
    print("Number of fields in the first three rows:")
    for i, row in first_three_rows.iterrows():
        print(f"Row {i + 1}: {len(row)} fields")

    print("\nNumber of fields in the last three rows:")
    for i, row in last_three_rows.iterrows():
        print(f"Row {len(first_three_rows) + i + 1}: {len(row)} fields")

except Exception as e:
    print(f"An error occurred: {e}")
