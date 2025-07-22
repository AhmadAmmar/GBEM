import geopandas as gpd
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import warnings
warnings.filterwarnings("ignore")

# === Load the GeoJSON ===
path = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\London\london_2024_epc_with_polygons.geojson"
gdf = gpd.read_file(path)

# === Define target columns ===
target_multiclass = 'CURRENT_ENERGY_RATING'
target_binary = 'EFFICIENCY_CLASS'  # Assumes 0 (inefficient) or 1 (efficient)

# === Manually define feature columns ===
feature_cols = [
    'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B11', 'B12',
    'VV', 'VH', 'L8B10',
    'NDVI', 'NDBI', 'UI', 'IBI', 'EVI', 'NDWI', 'GNDVI',
    'VV_VH_Sum', 'VV_VH_Difference', 'VV_VH_Product', 'VV_VH_Normalized_Difference',
    'VH_Proportion', 'VV_Proportion', 'Advanced_Polarization_Index',
    'Moisture_Index', 'LSWI', 'BUI', 'Brightness_Index',
    'SWIR_NDWI', 'SAVI', 'RE_NDVI', 'Albedo_Proxy'
]

# === Drop rows with missing values ===
gdf = gdf.dropna(subset=[target_multiclass, target_binary] + feature_cols)

# === Prepare feature matrix and targets ===
X = gdf[feature_cols]
y_multi = pd.Categorical(gdf[target_multiclass])
y_multi_codes = y_multi.codes
y_binary = gdf[target_binary].astype(int)

# === Split data for model tuning ===
X_train, X_test, y_multi_train, y_multi_test = train_test_split(X, y_multi_codes, test_size=0.2, random_state=42)
_, _, y_bin_train, y_bin_test = train_test_split(X, y_binary, test_size=0.2, random_state=42)

# === Train models for feature importance ===
rf_multi = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
rf_multi.fit(X_train, y_multi_train)
top_features_multi = pd.Series(rf_multi.feature_importances_, index=feature_cols).sort_values(ascending=False).head(10).index.tolist()

rf_bin = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
rf_bin.fit(X_train, y_bin_train)
top_features_bin = pd.Series(rf_bin.feature_importances_, index=feature_cols).sort_values(ascending=False).head(10).index.tolist()

# === Train final models with top features ===
final_model_multi = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
final_model_multi.fit(gdf[top_features_multi], y_multi_codes)
predicted_rating = final_model_multi.predict(gdf[top_features_multi])

final_model_bin = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
final_model_bin.fit(gdf[top_features_bin], y_binary)
predicted_class = final_model_bin.predict(gdf[top_features_bin])

# === Map predicted multiclass values back to A–G labels ===
label_map = dict(enumerate(y_multi.categories))
predicted_labels = pd.Series(predicted_rating).map(label_map)

# === Add predictions to GeoDataFrame ===
gdf['predicted_rating'] = predicted_labels
gdf['predicted_class'] = predicted_class

# === Save new GeoJSON ===
output_path = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\London\london_2024_epc_predictions.geojson"
gdf.to_file(output_path, driver='GeoJSON')

print(f"✅ Predictions saved to:\n{output_path}")
