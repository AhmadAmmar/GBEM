import os
import numpy as np
import rasterio
from PIL import Image

# Define the directory containing the files
directory = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\a2a9a8ac-c897-4caf-81f0-9724169a4da0\visual\20231125T143956000_visual_30_hotsat1"

# Loop over all files in the directory
for filename in os.listdir(directory):
    file_path = os.path.join(directory, filename)
    
    # Process TIFF files
    if filename.lower().endswith((".tiff", ".tif")):
        try:
            with rasterio.open(file_path) as src:
                # Read all bands; data shape will be (bands, rows, cols)
                data = src.read()
                # Compute overall min and max across all bands
                min_val = data.min()
                max_val = data.max()
                print(f"{filename} (TIFF): min = {min_val}, max = {max_val}")
        except Exception as e:
            print(f"Error reading {filename}: {e}")
    
    # Process PNG files
    elif filename.lower().endswith(".png"):
        try:
            with Image.open(file_path) as img:
                # Convert image to numpy array
                data = np.array(img)
                min_val = data.min()
                max_val = data.max()
                print(f"{filename} (PNG): min = {min_val}, max = {max_val}")
        except Exception as e:
            print(f"Error reading {filename}: {e}")
