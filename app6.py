import geopandas as gpd
import folium
from collections import Counter
import pandas as pd

# === Load data (entire dataset with predictions) ===
path = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\London\london_2024_epc_predictions.geojson"
gdf = gpd.read_file(path)

# === Compute map center ===
center = [gdf.geometry.centroid.y.mean(), gdf.geometry.centroid.x.mean()]

# === Binary color mapping: Efficient vs Inefficient ===
class_colors = {
    1: '#1a9850',  # Efficient → Green
    0: '#d73027'   # Inefficient → Red
}

# === Class counts and stats ===
class_counts = dict(Counter(gdf['predicted_class']))
actual_counts = dict(Counter(gdf['EFFICIENCY_CLASS']))
total_test = 21991  # From previous test set
total_train = 87964
test_accuracy = 0.661
n_trees = 100
top_features_bin = ['VV_VH_Sum', 'VH', 'L8B10', 'BUI', 'SWIR_NDWI',
                    'B2', 'VV_VH_Product', 'B3', 'RE_NDVI', 'B12']

# === Folium map ===
m = folium.Map(location=center, zoom_start=11, tiles="CartoDB positron")

# Style function
def style_function(feature):
    cls = feature['properties'].get('predicted_class')
    return {
        'fillColor': class_colors.get(cls, 'gray'),
        'color': 'black',
        'weight': 0.2,
        'fillOpacity': 0.6
    }

# Add layer
folium.GeoJson(
    gdf,
    name='Predicted Binary Classification',
    style_function=style_function,
    tooltip=folium.GeoJsonTooltip(
        fields=['EFFICIENCY_CLASS', 'predicted_class'],
        aliases=['Original Class (0/1):', 'Predicted Class (0/1):'],
        sticky=True
    )
).add_to(m)

# === Legend and info panel ===
legend_html = f"""
<div style="
    position: fixed;
    bottom: 30px;
    left: 30px;
    z-index: 9999;
    background-color: rgba(255, 255, 255, 0.95);
    padding: 15px;
    border-radius: 8px;
    font-size: 13px;
    width: 320px;
    max-height: 90vh;
    overflow-y: auto;
    box-shadow: 0 0 12px rgba(0,0,0,0.3);
">
<b>🔍 Model Summary (Binary)</b><br>
<b>Train/Test Split:</b> 80/20<br>
<b>Train Set Size:</b> {total_train}<br>
<b>Test Set Size:</b> {total_test}<br>
<b>Test Accuracy:</b> {test_accuracy:.3f}<br>
<b>Random Forest Trees:</b> {n_trees}<br><br>

<b>Top 10 Features (RF):</b><br>
{", ".join(top_features_bin)}<br><br>

<b>Classification Breakdown:</b><br>
<i style="background:{class_colors[1]};width:12px;height:12px;display:inline-block;margin-right:5px;"></i> Efficient (1) — Predicted: {class_counts.get(1, 0)} | Actual: {actual_counts.get(1, 0)}<br>
<i style="background:{class_colors[0]};width:12px;height:12px;display:inline-block;margin-right:5px;"></i> Inefficient (0) — Predicted: {class_counts.get(0, 0)} | Actual: {actual_counts.get(0, 0)}<br>
</div>
"""

m.get_root().html.add_child(folium.Element(legend_html))

# === Save map ===
output_path = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Maps\map_predicted_class.html"
m.save(output_path)
print(f"✅ Binary classification map saved to:\n{output_path}")
