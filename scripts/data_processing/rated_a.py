import pandas as pd

# Load the CSV file
file_path = r"D:\OneDrive - Ulster University\PhD\data\london_filtered.csv"
df = pd.read_csv(file_path, low_memory=False)

# Ensure date column is datetime
df['INSPECTION_DATE'] = pd.to_datetime(df['INSPECTION_DATE'], errors='coerce')

# Filter for rating A
rating_a = df[df['CURRENT_ENERGY_RATING'] == 'A']

# Total number of A-rated EPCs
total_a = len(rating_a)

# A-rated EPCs per year
a_2022 = len(rating_a[rating_a['INSPECTION_DATE'].dt.year == 2022])
a_2023 = len(rating_a[rating_a['INSPECTION_DATE'].dt.year == 2023])
a_2024 = len(rating_a[rating_a['INSPECTION_DATE'].dt.year == 2024])

# Print results
print(f"Total 'A' rated EPCs: {total_a}")
print(f"'A' rated in 2022: {a_2022}")
print(f"'A' rated in 2023: {a_2023}")
print(f"'A' rated in 2024: {a_2024}")
