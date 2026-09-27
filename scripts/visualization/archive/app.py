import geopandas as gpd
import folium
from folium.plugins import DualMap
import branca.colormap as cm
import os

# === Load your GeoDataFrame ===
path = r"D:\OneDrive - Ulster University\PhD\data\london\london_2024_epc_predictions.geojson"
gdf = gpd.read_file(path)

# === Filter columns we need ===
gdf = gdf[['geometry', 'id', 'predicted_rating', 'predicted_class']]

# === Center of London ===
center_lat = gdf.geometry.centroid.y.mean()
center_lon = gdf.geometry.centroid.x.mean()

# === Initialize Split-Screen Map ===
m = DualMap(location=[center_lat, center_lon], zoom_start=10)

# === Define Color Maps ===
ag_palette = {
    'A': '#1a9850',
    'B': '#66bd63',
    'C': '#a6d96a',
    'D': '#fdae61',
    'E': '#f46d43',
    'F': '#d73027',
    'G': '#a50026'
}
binary_palette = {
    1: '#1a9850',  # Efficient
    0: '#d73027'   # Inefficient
}

# === Helper: Style function ===
def style_function_ag(feature):
    code = feature['properties']['predicted_rating']
    return {
        'fillColor': ag_palette.get(code, '#cccccc'),
        'color': 'black',
        'weight': 0.2,
        'fillOpacity': 0.6
    }

def style_function_binary(feature):
    cls = feature['properties']['predicted_class']
    return {
        'fillColor': binary_palette.get(cls, '#cccccc'),
        'color': 'black',
        'weight': 0.2,
        'fillOpacity': 0.6
    }

# === Add A–G Prediction Layer ===
folium.GeoJson(
    gdf,
    style_function=style_function_ag,
    name="Predicted A–G Rating"
).add_to(m.m1)

# === Add Binary Class Layer ===
folium.GeoJson(
    gdf,
    style_function=style_function_binary,
    name="Efficient vs Inefficient"
).add_to(m.m2)

# === Add Legends ===
legend_ag = cm.StepColormap(
    colors=[ag_palette[k] for k in sorted(ag_palette)],
    index=list(range(8)),
    vmin=0, vmax=7,
    caption="Predicted A–G Rating"
)

legend_binary = cm.StepColormap(
    colors=[binary_palette[k] for k in [0,1]],
    index=[0, 1],
    vmin=0, vmax=1,
    caption="Efficient vs Inefficient"
)

legend_ag.add_to(m.m1)
legend_binary.add_to(m.m2)

# === Save Map ===
output_html = r"D:\OneDrive - Ulster University\PhD\Maps\london_prediction_map_split.html"
os.makedirs(os.path.dirname(output_html), exist_ok=True)
m.save(output_html)

print(f"✅ Map saved to: {output_html}")
