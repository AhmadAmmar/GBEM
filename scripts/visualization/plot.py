import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import pearsonr

# Load your dataset
file_path = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\london_samples_indices_binary_2024.csv"
df = pd.read_csv(file_path)

# Select relevant columns and drop missing values
x_col = 'VV_VH_Sum'
y_col = 'ENVIRONMENT_IMPACT_CURRENT'
subset = df[[x_col, y_col]].dropna()

# Calculate Pearson correlation
corr, p_value = pearsonr(subset[x_col], subset[y_col])

# Plot
plt.figure(figsize=(8, 6))
sns.regplot(x=x_col, y=y_col, data=subset, scatter_kws={"s": 10}, line_kws={"color": "red"})
plt.title(f"{y_col} vs {x_col}\nPearson r = {corr:.3f}, p = {p_value:.2e}")
plt.xlabel(x_col)
plt.ylabel(y_col)
plt.grid(True)

# Show or save the plot
plt.tight_layout()
plt.show()
# Optional: Save
# plt.savefig("environment_impact_vs_vv_vh_sum.png", dpi=300)
