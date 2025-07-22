import pandas as pd

# Path to the merged certificates file with latitude and longitude
file_path = "D:/OneDrive - Ulster University/PhD/Data/reduced_merged_certificates.csv"

# Check if the file exists and print column names
try:
    # Load just the header row
    df = pd.read_csv(file_path, nrows=0)
    
    # Print column names
    print("Column names in reduced_merged_certificates.csv:")
    for col in df.columns:
        print(col)
except FileNotFoundError:
    print(f"File not found: {file_path}")
except Exception as e:
    print(f"Error reading the file: {e}")
