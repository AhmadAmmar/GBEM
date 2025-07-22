import pandas as pd
import os

# Path to the input and output files
input_file = "D:/OneDrive - Ulster University/PhD/Data/merged_certificates_with_latlon.csv"
output_file = "D:/OneDrive - Ulster University/PhD/Data/header_first_last.csv"

try:
    # Read the header and first row
    header_and_first_row = pd.read_csv(input_file, nrows=1)
    
    # Read the last row
    with open(input_file, 'rb') as f:
        f.seek(-2, os.SEEK_END)  # Move to the end of the file
        while f.read(1) != b'\n':  # Move backward to find the last newline
            f.seek(-2, os.SEEK_CUR)
        last_line = f.readline().decode().strip()
    
    # Extract column names
    with open(input_file, 'r') as f:
        header = f.readline().strip().split(',')
    
    # Convert the last row to a DataFrame
    last_row = pd.DataFrame([last_line.split(',')], columns=header)
    
    # Concatenate header, first row, and last row into one DataFrame
    result = pd.concat([header_and_first_row, last_row], ignore_index=True)
    
    # Save to the output CSV
    result.to_csv(output_file, index=False)
    print(f"Header, first, and last rows saved to: {output_file}")

except FileNotFoundError:
    print(f"File not found: {input_file}")
except Exception as e:
    print(f"An error occurred: {e}")
