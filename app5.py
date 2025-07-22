import geopandas as gpd
import folium
from collections import Counter
import pandas as pd

# === Load data ===
path = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\London\london_2024_epc_predictions_test.geojson"
gdf = gpd.read_file(path)

# === Compute map center ===
center = [gdf.geometry.centroid.y.mean(), gdf.geometry.centroid.x.mean()]

# === Define A–G color mapping ===
rating_colors = {
    'A': '#1a9850', 'B': '#66bd63', 'C': '#a6d96a',
    'D': '#fee08b', 'E': '#fdae61', 'F': '#f46d43', 'G': '#d73027'
}

# === Frequencies and misclassification ===
ratings_order = ['A', 'B', 'C', 'D', 'E', 'F', 'G']
rating_to_code = {r: i for i, r in enumerate(ratings_order)}
actual_counts = dict(Counter(gdf['CURRENT_ENERGY_RATING']))
predicted_counts = dict(Counter(gdf['predicted_rating']))
misclass_1_jump = 0
misclass_gt_1_jump = 0

for _, row in gdf.iterrows():
    actual = row['CURRENT_ENERGY_RATING']
    pred = row['predicted_rating']
    if pd.isna(actual) or pd.isna(pred):
        continue
    diff = abs(rating_to_code[pred] - rating_to_code[actual])
    if diff == 1:
        misclass_1_jump += 1
    elif diff > 1:
        misclass_gt_1_jump += 1

# === Feature & data stats ===
top_features = ['VV_VH_Sum', 'VH', 'L8B10', 'VV_VH_Product', 'BUI', 'B2', 'B3', 'RE_NDVI', 'VV', 'B5']
total_test = len(gdf)
total_train = int(total_test / 0.2 * 0.8)  # Approximating based on 80/20
test_accuracy = 0.570
n_trees = 100

# === Folium map ===
m = folium.Map(location=center, zoom_start=11, tiles="CartoDB positron")

# Style function for polygons
def style_function(feature):
    rating = feature['properties'].get('predicted_rating')
    return {
        'fillColor': rating_colors.get(rating, 'gray'),
        'color': 'black',
        'weight': 0.2,
        'fillOpacity': 0.6
    }

# Add GeoJSON layer
folium.GeoJson(
    gdf,
    name='Predicted Ratings (A–G)',
    style_function=style_function,
    tooltip=folium.GeoJsonTooltip(
        fields=['CURRENT_ENERGY_RATING', 'predicted_rating'],
        aliases=['Original Rating:', 'Predicted Rating:'],
        sticky=True
    )
).add_to(m)

# === Legend and summary box ===
legend_items = ""
for r in ratings_order:
    color = rating_colors.get(r, 'gray')
    pred_count = predicted_counts.get(r, 0)
    actual_count = actual_counts.get(r, 0)
    legend_items += f'<i style="background:{color};width:12px;height:12px;display:inline-block;margin-right:5px;"></i> {r} — Predicted: {pred_count} | Actual: {actual_count}<br>'

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
    width: 350px;
    max-height: 90vh;
    overflow-y: auto;
    box-shadow: 0 0 12px rgba(0,0,0,0.3);
">
<b>🔍 Model Summary</b><br>
<b>Train/Test Split:</b> 80/20<br>
<b>Train Set Size:</b> {total_train}<br>
<b>Test Set Size:</b> {total_test}<br>
<b>Test Accuracy:</b> {test_accuracy:.3f}<br>
<b>Random Forest Trees:</b> {n_trees}<br><br>

<b>Misclassifications:</b><br>
• 1-Class Jump: {misclass_1_jump}<br>
• >1-Class Jump: {misclass_gt_1_jump}<br><br>

<b>Top 10 Features (RF):</b><br>
{", ".join(top_features)}<br><br>

<b>Ratings Breakdown:</b><br>
{legend_items}
</div>
"""

m.get_root().html.add_child(folium.Element(legend_html))

# === Save map ===
output_html = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Maps\map_predicted_rating_test.html"
m.save(output_html)
print(f"✅ Map saved to: {output_html}")
