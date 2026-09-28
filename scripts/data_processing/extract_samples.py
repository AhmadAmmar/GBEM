import pandas as pd
import rasterio
from multiprocessing import Pool, cpu_count
from tqdm import tqdm

# File paths
certificates_file = "D:/OneDrive - Ulster University/PhD/data/london/london_filtered_2024.csv"
output_file = "D:/OneDrive - Ulster University/PhD/data/london/london_samples_2024.csv"

# Satellite band raster files
rasters = {
    "B2": "D:/OneDrive - Ulster University/PhD/data/london/Sat/B2.tif",
    "B3": "D:/OneDrive - Ulster University/PhD/data/london/Sat/B3.tif",
    "B4": "D:/OneDrive - Ulster University/PhD/data/london/Sat/B4.tif",
    "B5": "D:/OneDrive - Ulster University/PhD/data/london/Sat/B5.tif",
    "B6": "D:/OneDrive - Ulster University/PhD/data/london/Sat/B6.tif",
    "B7": "D:/OneDrive - Ulster University/PhD/data/london/Sat/B7.tif",
    "B8": "D:/OneDrive - Ulster University/PhD/data/london/Sat/B8.tif",
    "B8A": "D:/OneDrive - Ulster University/PhD/data/london/Sat/B8A.tif",
    "B11": "D:/OneDrive - Ulster University/PhD/data/london/Sat/B11.tif",
    "B12": "D:/OneDrive - Ulster University/PhD/data/london/Sat/B12.tif",
    "VV": "D:/OneDrive - Ulster University/PhD/data/london/Sat/VV.tif",
    "VH": "D:/OneDrive - Ulster University/PhD/data/london/Sat/VH.tif",
    "L8B10": "D:/OneDrive - Ulster University/PhD/data/london/Sat/L8B10.tif",
}

# Load certificates
print("Loading certificates dataset...")
certificates = pd.read_csv(certificates_file)
coords = certificates[["LONGITUDE", "LATITUDE"]].values  # Extract coordinates once

def process_raster(args):
    """Function to process a single raster in parallel."""
    band_name, raster_file = args
    with rasterio.open(raster_file) as src:
        values = []
        for lon, lat in coords:
            try:
                row_idx, col_idx = src.index(lon, lat)
                value = src.read(1)[row_idx, col_idx]
                values.append(value)
            except Exception:
                values.append(float('nan'))
    return band_name, values

# Parallel processing
if __name__ == "__main__":
    print("Extracting satellite band values in parallel...")
    with Pool(cpu_count() - 1) as pool:  # Use all but one CPU core
        results = list(tqdm(pool.imap(process_raster, rasters.items()), total=len(rasters)))

    # Add results to the dataframe
    for band_name, values in results:
        certificates[band_name] = values

    # Save the output
    print(f"Saving the output to {output_file}...")
    certificates.to_csv(output_file, index=False)
    print("Satellite samples extracted successfully!")
