import rasterio
import os

# Input and output paths
input_file = "D:/OneDrive - Ulster University/PhD/data/london/Sat/londonS2.tif"
output_dir = "D:/OneDrive - Ulster University/PhD/data/london/Sat/Bands/"

# Create the output directory if it doesn't exist
os.makedirs(output_dir, exist_ok=True)

# Open the multi-band raster file
with rasterio.open(input_file) as src:
    # Iterate through each band
    for band_idx in range(1, src.count + 1):  # Bands are 1-indexed in rasterio
        # Read the current band
        band_data = src.read(band_idx)
        
        # Create an output path for the current band
        band_file = os.path.join(output_dir, f"B{band_idx}.tif")
        
        # Write the single band to a new GeoTIFF
        with rasterio.open(
            band_file,
            "w",
            driver="GTiff",
            height=src.height,
            width=src.width,
            count=1,  # Single band
            dtype=band_data.dtype,
            crs=src.crs,
            transform=src.transform
        ) as dst:
            dst.write(band_data, 1)  # Write the first (and only) band
        
        print(f"Band {band_idx} saved to: {band_file}")