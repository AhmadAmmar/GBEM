import geopandas as gpd
import pandas as pd
import folium
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

# === Load your dataset ===
path = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\London\london_2024_epc_with_polygons.geojson"
gdf = gpd.read_file(path)

# === Columns
target_multiclass = 'CURRENT_ENERGY_RATING'
target_binary = 'EFFICIENCY_CLASS'
feature_cols = [
    'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B11', 'B12',
    'VV', 'VH', 'L8B10',
    'NDVI', 'NDBI', 'UI', 'IBI', 'EVI', 'NDWI', 'GNDVI',
    'VV_VH_Sum', 'VV_VH_Difference', 'VV_VH_Product', 'VV_VH_Normalized_Difference',
    'VH_Proportion', 'VV_Proportion', 'Advanced_Polarization_Index',
    'Moisture_Index', 'LSWI', 'BUI', 'Brightness_Index',
    'SWIR_NDWI', 'SAVI', 'RE_NDVI', 'Albedo_Proxy'
]

# === Drop missing
gdf = gdf.dropna(subset=[target_multiclass, target_binary] + feature_cols)

# === Prepare data
X = gdf[feature_cols]
y_multi = pd.Categorical(gdf[target_multiclass]).codes
y_binary = gdf[target_binary].astype(int)

# === Train/test split
X_train, X_test, y_multi_train, y_multi_test, y_bin_train, y_bin_test = train_test_split(
    X, y_multi, y_binary, test_size=0.2, random_state=42
)

# === Train models
rf_multi = RandomForestClassifier(n_estimators=100, random_state=42).fit(X_train, y_multi_train)
rf_bin = RandomForestClassifier(n_estimators=100, random_state=42).fit(X_train, y_bin_train)

# === Predict and subset test set
gdf_test = gdf.iloc[X_test.index].copy()
gdf_test['predicted_rating'] = pd.Categorical.from_codes(rf_multi.predict(X_test), categories=list("ABCDEFG"))
gdf_test['predicted_class'] = rf_bin.predict(X_test)

# === Center for map
gdf_proj = gdf_test.to_crs(epsg=3857)
center = [gdf_proj.geometry.centroid.y.mean(), gdf_proj.geometry.centroid.x.mean()]
center = gdf_test.to_crs(epsg=4326).geometry.centroid.iloc[0].y, gdf_test.to_crs(epsg=4326).geometry.centroid.iloc[0].x

# === Initialize map
m = folium.Map(location=center, zoom_start=11, tiles='CartoDB positron')

# === Color dictionaries
rating_colors = {
    'A': '#1a9850', 'B': '#91cf60', 'C': '#d9ef8b', 'D': '#ffffbf',
    'E': '#fee08b', 'F': '#fc8d59', 'G': '#d73027'
}
binary_colors = {
    0: '#d7191c',  # Inefficient
    1: '#1a9641'   # Efficient
}

# === Predicted A–G Layer
ag_layer = folium.FeatureGroup(name="Predicted A–G Rating", show=True)
for _, row in gdf_test.iterrows():
    folium.GeoJson(
        row.geometry,
        style_function=lambda feat, rating=row['predicted_rating']:
            {'fillColor': rating_colors.get(rating, '#cccccc'), 'color': 'black', 'weight': 0.5, 'fillOpacity': 0.6},
        tooltip=f"Predicted: {row['predicted_rating']} | Actual: {row[target_multiclass]}"
    ).add_to(ag_layer)

# === Predicted Binary Efficiency Layer
bin_layer = folium.FeatureGroup(name="Predicted Efficiency Class", show=False)
for _, row in gdf_test.iterrows():
    label = 'Efficient' if row['predicted_class'] == 1 else 'Inefficient'
    actual = 'Efficient' if row[target_binary] == 1 else 'Inefficient'
    folium.GeoJson(
        row.geometry,
        style_function=lambda feat, cls=row['predicted_class']:
            {'fillColor': binary_colors.get(cls, '#cccccc'), 'color': 'black', 'weight': 0.5, 'fillOpacity': 0.6},
        tooltip=f"Predicted: {label} | Actual: {actual}"
    ).add_to(bin_layer)

# === Add layers and control
ag_layer.add_to(m)
bin_layer.add_to(m)
folium.LayerControl().add_to(m)

# === Save
output_path = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Outputs\ml_prediction_testset_map.html"
m.save(output_path)
print(f"✅ Map saved to:\n{output_path}")
