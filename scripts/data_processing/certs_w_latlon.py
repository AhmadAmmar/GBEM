import geopandas as gpd
import pandas as pd
import dask_geopandas as dgpd
import matplotlib.pyplot as plt
import pickle
import os
from osgeo import ogr
from tqdm import tqdm

import pandas as pd

# Path to the merged certificates file
input_file = "D:/OneDrive - Ulster University/PhD/data/merged_certificates.csv"

# Path to save the filtered certificates file
output_file = "D:/OneDrive - Ulster University/PhD/data/merged_certificates_with_latlon.csv"

# Load the merged certificates file
df = pd.read_csv(input_file)

# Filter rows where LATITUDE or LONGITUDE is not null
filtered_df = df[(df['LATITUDE'].notna()) & (df['LONGITUDE'].notna())]

# Save the filtered DataFrame to a new file
filtered_df.to_csv(output_file, index=False)

print(f"Filtered certificates file saved to: {output_file}")