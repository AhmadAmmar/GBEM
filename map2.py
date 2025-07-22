import rasterio
import matplotlib.pyplot as plt
import matplotlib.patheffects as PathEffects
import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.patches as mpatches

# -------------------------------------------------------------------
# File paths
# -------------------------------------------------------------------
lst_path = "D:/OneDrive - Ulster University/PhD/Data/London/Sat/L8B10.tif"
epc_csv  = "D:/OneDrive - Ulster University/PhD/Data/London/Certs/certificates_london_sample_100.csv"

out_lst_map       = "D:/OneDrive - Ulster University/PhD/Data/London/Output/london_LST_2024_stretched.png"
out_lst_map_epc   = "D:/OneDrive - Ulster University/PhD/Data/London/Output/london_LST_2024_stretched_with_EPC.png"

# -------------------------------------------------------------------
# 1) Load the LST raster (original, unmodified data)
# -------------------------------------------------------------------
def load_single_band(band_path):
    """Return array data, bounding extent, CRS, and transform from a single-band GeoTIFF."""
    with rasterio.open(band_path) as src:
        band = src.read(1).astype(float)
        extent = src.bounds  # (left, bottom, right, top)
        crs = src.crs
        transform = src.transform
    return band, extent, crs, transform

lst_band, extent_lst, crs_lst, transform_lst = load_single_band(lst_path)
left, bottom, right, top = extent_lst

# -------------------------------------------------------------------
# 2) Compute display range via percentile stretch (2–98%)
# -------------------------------------------------------------------
p2 = np.nanpercentile(lst_band, 2)
p98 = np.nanpercentile(lst_band, 98)

# We'll pass these to imshow (vmin=p2, vmax=p98) to improve contrast.
# The raw data remains intact; only display is clipped at p2–p98.

# (Optional) If your LST is in °C or K, label accordingly.
# We'll assume °C for labeling.

# -------------------------------------------------------------------
# 3) Plot LST (stretched) without EPC
# -------------------------------------------------------------------
figsize_standard = (12, 10)  # matches your Sentinel-2 figure dimensions

fig1, ax1 = plt.subplots(figsize=figsize_standard)

im1 = ax1.imshow(
    lst_band,
    extent=[left, right, bottom, top],
    origin='upper',
    cmap='coolwarm',     # Good diverging colormap for temperature
    vmin=p2,
    vmax=p98,            # Clip display at 2-98% percentile
    zorder=1
)

ax1.set_aspect('equal', adjustable='box')
ax1.set_title("London LST (2024 Composite) - Stretched Display")
ax1.set_xlabel("Longitude")
ax1.set_ylabel("Latitude")
ax1.grid(True)

# Colorbar to show p2 -> p98 range
cbar1 = plt.colorbar(im1, ax=ax1, fraction=0.03, pad=0.04)
cbar1.set_label("Land Surface Temperature (°C) - 2024 (Stretched)")

plt.tight_layout()
plt.savefig(out_lst_map, dpi=300, bbox_inches='tight')
plt.close(fig1)
print(f"LST map (stretched) saved to: {out_lst_map}")

# -------------------------------------------------------------------
# 4) Load EPC data & convert to GeoDataFrame
# -------------------------------------------------------------------
epc_data = pd.read_csv(epc_csv)

rating_colors = {
    'A': 'green',
    'B': 'lime',
    'C': 'yellow',
    'D': 'orange',
    'E': 'orangered',
    'F': 'red',
    'G': 'darkred'
}

epc_gdf = gpd.GeoDataFrame(
    epc_data,
    geometry=gpd.points_from_xy(epc_data['LONGITUDE'], epc_data['LATITUDE']),
    crs="EPSG:4326"
)
# If needed, reproject:
# if crs_lst != epc_gdf.crs:
#     epc_gdf = epc_gdf.to_crs(crs_lst)

# -------------------------------------------------------------------
# 5) Plot LST (stretched) with EPC overlay
# -------------------------------------------------------------------
fig2, ax2 = plt.subplots(figsize=figsize_standard)

im2 = ax2.imshow(
    lst_band,
    extent=[left, right, bottom, top],
    origin='upper',
    cmap='coolwarm',
    vmin=p2,  # percentile clipped
    vmax=p98,
    zorder=1
)
ax2.set_aspect('equal', adjustable='box')
ax2.set_title("London LST (2024 Composite) + EPC - Stretched Display")
ax2.set_xlabel("Longitude")
ax2.set_ylabel("Latitude")
ax2.grid(True)

# Overlay EPC letters with halos
for idx, row in epc_gdf.iterrows():
    rating = row['CURRENT_ENERGY_RATING']
    x_coord = row.geometry.x
    y_coord = row.geometry.y
    letter_color = rating_colors.get(rating, 'black')
    
    txt = ax2.text(
        x_coord, 
        y_coord,
        rating,
        fontsize=7,
        fontweight='bold',
        color=letter_color,
        ha='center',
        va='center',
        zorder=2
    )
    txt.set_path_effects([
        PathEffects.withStroke(linewidth=2, foreground='black')
    ])

# Add colorbar (p2 -> p98)
cbar2 = plt.colorbar(im2, ax=ax2, fraction=0.03, pad=0.04)
cbar2.set_label("Land Surface Temperature (°C) - 2024 (Stretched)")

# Legend for EPC colors
legend_patches = []
for rat, col in rating_colors.items():
    patch = mpatches.Patch(color=col, label=f"Rating {rat}")
    legend_patches.append(patch)

plt.legend(handles=legend_patches, title="Energy Ratings", loc='lower right', fontsize=8)

plt.tight_layout()
plt.savefig(out_lst_map_epc, dpi=300, bbox_inches='tight')
plt.close(fig2)
print(f"LST map with EPC (stretched) saved to: {out_lst_map_epc}")
