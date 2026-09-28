import rasterio
import numpy as np
import matplotlib.pyplot as plt
from rasterio.warp import reproject, Resampling
from scipy.stats import pearsonr, linregress

# File paths for the two raster files
hotsat_tiff = r"D:\OneDrive - Ulster University\PhD\data\belfast\hotsat\20230713T005702000_visual_30_hotsat1\20230713T005702000_visual_30_hotsat1.tiff"
landsat_tiff = r"D:\OneDrive - Ulster University\PhD\data\belfast\hotsat\20230713T005702000_visual_30_hotsat1\Landsat8_Thermal_July2023.tif"

# Open the HotSat raster and read the first band
with rasterio.open(hotsat_tiff) as src_h:
    hotsat_data = src_h.read(1)  # read first band
    hotsat_transform = src_h.transform
    hotsat_crs = src_h.crs
    hotsat_nodata = src_h.nodata

# Open the Landsat raster and read the first band
with rasterio.open(landsat_tiff) as src_l:
    landsat_data = src_l.read(1)
    landsat_transform = src_l.transform
    landsat_crs = src_l.crs
    landsat_nodata = src_l.nodata

# If necessary, reproject the Landsat data to match the HotSat grid
if (landsat_crs != hotsat_crs) or (src_l.width != src_h.width or src_l.height != src_h.height):
    landsat_data_reproj = np.empty_like(hotsat_data, dtype=landsat_data.dtype)
    reproject(
        source=landsat_data,
        destination=landsat_data_reproj,
        src_transform=landsat_transform,
        src_crs=landsat_crs,
        dst_transform=hotsat_transform,
        dst_crs=hotsat_crs,
        resampling=Resampling.nearest
    )
    landsat_data = landsat_data_reproj

# Create a mask to exclude no-data/background pixels.
# Use nodata if available; otherwise, assume zero represents no-data.
mask = np.ones(hotsat_data.shape, dtype=bool)
if hotsat_nodata is not None:
    mask &= (hotsat_data != hotsat_nodata)
else:
    mask &= (hotsat_data != 0)
if landsat_nodata is not None:
    mask &= (landsat_data != landsat_nodata)
else:
    mask &= (landsat_data != 0)

# Extract valid pixels from both arrays using the mask
hotsat_valid = hotsat_data[mask].flatten()
landsat_valid = landsat_data[mask].flatten()

# Remove any remaining NaN or infinite values from both arrays
valid_idx = np.isfinite(hotsat_valid) & np.isfinite(landsat_valid)
hotsat_valid = hotsat_valid[valid_idx]
landsat_valid = landsat_valid[valid_idx]

# Compute correlation statistics using scipy
pearson_corr, p_value = pearsonr(hotsat_valid, landsat_valid)
slope, intercept, r_value, p_val, std_err = linregress(hotsat_valid, landsat_valid)

print(f"Pearson correlation coefficient: {pearson_corr:.2f}")
print(f"P-value: {p_value:.2g}")
print(f"Slope: {slope:.2f}")
print(f"Intercept: {intercept:.2f}")

# Create scatter plot
plt.figure(figsize=(8,6))
plt.scatter(hotsat_valid, landsat_valid, s=1, alpha=0.5, label='Pixels')
plt.xlabel('HotSat Thermal DN')
plt.ylabel('Landsat8 Thermal DN')
plt.title('Scatter Plot of HotSat vs. Landsat8 Thermal Data')

# Plot the best-fit regression line
x_vals = np.linspace(hotsat_valid.min(), hotsat_valid.max(), 100)
y_vals = intercept + slope * x_vals
plt.plot(x_vals, y_vals, color='red', label='Fit')

# Annotate the plot with the correlation statistics
plt.text(0.05, 0.95, 
         f'Pearson R = {pearson_corr:.2f}\nSlope = {slope:.2f}\nIntercept = {intercept:.2f}',
         transform=plt.gca().transAxes, verticalalignment='top', 
         bbox=dict(boxstyle='round', facecolor='white', alpha=0.5))

plt.legend()
plt.show()
