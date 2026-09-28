import pandas as pd
import numpy as np

# File paths
input_file = "D:/OneDrive - Ulster University/PhD/data/london/london_samples_2024.csv"
output_file = "D:/OneDrive - Ulster University/PhD/data/london/london_samples_indices_2024.csv"

# Load the dataset
print("Loading dataset...")
data = pd.read_csv(input_file)

# Sentinel-2 Indices
print("Calculating Sentinel-2 indices...")

# NDVI (Normalized Difference Vegetation Index)
data['NDVI'] = (data['B8'] - data['B4']) / (data['B8'] + data['B4'])

# NDBI (Normalized Difference Built-up Index)
data['NDBI'] = (data['B11'] - data['B8']) / (data['B11'] + data['B8'])

# UI (Urban Index)
data['UI'] = data['B11'] / data['B8']

# IBI (Index-Based Built-up Index)
data['IBI'] = ((data['B11'] - (data['B8'] + data['B4'])) / 
               (data['B11'] + (data['B8'] + data['B4'])))

# EVI (Enhanced Vegetation Index)
data['EVI'] = 2.5 * ((data['B8'] - data['B4']) / 
                     (data['B8'] + 6 * data['B4'] - 7.5 * data['B2'] + 1))

# NDWI (Normalized Difference Water Index)
data['NDWI'] = (data['B3'] - data['B8']) / (data['B3'] + data['B8'])

# GNDVI (Green Normalized Difference Vegetation Index)
data['GNDVI'] = (data['B8'] - data['B3']) / (data['B8'] + data['B3'])

# Sentinel-1 Indices (VV and VH)
print("Calculating Sentinel-1 indices...")

# Sum
data['VV_VH_Sum'] = data['VH'] + data['VV']

# Difference
data['VV_VH_Difference'] = data['VH'] - data['VV']

# Product
data['VV_VH_Product'] = data['VH'] * data['VV']

# Normalized Difference
data['VV_VH_Normalized_Difference'] = (data['VH'] - data['VV']) / (data['VH'] + data['VV'])

# Proportion VH
data['VH_Proportion'] = data['VH'] / (data['VH'] + data['VV'])

# Proportion VV
data['VV_Proportion'] = data['VV'] / (data['VH'] + data['VV'])

# Advanced Polarization Index
data['Advanced_Polarization_Index'] = (data['VH']**2 - data['VV']**2) / (data['VH'] + data['VV'])

# Log Ratio
data['VH_VV_Log_Ratio'] = np.log(data['VH'] / (data['VV'] + 1e-10))

# Landsat-8 Indices
print("Calculating Landsat-8 indices...")

# Handle potential division by zero or invalid values
print("Handling invalid values...")
data.replace([np.inf, -np.inf], np.nan, inplace=True)
data.fillna(value=np.nan, inplace=True)

# Save the updated dataset
print(f"Saving dataset with all indices to {output_file}...")
data.to_csv(output_file, index=False)
print("All indices calculated and dataset saved!")
