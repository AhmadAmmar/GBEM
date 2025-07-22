import pandas as pd

# File path
certificates_file = "D:/OneDrive - Ulster University/PhD/Data/London/Certs/certificates_london.csv"

# Load the certificates dataset
certificates = pd.read_csv(certificates_file)

# Print the first few rows of LATITUDE and LONGITUDE columns
print(certificates[['LATITUDE', 'LONGITUDE']].head())
