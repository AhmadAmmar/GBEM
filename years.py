import pandas as pd

# Load the filtered CSV
file_path = r"C:/Users/B00996107/OneDrive - Ulster University/PhD/Data/london_filtered.csv"
df = pd.read_csv(file_path, low_memory=False)

# Ensure INSPECTION_DATE is in datetime format
df['INSPECTION_DATE'] = pd.to_datetime(df['INSPECTION_DATE'], errors='coerce')

# Extract the year and count occurrences
certs_per_year = df['INSPECTION_DATE'].dt.year.value_counts().sort_index()

# Print results
print(certs_per_year)
