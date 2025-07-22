import pandas as pd
from scipy.stats import pearsonr

# Load the dataset
file_path = r"C:/Users/B00996107/OneDrive - Ulster University/PhD/Data/london_samples_indices_binary_2024.csv"
print("Loading dataset...")
df = pd.read_csv(file_path)

# Define Excel-like column ranges (A to AA → index 0–26), (AD to BD → index 29–55)
group1_cols = df.iloc[:, 0:27].select_dtypes(include='number').columns
group2_cols = df.iloc[:, 29:56].select_dtypes(include='number').columns

# Store correlation results
correlation_results = []

print("Computing correlations...")

for col1 in group1_cols:
    for col2 in group2_cols:
        subset = df[[col1, col2]].dropna()
        if not subset.empty:
            corr, _ = pearsonr(subset[col1], subset[col2])
            correlation_results.append((col1, col2, corr))

# Sort by absolute correlation value (descending)
sorted_results = sorted(correlation_results, key=lambda x: abs(x[2]), reverse=True)

# Print results
print("\nTop correlations between Group 1 (A–AA) and Group 2 (AD–BD):\n")
for col1, col2, corr in sorted_results:
    print(f"{col1} vs {col2} → Pearson r = {corr:.3f}")
