import pandas as pd

# File paths
input_file = "D:/OneDrive - Ulster University/PhD/data/london/Certs/certificates_london.csv"
output_file = "D:/OneDrive - Ulster University/PhD/data/london/Certs/certificates_london_sample_100.csv"

# Load the certificates dataset
certificates = pd.read_csv(input_file)

# Define the minimum number of samples per energy rating level
min_samples_per_rating = 100

# Perform stratified sampling to ensure at least 1000 representatives for each rating level
sampled_certificates = certificates.groupby("CURRENT_ENERGY_RATING", group_keys=False).apply(
    lambda x: x.sample(n=min(len(x), min_samples_per_rating), random_state=42)
).reset_index(drop=True)

# Save the sampled data to a new file
sampled_certificates.to_csv(output_file, index=False)

print(f"Balanced sampled data saved to: {output_file}")
