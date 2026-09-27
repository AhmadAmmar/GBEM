import geopandas as gpd
import rasterio
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
import matplotlib.patheffects as PathEffects
import pandas as pd
import numpy as np
import math

# -------------------------------------------------------------------
# File Paths
# -------------------------------------------------------------------
vv_path = "D:/OneDrive - Ulster University/PhD/data/london/Sat/VV.tif"
vh_path = "D:/OneDrive - Ulster University/PhD/data/london/Sat/VH.tif"

epc_csv = "D:/OneDrive - Ulster University/PhD/data/london/Certs/certificates_london_sample_100.csv"
london_shp = "D:/OneDrive - Ulster University/PhD/data/london/SHP/london.shp"

output_map_with_epc = "D:/OneDrive - Ulster University/PhD/data/london/Output/london_s1_falsecolor_with_epc.png"
output_map_without_epc = "D:/OneDrive - Ulster University/PhD/data/london/Output/london_s1_falsecolor_without_epc.png"

# -------------------------------------------------------------------
# Load EPC Data
# -------------------------------------------------------------------
epc_data = pd.read_csv(epc_csv)

rating_colors = {
    "A": "#00ff00",
    "B": "#7fff00",
    "C": "#ffff00",
    "D": "#ffbf00",
    "E": "#ff8000",
    "F": "#ff4000",
    "G": "#ff0000",
}

# -------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------
def load_band(band_path):
    with rasterio.open(band_path) as src:
        band = src.read(1).astype(float)
        extent = src.bounds
        crs = src.crs
        transform = src.transform
    return band, extent, crs, transform


def stretch_band(band, low=2, high=98):
    b_min, b_max = np.nanpercentile(band, [low, high])
    stretched = (band - b_min) / (b_max - b_min)
    return np.clip(stretched, 0, 1)


def add_scale_bar_with_cm_divisions(ax, extent, fig, distance_km=5, bar_y_frac=0.09, color="white", max_cm_ticks=5):
    left, bottom, right, top = extent
    lat_center = (bottom + top) / 2.0
    km_per_deg_lon = 111.32 * math.cos(math.radians(lat_center))
    deg_len_for_bar = distance_km / km_per_deg_lon
    bar_left = left + 0.03 * (right - left)
    bar_right = bar_left + deg_len_for_bar
    bar_y = bottom + bar_y_frac * (top - bottom)
    dpi = fig.dpi
    fig_w_in = fig.get_size_inches()[0]
    fig_w_px = fig_w_in * dpi
    deg_per_px = (right - left) / fig_w_px
    km_per_px = deg_per_px * km_per_deg_lon
    px_in_one_cm = (1.0 / 2.54) * dpi
    km_per_cm = km_per_px * px_in_one_cm

    ax.plot([bar_left, bar_right], [bar_y, bar_y], color=color, linewidth=3, zorder=3)
    mid_x = (bar_left + bar_right) / 2.0
    label_above_y = bar_y + 0.005 * (top - bottom)
    ax.text(
        mid_x,
        label_above_y,
        f"{distance_km} km",
        color=color,
        fontsize=9,
        fontweight="bold",
        ha="center",
        va="bottom",
        zorder=4,
    )
    deg_in_one_cm = deg_per_px * px_in_one_cm
    bar_px = deg_len_for_bar / deg_per_px
    total_bar_cm = bar_px / px_in_one_cm
    n_cm = min(int(total_bar_cm), max_cm_ticks)
    tick_height = 0.01 * (top - bottom)

    for i in range(1, n_cm + 1):
        x_tick = bar_left + i * deg_in_one_cm
        if x_tick > bar_right:
            break
        ax.plot([x_tick, x_tick], [bar_y - tick_height / 2, bar_y + tick_height / 2], color="black", linewidth=1, zorder=4)

    label_below_y = bar_y - 0.012 * (top - bottom)
    scale_text = f"1 cm ≈ {km_per_cm:.1f} km\n(EPSG:4326)"
    ax.text(
        mid_x,
        label_below_y,
        scale_text,
        color=color,
        fontsize=8,
        ha="center",
        va="top",
        zorder=4,
    )


def add_north_arrow(ax, x=0.02, y=0.98, length=0.05, label="N"):
    ax.annotate(
        label,
        xy=(x, y),
        xytext=(x, y - length),
        arrowprops=dict(facecolor="white", edgecolor="white", width=2, headwidth=8),
        ha="center",
        va="center",
        fontsize=10,
        color="white",
        xycoords=ax.transAxes,
        textcoords=ax.transAxes,
        zorder=3,
    )


def add_locator_inset(fig, ax, london_shp, inset_position=[0.875, 0.4, 0.12, 0.12]):
    london_boundary = gpd.read_file(london_shp)
    if london_boundary.crs is None:
        london_boundary.set_crs(epsg=4326, inplace=True)
    else:
        london_boundary = london_boundary.to_crs(epsg=4326)

    world = gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))

    inset_ax = fig.add_axes(inset_position)  # Positioned above the EPC legend
    inset_ax.set_facecolor("black")
    world.plot(ax=inset_ax, color="lightgray", edgecolor="white", linewidth=0.5)

    uk_box = mpatches.Rectangle(
        xy=(-10, 49), width=12, height=10, facecolor="none", edgecolor="white", linewidth=1.2, zorder=2
    )
    inset_ax.add_patch(uk_box)

    london_boundary.plot(ax=inset_ax, color="none", edgecolor="red", linewidth=0.7, zorder=3)

    inset_ax.set_xlim(-15, 10)
    inset_ax.set_ylim(45, 61)
    inset_ax.set_xticks([])
    inset_ax.set_yticks([])
    inset_ax.set_title("Locator", fontsize=10, color="white")
    for spine in inset_ax.spines.values():
        spine.set_edgecolor("white")


def plot_map(rgb_composite, extent, epc=None, title="", output_path="", show_legend=False, london_shp=None):
    fig, ax = plt.subplots(figsize=(12, 10))
    fig.patch.set_facecolor("black")
    ax.set_facecolor("black")

    ax.imshow(rgb_composite, extent=[extent.left, extent.right, extent.bottom, extent.top], origin="upper")
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(title, color="white", fontsize=14)
    ax.set_xlabel("Longitude", color="white")
    ax.set_ylabel("Latitude", color="white")
    ax.grid(True, color="white", linewidth=0.4, alpha=0.5)
    ax.tick_params(axis="both", colors="white")

    if epc is not None:
        for idx, row in epc.iterrows():
            rating = row["CURRENT_ENERGY_RATING"]
            x, y = row.geometry.x, row.geometry.y
            c = rating_colors.get(rating, "white")
            txt = ax.text(
                x, y, rating, fontsize=7, fontweight="bold", color=c, ha="center", va="center", zorder=2
            )
            txt.set_path_effects([PathEffects.withStroke(linewidth=2, foreground="black")])

        rating_handles = []
        for rat, col in rating_colors.items():
            mk = mlines.Line2D(
                [], [], marker="o", markersize=8, markerfacecolor=col, markeredgecolor="white", linewidth=0, label=f"Rating {rat}"
            )
            rating_handles.append(mk)

        ratings_legend = ax.legend(
            handles=rating_handles,
            title="Energy Ratings",
            loc="lower right",
            facecolor="black",
            edgecolor="white",
            fontsize=8,
        )
        for txtobj in ratings_legend.get_texts():
            txtobj.set_color("white")
        if ratings_legend.get_title():
            ratings_legend.get_title().set_color("white")
        ax.add_artist(ratings_legend)

    if show_legend:
        band_legend_handles = [
            mpatches.Patch(color="red", label="Red → VV"),
            mpatches.Patch(color="green", label="Green → VH"),
            mpatches.Patch(color="blue", label="Blue → ND (VV - VH)"),
        ]
        band_legend = ax.legend(
            handles=band_legend_handles,
            title="Band Mapping",
            loc="upper right",
            facecolor="black",
            edgecolor="white",
            fontsize=8,
        )
        for txtobj in band_legend.get_texts():
            txtobj.set_color("white")
        if band_legend.get_title():
            band_legend.get_title().set_color("white")
        ax.add_artist(band_legend)

    add_scale_bar_with_cm_divisions(ax, extent, fig, distance_km=5, bar_y_frac=0.09, color="white", max_cm_ticks=5)
    add_north_arrow(ax, x=0.02, y=0.98, length=0.05, label="N")

    if london_shp:
        add_locator_inset(fig, ax, london_shp)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Map saved to: {output_path}")


# -------------------------------------------------------------------
# Main Code
# -------------------------------------------------------------------
# Load Sentinel-1 VV and VH Bands
vv, extent, _, _ = load_band(vv_path)
vh, _, _, _ = load_band(vh_path)

# Perform band math: Normalized Difference (ND = (VV - VH) / (VV + VH))
nd = np.divide(vv - vh, vv + vh, out=np.zeros_like(vv), where=(vv + vh) != 0)

# Stretch bands for visualization
vv_s = stretch_band(vv)
vh_s = stretch_band(vh)
nd_s = stretch_band(nd)

# Create false color composite (RGB = [VV, VH, ND])
rgb_composite = np.dstack((vv_s, vh_s, nd_s))

# EPC GeoDataFrame
epc_df = gpd.GeoDataFrame(
    epc_data, geometry=gpd.points_from_xy(epc_data["LONGITUDE"], epc_data["LATITUDE"]), crs="EPSG:4326"
)

# Map with EPC and legend
plot_map(rgb_composite, extent, epc=epc_df, title="Greater London Sentinel-1 False Color + EPC", output_path=output_map_with_epc, show_legend=True, london_shp=london_shp)

# Map without EPC
plot_map(rgb_composite, extent, epc=None, title="Greater London Sentinel-1 False Color", output_path=output_map_without_epc, show_legend=True, london_shp=london_shp)
