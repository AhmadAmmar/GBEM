import geopandas as gpd
import folium
from collections import Counter
import pandas as pd

# === Load data ===
path = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\London\london_2024_epc_predictions.geojson"
gdf = gpd.read_file(path)

# === Compute map center ===
center = [gdf.geometry.centroid.y.mean(), gdf.geometry.centroid.x.mean()]

# === Define color mapping for A–G ===
rating_colors = {
    'A': '#1a9850', 'B': '#66bd63', 'C': '#a6d96a',
    'D': '#fee08b', 'E': '#fdae61', 'F': '#f46d43', 'G': '#d73027'
}

# === Frequencies ===
actual_counts = dict(Counter(gdf['CURRENT_ENERGY_RATING']))
predicted_counts = dict(Counter(gdf['predicted_rating']))

# === Misclassification (more than 1-class deviation) ===
ratings_order = ['A', 'B', 'C', 'D', 'E', 'F', 'G']
rating_to_code = {r: i for i, r in enumerate(ratings_order)}

misclassified = 0
for _, row in gdf.iterrows():
    actual = row['CURRENT_ENERGY_RATING']
    pred = row['predicted_rating']
    if pd.isna(actual) or pd.isna(pred):
        continue
    diff = abs(rating_to_code[pred] - rating_to_code[actual])
    if diff > 1:
        misclassified += 1

# === Top 10 features from previous model ===
top_features = [
    'VV_VH_Sum', 'VH', 'L8B10', 'VV_VH_Product', 'BUI',
    'B2', 'B3', 'RE_NDVI', 'VV', 'B5'
]

# === Create Folium Map ===
m = folium.Map(location=center, zoom_start=11, tiles="CartoDB positron")

# === Add buildings layer with predicted color ===
def style_function(feature):
    rating = feature['properties'].get('predicted_rating')
    return {
        'fillColor': rating_colors.get(rating, 'gray'),
        'color': 'black',
        'weight': 0.2,
        'fillOpacity': 0.6
    }

tooltip_fields = ['CURRENT_ENERGY_RATING', 'predicted_rating']
tooltip_aliases = ['Original Rating:', 'Predicted Rating:']

folium.GeoJson(
    gdf,
    name='Predicted Ratings (A–G)',
    style_function=style_function,
    tooltip=folium.GeoJsonTooltip(fields=tooltip_fields, aliases=tooltip_aliases)
).add_to(m)

# === Create Legend HTML ===
legend_html = f"""
<div style="
    position: fixed;
    bottom: 30px;
    left: 30px;
    z-index: 9999;
    background-color: rgba(255, 255, 255, 0.92);
    padding: 15px;
    border-radius: 8px;
    font-size: 13px;
    width: 280px;
    max-height: 90vh;
    overflow-y: auto;
    box-shadow: 0 0 12px rgba(0,0,0,0.3);
">
<b>🔍 Model Overview</b><br>
<b>Accuracy (A–G):</b> 0.570<br>
<b>Misclassified (>1 class off):</b> {misclassified}<br><br>

<b>Top 10 Features:</b><br>
<ul style="margin-left: -20px;">
    {''.join(f"<li>{feat}</li>" for feat in top_features)}
</ul>

<b>Original Ratings Count:</b><br>
<ul style="margin-left: -20px;">
    {''.join(f"<li>{r}: {actual_counts.get(r, 0)}</li>" for r in ratings_order)}
</ul>

<b>Predicted Ratings Count:</b><br>
<ul style="margin-left: -20px;">
    {''.join(f"<li>{r}: {predicted_counts.get(r, 0)}</li>" for r in ratings_order)}
</ul>
</div>
"""

# === Add legend to map ===
m.get_root().html.add_child(folium.Element(legend_html))

# === Save the map ===
output_html = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Maps\map_predicted_rating.html"
m.save(output_html)
print(f"✅ Map saved to: {output_html}")
