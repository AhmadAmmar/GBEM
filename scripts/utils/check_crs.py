"""Print the first latitude and longitude values of the London certificates file, to see which coordinate system
they are in. Early inspection script (2025).
"""
import pandas as pd

# File path
certificates_file = "D:/OneDrive - Ulster University/PhD/data/london/Certs/certificates_london.csv"

# Load the certificates dataset
certificates = pd.read_csv(certificates_file)

# Print the first few rows of LATITUDE and LONGITUDE columns
print(certificates[['LATITUDE', 'LONGITUDE']].head())
