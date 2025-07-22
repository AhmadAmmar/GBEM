from osgeo import gdal
import os

# Input raster file paths
raster1_path = "D:/OneDrive - Ulster University/PhD/Data/LondonS2/s2Median_Composite_2024_London-0000000000-0000000000.tif"  # Replace with the path to your first raster
raster2_path = "D:/OneDrive - Ulster University/PhD/Data/LondonS2/s2Median_Composite_2024_London-0000000000-0000007424.tif"  # Replace with the path to your second raster

# Output raster file path
output_mosaic_path = "D:/OneDrive - Ulster University/PhD/Data/LondonS2/london.tif"  # Replace with your desired output path

# List of input raster file paths
input_rasters = [raster1_path, raster2_path]

# Create a virtual raster to merge the inputs
vrt_path = "temporary_mosaic.vrt"
vrt_options = gdal.BuildVRTOptions(resampleAlg="nearest")  # Adjust resampling method if needed
gdal.BuildVRT(vrt_path, input_rasters, options=vrt_options)

# Translate the virtual raster to a GeoTIFF without compression
translate_options = gdal.TranslateOptions(format="GTiff")
gdal.Translate(output_mosaic_path, vrt_path, options=translate_options)

# Clean up the temporary VRT file
os.remove(vrt_path)

print(f"Mosaic created and saved to: {output_mosaic_path}")