import pandas as pd

# Path to the certificates file
file_path = "D:/OneDrive - Ulster University/PhD/Data/reduced_merged_certificates.csv"

try:
    # Read the FLAT_TOP_STOREY column
    df = pd.read_csv(file_path, usecols=["FLAT_TOP_STOREY"])

    # Get unique values in the column
    unique_values = df["FLAT_TOP_STOREY"].unique()

    # Print unique values
    print("Unique values in FLAT_TOP_STOREY column:")
    for value in unique_values:
        print(value)

except Exception as e:
    print(f"An error occurred: {e}")
