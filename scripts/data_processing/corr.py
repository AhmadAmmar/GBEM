import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import pearsonr

# File paths
input_file = "D:/OneDrive - Ulster University/PhD/Data/London/Output/satellite_samples_with_all_indices.csv"
output_plots_dir = "D:/OneDrive - Ulster University/PhD/Data/London/Output/CorrelationPlots/"

# Load the dataset
print("Loading dataset...")
data = pd.read_csv(input_file)

# Define the column for energy efficiency
energy_efficiency_column = "CURRENT_ENERGY_EFFICIENCY"

# Define column indices for satellite bands (as in Excel: e.g., AI=34, AJ=35, etc.)
start_index = 34  # Replace with the actual starting index for your desired columns
end_index = 52    # Replace with the actual ending index for your desired columns

# Select columns by index
custom_columns = data.iloc[:, start_index:end_index].columns

# Create correlation plots
print("Creating correlation plots...")
for band in custom_columns:
    # Drop rows with NaN values in the current band or energy efficiency column
    subset = data[[energy_efficiency_column, band]].dropna()
    
    # Compute correlation
    correlation, p_value = pearsonr(subset[energy_efficiency_column], subset[band])
    
    # Plot scatterplot with regression line
    plt.figure(figsize=(8, 6))
    sns.regplot(x=energy_efficiency_column, y=band, data=subset, scatter_kws={"s": 10}, line_kws={"color": "red"})
    plt.title(f"Correlation: {energy_efficiency_column} vs {band}\nPearson r = {correlation:.2f}, p = {p_value:.2e}")
    plt.xlabel(f"{energy_efficiency_column}")
    plt.ylabel(f"{band} Value")
    plt.grid(True)
    
    # Save plot
    plot_file = f"{output_plots_dir}{band}_correlation.png"
    plt.savefig(plot_file, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved plot: {plot_file}")

print("All correlation plots generated and saved.")
