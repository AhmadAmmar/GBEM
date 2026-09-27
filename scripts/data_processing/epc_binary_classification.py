import pandas as pd

# Load data
file_path = r"D:\OneDrive - Ulster University\PhD\data\london_samples_indices_2024.csv"
df = pd.read_csv(file_path, low_memory=False)

# Define efficient/inneficient categories
efficient_ratings = ['A', 'B', 'C']

# Apply classification
df['EFFICIENCY_CLASS'] = df['CURRENT_ENERGY_RATING'].apply(
    lambda x: 1 if x in efficient_ratings else 0
)

# Count results
class_counts = df['EFFICIENCY_CLASS'].value_counts()
print("Efficiency class counts (1 = Efficient, 0 = Inefficient):")
print(class_counts)

# Save to new file
output_path = r"D:\OneDrive - Ulster University\PhD\data\london_samples_indices_2024_epc_band_binary.csv"
df.to_csv(output_path, index=False)

print(f"\nBinary EPC-based classification saved to:\n{output_path}")
