import os
import numpy as np
import rasterio
from rasterio.enums import Resampling
from skimage.feature import graycomatrix, graycoprops
from skimage.util import img_as_ubyte
from tqdm import tqdm

# === Paths ===
base_folder = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\London\Sat"

# === Helpers ===
def read_band(name):
    path = os.path.join(base_folder, f"{name}.tif")
    with rasterio.open(path) as src:
        data = src.read(1).astype("float32")
        profile = src.profile
    return data, profile

def write_raster(data, profile, name):
    out_path = os.path.join(base_folder, f"{name}.tif")
    profile.update(dtype='float32', count=1, compress='lzw')
    with rasterio.open(out_path, 'w', **profile) as dst:
        dst.write(data, 1)
    print(f"✅ Saved: {name}.tif")

def safe_div(numer, denom):
    with np.errstate(divide='ignore', invalid='ignore'):
        result = np.true_divide(numer, denom)
        result[~np.isfinite(result)] = np.nan
    return result

# === Read required bands ===
b2, prof = read_band("B2")
b3, _ = read_band("B3")
b4, _ = read_band("B4")
b5, _ = read_band("B5")
b6, _ = read_band("B6")
b7, _ = read_band("B7")
b8, _ = read_band("B8")
b8a, _ = read_band("B8A")
b11, _ = read_band("B11")
b12, _ = read_band("B12")
vv, _ = read_band("VV")
vh, _ = read_band("VH")

# === Vegetation / Water Indices ===
ndvi = safe_div(b8 - b4, b8 + b4)
gndvi = safe_div(b8 - b3, b8 + b3)
evi = 2.5 * safe_div(b8 - b4, b8 + 6*b4 - 7.5*b2 + 1)
savi = safe_div(b8 - b4, b8 + b4 + 0.5) * (1 + 0.5)
lswi = safe_div(b8 - b11, b8 + b11)
ndwi = safe_div(b3 - b8, b3 + b8)

# === Urban / Built-Up Indices ===
ndbi = safe_div(b11 - b8, b11 + b8)
ui = safe_div(ndbi - ndvi, ndbi + ndvi)
ibi = ui * safe_div((b11 + b4), (b8 + b2))
bui = ndbi - ndvi
albedo = (b2 + b4 + b6) / 3
brightness = np.sqrt((b2**2 + b4**2) / 2)

# === Extended Red Edge / SWIR Indices ===
re_ndvi = safe_div(b8a - b5, b8a + b5)
moisture_index = safe_div(b8a - b12, b8a + b12)
swir_ndwi = safe_div(b3 - b12, b3 + b12)

# === SAR Indices ===
vv_vh_sum = vv + vh
vv_vh_diff = vv - vh
vv_vh_prod = vv * vh
vv_vh_nd = safe_div(vv - vh, vv + vh)
vv_prop = safe_div(vv, vv + vh)
vh_prop = safe_div(vh, vv + vh)
api = vv**2 - vh**2

# === Save all standard indices ===
indices = {
    "NDVI": ndvi, "GNDVI": gndvi, "EVI": evi, "SAVI": savi,
    "LSWI": lswi, "NDWI": ndwi, "NDBI": ndbi, "UI": ui, "IBI": ibi, "BUI": bui,
    "Albedo_Proxy": albedo, "Brightness_Index": brightness,
    "RE_NDVI": re_ndvi, "Moisture_Index": moisture_index, "SWIR_NDWI": swir_ndwi,
    "VV_VH_Sum": vv_vh_sum, "VV_VH_Difference": vv_vh_diff, "VV_VH_Product": vv_vh_prod,
    "VV_VH_Normalized_Difference": vv_vh_nd, "VV_Proportion": vv_prop,
    "VH_Proportion": vh_prop, "Advanced_Polarization_Index": api
}

for name, arr in indices.items():
    write_raster(arr, prof, name)

# === SAR Texture Metrics ===
def compute_texture_metrics(band, name_prefix, profile, window=5):
    print(f"📊 Computing SAR texture metrics for {name_prefix}...")

    band_scaled = np.nan_to_num(img_as_ubyte(safe_div(band, np.nanmax(band))))
    height, width = band_scaled.shape

    # Initialize empty arrays
    contrast = np.zeros_like(band_scaled, dtype='float32')
    dissimilarity = np.zeros_like(band_scaled, dtype='float32')
    entropy = np.zeros_like(band_scaled, dtype='float32')

    offset = window // 2

    # Loop through pixels
    for i in tqdm(range(offset, height - offset)):
        for j in range(offset, width - offset):
            patch = band_scaled[i-offset:i+offset+1, j-offset:j+offset+1]
            glcm = graycomatrix(patch, [1], [0], levels=256, symmetric=True, normed=True)
            contrast[i, j] = graycoprops(glcm, 'contrast')[0, 0]
            dissimilarity[i, j] = graycoprops(glcm, 'dissimilarity')[0, 0]
            entropy[i, j] = -np.sum(glcm * np.log2(glcm + 1e-10))

    write_raster(contrast, profile, f"{name_prefix}_contrast")
    write_raster(dissimilarity, profile, f"{name_prefix}_dissimilarity")
    write_raster(entropy, profile, f"{name_prefix}_entropy")

# Run for VV and VH
compute_texture_metrics(vv, "VV", prof)
compute_texture_metrics(vh, "VH", prof)

print("\n🏁 All index and SAR texture raster files successfully generated!")
