import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    classification_report, confusion_matrix, accuracy_score, f1_score,
    precision_score, recall_score, balanced_accuracy_score, mean_squared_error
)
import matplotlib.pyplot as plt
import seaborn as sns

# Load dataset
input_file = "D:/OneDrive - Ulster University/PhD/data/london/Output/satellite_samples_with_all_indices.csv"
print("Loading dataset...")
data = pd.read_csv(input_file)

# Define target and features
# Features are the contiguous block of satellite/spectral-index columns
# starting at S2_B2 (Sentinel-2 band B2) and running to the end of the
# file. Anchored on the column name rather than a fixed position (21)
# so it stays correct if EPC/building-attribute columns are ever added
# or reordered before this block.
target = "CURRENT_ENERGY_RATING"
start_column_index = data.columns.get_loc("S2_B2")
features = data.columns[start_column_index:]
data = data.dropna(subset=list(features) + [target])

# Train-test split
X = data[features]
y = data[target]
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y)

# Class distribution
train_class_counts = y_train.value_counts().sort_index()
test_class_counts = y_test.value_counts().sort_index()

# Random Forest Model
rf_model = RandomForestClassifier(n_estimators=100, random_state=42)
rf_model.fit(X_train, y_train)

# Feature Importance
feature_importances = pd.DataFrame({
    "Feature": features,
    "Importance": rf_model.feature_importances_
}).sort_values(by="Importance", ascending=False)

# Top 10 Features with Importance
top_features = feature_importances.head(10)
X_train_top = X_train[top_features["Feature"]]
X_test_top = X_test[top_features["Feature"]]

# Train with Top 10 Features
rf_model_top = RandomForestClassifier(n_estimators=100, random_state=42)
rf_model_top.fit(X_train_top, y_train)
y_pred_top = rf_model_top.predict(X_test_top)

# Metrics Calculation
accuracy_top = accuracy_score(y_test, y_pred_top)
f1_top = f1_score(y_test, y_pred_top, average="weighted")
precision_top = precision_score(y_test, y_pred_top, average="weighted")
recall_top = recall_score(y_test, y_pred_top, average="weighted")
balanced_acc = balanced_accuracy_score(y_test, y_pred_top)

# RMSE Calculation
class_mapping = {label: idx for idx, label in enumerate(sorted(y_test.unique()))}
y_true_num = y_test.map(class_mapping)
y_pred_num = pd.Series(y_pred_top).map(class_mapping)
rmse = np.sqrt(mean_squared_error(y_true_num, y_pred_num))

# Confusion Matrix & Per-Class Accuracy
cm = confusion_matrix(y_test, y_pred_top, labels=rf_model_top.classes_)
per_class_accuracy = (np.diag(cm) / cm.sum(axis=1)).round(2)

# Test Samples with Accuracy %
combined_class_info = [
    f"{cls}: {test_class_counts[cls]} ({acc*100:.0f}%)"
    for cls, acc in zip(rf_model_top.classes_, per_class_accuracy)
]

# Top 10 Features with Importance
top_features_info = [
    f"{row['Feature']} ({row['Importance']*100:.1f}%)"
    for _, row in top_features.iterrows()
]

# Metrics Summary
metrics_text = (
    f"Accuracy: {accuracy_top:.2f}\n"
    f"Balanced Accuracy: {balanced_acc:.2f}\n"
    f"Weighted F1 Score: {f1_top:.2f}\n"
    f"Precision: {precision_top:.2f}\n"
    f"Recall: {recall_top:.2f}\n"
    f"RMSE: {rmse:.2f}\n"
    f"\nTop 10 Features (Imp%):\n" + "\n".join(top_features_info) +
    f"\n\nTrain Samples:\n" + "\n".join([f"{cls}: {cnt}" for cls, cnt in train_class_counts.items()]) +
    f"\n\nTest Samples (Acc%):\n" + "\n".join(combined_class_info)
)

# Plotting the Confusion Matrix
plt.figure(figsize=(15, 8))
ax = sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                 xticklabels=rf_model_top.classes_, yticklabels=rf_model_top.classes_,
                 cbar=False)

plt.subplots_adjust(right=0.75)  # Space for metrics

plt.title("Random Forest (Top 10 Features) | ~7k EPC Samples (A-G) | Greater London Area", fontsize=14)
plt.xlabel("Predicted", fontsize=12)
plt.ylabel("Actual", fontsize=12)

# Displaying Metrics on the Right
plt.gcf().text(0.78, 0.5, metrics_text, fontsize=10, va='center', ha='left')

# Save the Figure
plt.tight_layout(rect=[0, 0, 0.75, 1])
plt.savefig("confusion_matrix_with_importance.png", dpi=300)
plt.show()

print("Confusion matrix with detailed metrics saved successfully!")
