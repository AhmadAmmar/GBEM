import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.affinity import scale

# --- Step 1: Load boundaries ---
# You can replace these with actual shapefile/GeoJSON paths.
# For demonstration, we'll use built-in Natural Earth data.
world = gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))

# Filter for United Kingdom, then clip approximate geometries
uk = world[world['name'] == 'United Kingdom']

# In practice, replace with actual boundaries of Greater London & Belfast
# For example:
# london = gpd.read_file("greater_london_boundary.geojson")
# belfast = gpd.read_file("belfast_boundary.geojson")

# --- Approximate geometries ---
# Using bounding boxes instead (replace with real data!)
from shapely.geometry import Polygon

# Rough bounding boxes (degrees, approx):
# Greater London ~ 1572 km²
london_geom = Polygon([(-0.6, 51.2), (0.4, 51.2), (0.4, 51.8), (-0.6, 51.8)])
# Belfast ~ 132 km²
belfast_geom = Polygon([(-5.98, 54.55), (-5.85, 54.55), (-5.85, 54.65), (-5.98, 54.65)])

london = gpd.GeoDataFrame(geometry=[london_geom], crs="EPSG:4326")
belfast = gpd.GeoDataFrame(geometry=[belfast_geom], crs="EPSG:4326")

# --- Step 2: Reproject to equal-area CRS for area calculation ---
london = london.to_crs("EPSG:6933")
belfast = belfast.to_crs("EPSG:6933")

london_area = london.geometry.area.iloc[0] / 1e6  # km²
belfast_area = belfast.geometry.area.iloc[0] / 1e6  # km²

ratio = london_area / belfast_area
print(f"Greater London area: {london_area:.1f} km²")
print(f"Belfast area: {belfast_area:.1f} km²")
print(f"London is about {ratio:.1f} times the size of Belfast")

# --- Step 3: Visualization ---
# Scale Belfast to fit inside London
scale_factor = (london_area / belfast_area) ** 0.5  # linear scaling for area
belfast_scaled = belfast.copy()
belfast_scaled['geometry'] = belfast_scaled.scale(
    xfact=scale_factor, yfact=scale_factor, origin='center'
)

# Plot
fig, ax = plt.subplots(figsize=(8, 8))
london.boundary.plot(ax=ax, color="blue", linewidth=2, label="Greater London")
belfast_scaled.boundary.plot(ax=ax, color="red", linestyle="--", label="Belfast (scaled)")
plt.title(f"How many Belfasts fit in Greater London? ~{ratio:.1f} times")
plt.legend()
plt.show()
