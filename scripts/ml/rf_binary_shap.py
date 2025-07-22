import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    confusion_matrix, accuracy_score, f1_score,
    precision_score, recall_score, balanced_accuracy_score,
    roc_auc_score, roc_curve
)

import shap
import warnings
warnings.filterwarnings("ignore")

# Load dataset
input_file = r"C:\Users\B00996107\OneDrive - Ulster University\PhD\Data\london_samples_indices_binary_2024.csv"
print("Loading dataset...")
df = pd.read_csv(input_file)

# Target and feature selection
target = "EFFICIENCY_CLASS"
feature_columns = df.iloc[:, 29:56].select_dtypes(include='number').columns
df = df.dropna(subset=list(feature_columns) + [target])

X = df[feature_columns]
y = df[target]

# Split data
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.3, stratify=y, random_state=42
)

# Train RF model
rf = RandomForestClassifier(n_estimators=100, random_state=42)
rf.fit(X_train, y_train)

# Get predictions and probabilities
y_pred = rf.predict(X_test)
y_prob = rf.predict_proba(X_test)[:, 1]

# Metrics
acc = accuracy_score(y_test, y_pred)
f1 = f1_score(y_test, y_pred)
precision = precision_score(y_test, y_pred)
recall = recall_score(y_test, y_pred)
balanced_acc = balanced_accuracy_score(y_test, y_pred)
roc_auc = roc_auc_score(y_test, y_prob)

# Print metrics to terminal
print("\n=== Performance Metrics ===")
print(f"Accuracy:          {acc:.2f}")
print(f"Balanced Accuracy: {balanced_acc:.2f}")
print(f"F1 Score:          {f1:.2f}")
print(f"Precision:         {precision:.2f}")
print(f"Recall:            {recall:.2f}")
print(f"ROC AUC:           {roc_auc:.2f}")

# Confusion matrix
cm = confusion_matrix(y_test, y_pred)

# ROC Curve
fpr, tpr, thresholds = roc_curve(y_test, y_prob)

plt.figure(figsize=(10, 6))
sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
            xticklabels=['Inefficient (0)', 'Efficient (1)'],
            yticklabels=['Inefficient (0)', 'Efficient (1)'])

# Add metrics text
metrics_text = (
    f"Accuracy: {acc:.2f}\n"
    f"Balanced Acc: {balanced_acc:.2f}\n"
    f"F1 Score: {f1:.2f}\n"
    f"Precision: {precision:.2f}\n"
    f"Recall: {recall:.2f}\n"
    f"ROC AUC: {roc_auc:.2f}"
)

plt.gcf().text(1.02, 0.5, metrics_text, fontsize=10, va='center', ha='left')
plt.title("Confusion Matrix – Binary Classification (RF)\nEfficient vs Inefficient EPC (A–C vs D–G)")
plt.xlabel("Predicted")
plt.ylabel("Actual")
plt.tight_layout(rect=[0, 0, 0.85, 1])
plt.savefig("binary_confusion_matrix_rf.png", dpi=300)
plt.show()

# === Plot ROC Curve ===
plt.figure(figsize=(8, 6))
plt.plot(fpr, tpr, label=f"ROC Curve (AUC = {roc_auc:.2f})", color="blue")
plt.plot([0, 1], [0, 1], 'k--', label="Random Classifier")
plt.xlabel("False Positive Rate")
plt.ylabel("True Positive Rate")
plt.title("ROC Curve – EPC Efficiency Classification")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.savefig("binary_roc_curve_rf.png", dpi=300)
plt.show()

# === SHAP Feature Interpretation ===
print("Calculating SHAP values...")
explainer = shap.TreeExplainer(rf)
shap_values = explainer.shap_values(X_test)

# Summary plot (for class 1 = Efficient)
shap.summary_plot(shap_values[1], X_test, plot_type="bar", show=False)
plt.title("SHAP Feature Importance (Efficient Class)")
plt.tight_layout()
plt.savefig("shap_summary_bar_rf.png", dpi=300)
plt.show()
