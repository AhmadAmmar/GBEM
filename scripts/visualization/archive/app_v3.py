import geopandas as gpd
import folium
from branca.element import Template, MacroElement

# === Load test data with predictions ===
path = r"D:\OneDrive - Ulster University\PhD\data\london\london_2024_epc_predictions.geojson"
gdf = gpd.read_file(path)

# === Define center of map ===
center = [gdf.geometry.centroid.y.mean(), gdf.geometry.centroid.x.mean()]

# === Define color mapping for A–G ===
rating_colors = {
    'A': '#1a9850',  # green
    'B': '#66bd63',
    'C': '#a6d96a',
    'D': '#fee08b',
    'E': '#fdae61',
    'F': '#f46d43',
    'G': '#d73027'   # red
}

# === Create Folium map ===
m = folium.Map(location=center, zoom_start=11, tiles="CartoDB positron")

# === Add buildings layer ===
def style_function(feature):
    rating = feature['properties']['predicted_rating']
    return {
        'fillColor': rating_colors.get(rating, 'gray'),
        'color': 'black',
        'weight': 0.2,
        'fillOpacity': 0.6
    }

folium.GeoJson(
    gdf,
    name='Predicted Ratings (A–G)',
    style_function=style_function,
    tooltip=folium.GeoJsonTooltip(fields=[
        'CURRENT_ENERGY_RATING', 'predicted_rating'
    ],
    aliases=[
        'Original Rating:', 'Predicted Rating:'
    ],
    sticky=True)
).add_to(m)

# === Add floating legend box ===
legend_html = """
<div style="
    position: fixed;
    bottom: 30px;
    left: 30px;
    z-index: 9999;
    background-color: rgba(255, 255, 255, 0.85);
    padding: 15px;
    border-radius: 8px;
    font-size: 14px;
    box-shadow: 0 0 10px rgba(0,0,0,0.3);
    ">
    <b>Legend: Predicted Energy Rating</b><br>
    <i style="background:#1a9850;width:12px;height:12px;display:inline-block"></i> A<br>
    <i style="background:#66bd63;width:12px;height:12px;display:inline-block"></i> B<br>
    <i style="background:#a6d96a;width:12px;height:12px;display:inline-block"></i> C<br>
    <i style="background:#fee08b;width:12px;height:12px;display:inline-block"></i> D<br>
    <i style="background:#fdae61;width:12px;height:12px;display:inline-block"></i> E<br>
    <i style="background:#f46d43;width:12px;height:12px;display:inline-block"></i> F<br>
    <i style="background:#d73027;width:12px;height:12px;display:inline-block"></i> G<br>
    <br>
    <b>Model Info:</b><br>
    Accuracy (A–G): 0.570<br>
    Features: Top 10 based on RF<br>
</div>
"""

m.get_root().html.add_child(folium.Element(legend_html))

# === Save to HTML ===
output_html = r"D:\OneDrive - Ulster University\PhD\Maps\map_predicted_rating.html"
m.save(output_html)
print(f"✅ Map saved to: {output_html}")
