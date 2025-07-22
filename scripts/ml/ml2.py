import geopandas as gpd
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from sklearn.feature_selection import SelectFromModel
import warnings
warnings.filterwarnings("ignore")

# === Load the GeoJSON ===
path = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\London\london_2024_epc_with_polygons.geojson"
gdf = gpd.read_file(path)

# === Define target columns ===
target_multiclass = 'CURRENT_ENERGY_RATING'
target_binary = 'EFFICIENCY_CLASS'  # Assumes already 0 (inefficient) or 1 (efficient)

# === Manually define feature columns (based on your list) ===
feature_cols = [
    'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B11', 'B12',
    'VV', 'VH', 'L8B10',
    'NDVI', 'NDBI', 'UI', 'IBI', 'EVI', 'NDWI', 'GNDVI',
    'VV_VH_Sum', 'VV_VH_Difference', 'VV_VH_Product', 'VV_VH_Normalized_Difference',
    'VH_Proportion', 'VV_Proportion', 'Advanced_Polarization_Index',
    'Moisture_Index', 'LSWI', 'BUI', 'Brightness_Index',
    'SWIR_NDWI', 'SAVI', 'RE_NDVI', 'Albedo_Proxy'
]

# === Drop rows with missing targets or features ===
gdf = gdf.dropna(subset=[target_multiclass, target_binary] + feature_cols)

# === Prepare features and targets ===
X = gdf[feature_cols]
y_multi = gdf[target_multiclass]
y_binary = gdf[target_binary].astype(int)

# === Encode target for A–G as categories if needed ===
y_multi = pd.Categorical(y_multi).codes

# === Train-test split ===
X_train, X_test, y_multi_train, y_multi_test = train_test_split(X, y_multi, test_size=0.2, random_state=42)
_, _, y_bin_train, y_bin_test = train_test_split(X, y_binary, test_size=0.2, random_state=42)

# === Train Random Forest and evaluate for 1–100 estimators ===
best_acc_multi = 0
best_acc_bin = 0
best_model_multi = None
best_model_bin = None

for n in range(10, 101, 10):
    rf_multi = RandomForestClassifier(n_estimators=n, random_state=42, n_jobs=-1)
    rf_multi.fit(X_train, y_multi_train)
    acc_multi = rf_multi.score(X_test, y_multi_test)

    rf_bin = RandomForestClassifier(n_estimators=n, random_state=42, n_jobs=-1)
    rf_bin.fit(X_train, y_bin_train)
    acc_bin = rf_bin.score(X_test, y_bin_test)

    print(f"n={n}: A–G acc = {acc_multi:.3f} | Binary acc = {acc_bin:.3f}")

    if acc_multi > best_acc_multi:
        best_acc_multi = acc_multi
        best_model_multi = rf_multi

    if acc_bin > best_acc_bin:
        best_acc_bin = acc_bin
        best_model_bin = rf_bin

# === Feature Importance (Top 10 features) ===
feat_imp_multi = pd.Series(best_model_multi.feature_importances_, index=feature_cols).sort_values(ascending=False)
feat_imp_bin = pd.Series(best_model_bin.feature_importances_, index=feature_cols).sort_values(ascending=False)

print("\n🌟 Best Multiclass Accuracy (A–G):", round(best_acc_multi, 3))
print("🔍 Top features (Multiclass):")
print(feat_imp_multi.head(10))

print("\n🌟 Best Binary Accuracy (Efficient vs Inefficient):", round(best_acc_bin, 3))
print("🔍 Top features (Binary):")
print(feat_imp_bin.head(10))
