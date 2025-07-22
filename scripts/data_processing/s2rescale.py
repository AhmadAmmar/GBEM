import os
import rasterio
from rasterio.enums import Resampling
from rasterio import Affine
import numpy as np

# Define input and output folders
input_folder = r"D:\OneDrive - Ulster University\PhD\Data\London\Sat\Bands"
output_folder = r"D:\OneDrive - Ulster University\PhD\Data\London\Sat\Scaled_Bands"

# Ensure the output folder exists
os.makedirs(output_folder, exist_ok=True)

# Iterate through each file in the input folder
for filename in os.listdir(input_folder):
    if filename.endswith(".tif"):  # Process only .tif files
        input_path = os.path.join(input_folder, filename)
        output_path = os.path.join(output_folder, filename)

        # Open the raster file
        with rasterio.open(input_path) as src:
            # Read all the bands as a NumPy array
            data = src.read().astype(np.float32)  # Convert to float32 for scaling
            scaled_data = data / 10000.0  # Apply the scaling factor

            # Update metadata for the output file
            meta = src.meta.copy()
            meta.update(dtype=rasterio.float32)  # Set the data type to float32

            # Write the scaled raster to the output file
            with rasterio.open(output_path, "w", **meta) as dst:
                dst.write(scaled_data)

        print(f"Processed and saved: {filename}")

print("Scaling completed for all bands.")
