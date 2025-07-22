import pandas as pd

# Path to the merged certificates file
input_file = "D:/OneDrive - Ulster University/PhD/Data/merged_certificates_with_latlon.csv"
output_file = "D:/OneDrive - Ulster University/PhD/Data/first_five_rows.csv"

try:
    # Read the first five rows
    first_five_rows = pd.read_csv(input_file, nrows=5)
    
    # Save the extracted rows to a new file
    first_five_rows.to_csv(output_file, index=False)
    
    print(f"The first five rows have been saved to: {output_file}")
except Exception as e:
    print(f"An error occurred: {e}")
