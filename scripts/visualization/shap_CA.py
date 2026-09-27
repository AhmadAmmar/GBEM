# -*- coding: utf-8 -*-
r"""
Quick SHAP (5% stratified sample) for London EPC — robust to SHAP output shapes.

Outputs -> D:\OneDrive - Ulster University\PhD\Outputs\shap_quicklook\run_YYYYMMDD_HHMM\
"""

import os, json, warnings, datetime, numpy as np, pandas as pd, geopandas as gpd
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
import shap
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")

# ── I/O ──────────────────────────────────────────────────────────────────
DATA_FILE = r"D:\OneDrive - Ulster University\PhD\data\london\london_2024_epc_with_polygons.geojson"
OUTROOT   = r"D:\OneDrive - Ulster University\PhD\Outputs\shap_quicklook"
RUN_DIR   = Path(OUTROOT) / f"run_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}"
RUN_DIR.mkdir(parents=True, exist_ok=True)

def log(path, label="SAVE"):
    print(f"[{label}] {Path(path).resolve()}")

# ── Config ───────────────────────────────────────────────────────────────
FEATURE_COLS_ALL = [
    'B2','B3','B4','B5','B6','B7','B8','B8A','B11','B12',
    'VV','VH','L8B10',
    'NDVI','NDBI','UI','IBI','EVI','NDWI','GNDVI',
    'VV_VH_Sum','VV_VH_Difference','VV_VH_Product','VV_VH_Normalized_Difference',
    'VH_Proportion','VV_Proportion','Advanced_Polarization_Index',
    'Moisture_Index','LSWI','BUI','Brightness_Index','SWIR_NDWI',
    'SAVI','RE_NDVI','Albedo_Proxy'
]

TARGETS    = {"binary": "EFFICIENCY_CLASS", "multiclass": "CURRENT_ENERGY_RATING"}
USE_TARGET = "binary"            # change to "multiclass" for A–G explanations

SAMPLE_FRAC     = 0.05           # ← ~5% of data per class
MIN_PER_CLASS   = 30             # keep small classes visible
RANDOM_SEED     = 42
N_TREES         = 120            # smaller forest for speed
PLOT_SLICE_MAX  = 600            # cap n rows used in SHAP plots

# ── Load & prep ─────────────────────────────────────────────────────────
print(f"[LOAD] {DATA_FILE}")
gdf = gpd.read_file(DATA_FILE)

target_col   = TARGETS[USE_TARGET]
feature_cols = [c for c in FEATURE_COLS_ALL if c in gdf.columns]
if len(feature_cols) < 5:
    raise RuntimeError("Not enough feature columns present in the file.")

df = gdf[feature_cols + [target_col]].dropna().copy()

# Stratified 5% sample with per-class floor
def stratified_fraction_sample(df, target, frac, min_per_class=1, random_state=RANDOM_SEED):
    parts = []
    for cls, sub in df.groupby(target, dropna=False):
        n_cls = len(sub)
        n_take = max(min_per_class, int(np.ceil(frac * n_cls)))
        n_take = min(n_take, n_cls)
        parts.append(sub.sample(n=n_take, random_state=random_state, replace=False))
    return pd.concat(parts, axis=0).sample(frac=1.0, random_state=random_state).reset_index(drop=True)

df_small = stratified_fraction_sample(df, target_col, SAMPLE_FRAC, MIN_PER_CLASS)
print(f"[INFO] Using {len(df_small):,} rows (~5% stratified sample).")

# Encode target where needed
if USE_TARGET == "multiclass":
    df_small[target_col] = pd.Categorical(df_small[target_col], categories=list("ABCDEFG"))
    y = df_small[target_col].codes
else:
    y = df_small[target_col].astype(int).values

X = df_small[feature_cols].astype(float)

# Train/test split on sampled data
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.30, stratify=y, random_state=RANDOM_SEED
)
print(f"Train: {len(X_train):,}   Test: {len(X_test):,}   Features: {len(feature_cols)}")

# ── Train a compact RF ──────────────────────────────────────────────────
rf = RandomForestClassifier(
    n_estimators=N_TREES, max_depth=None, max_features="sqrt",
    random_state=RANDOM_SEED, n_jobs=-1
).fit(X_train, y_train)

y_pred = rf.predict(X_test)
acc  = accuracy_score(y_test, y_pred)
bacc = balanced_accuracy_score(y_test, y_pred)
f1w  = f1_score(y_test, y_pred, average=("weighted" if USE_TARGET=="multiclass" else "binary"))

metrics_json = {
    "use_target": USE_TARGET,
    "n_features": len(feature_cols),
    "n_train": int(len(X_train)),
    "n_test": int(len(X_test)),
    "accuracy": float(acc),
    "balanced_accuracy": float(bacc),
    "f1": float(f1w),
    "sample_frac": SAMPLE_FRAC,
    "min_per_class": MIN_PER_CLASS,
    "n_trees": N_TREES
}
with open(RUN_DIR / "metrics.json", "w", encoding="utf-8") as f:
    json.dump(metrics_json, f, indent=2)
log(RUN_DIR / "metrics.json")

print("\n=== Performance (5% sample) ===")
print(f"Accuracy: {acc:.3f} | Balanced Acc: {bacc:.3f} | F1: {f1w:.3f}")

# ── SHAP (robust to shape variants) ─────────────────────────────────────
print("\nCalculating SHAP values (capped slice for speed)...")
explainer = shap.TreeExplainer(rf)

plot_slice = min(PLOT_SLICE_MAX, len(X_test))
X_plot = X_test.iloc[:plot_slice]

raw_shap = explainer.shap_values(X_plot)

def coerce_binary_shap_matrix(raw, positive_index=1):
    """
    Return a 2-D array (n_samples, n_features) for binary classification
    regardless of whether SHAP returned a list, 2-D ndarray, or 3-D ndarray.
    """
    if isinstance(raw, list):
        if len(raw) == 1:
            return np.asarray(raw[0])          # (n_samples, n_features)
        idx = min(positive_index, len(raw)-1)  # pick positive class
        return np.asarray(raw[idx])

    arr = np.asarray(raw)
    if arr.ndim == 2:
        return arr                              # (n_samples, n_features)
    if arr.ndim == 3:
        # Shapes seen in the wild:
        #  (n_classes, n_samples, n_features)  or  (n_samples, n_features, n_classes)
        if arr.shape[0] in (1,2,3,7) and arr.shape[1] == X_plot.shape[0]:
            # class-first
            idx = min(positive_index, arr.shape[0]-1)
            return arr[idx, :, :]
        if arr.shape[-1] in (1,2,3,7) and arr.shape[0] == X_plot.shape[0]:
            # class-last
            idx = min(positive_index, arr.shape[-1]-1)
            return arr[:, :, idx]
    raise ValueError(f"Unexpected SHAP shape for binary: {arr.shape}")

def aggregate_multiclass_mean_abs(raw):
    """
    Return a 2-D array (n_samples, n_features) for multiclass by
    averaging |SHAP| across classes, robust to list/array shapes.
    """
    if isinstance(raw, list):
        mats = [np.asarray(m) for m in raw]   # each (n_samples, n_features)
    else:
        arr = np.asarray(raw)
        if arr.ndim == 3:
            if arr.shape[0] in (2,3,7) and arr.shape[1] == X_plot.shape[0]:
                mats = [arr[i, :, :] for i in range(arr.shape[0])]
            elif arr.shape[-1] in (2,3,7) and arr.shape[0] == X_plot.shape[0]:
                mats = [arr[:, :, i] for i in range(arr.shape[-1])]
            else:
                raise ValueError(f"Unexpected SHAP shape for multiclass: {arr.shape}")
        elif arr.ndim == 2:  # degenerate case
            mats = [arr]
        else:
            raise ValueError(f"Unexpected SHAP ndim: {arr.ndim}")
    return np.mean([np.abs(m) for m in mats], axis=0)

# Coerce to a clean (n_samples, n_features) matrix
if USE_TARGET == "binary":
    shap_mat = coerce_binary_shap_matrix(raw_shap, positive_index=1)
else:
    shap_mat = aggregate_multiclass_mean_abs(raw_shap)

# ── Global importance (mean |SHAP|) ──────────────────────────────────────
global_imp = pd.Series(np.abs(shap_mat).mean(axis=0), index=feature_cols).sort_values(ascending=False)
global_imp_df = global_imp.reset_index()
global_imp_df.columns = ["feature", "mean_abs_shap"]
global_imp_df.to_csv(RUN_DIR / "shap_global_importance.csv", index=False)
log(RUN_DIR / "shap_global_importance.csv")

# Quick “direction” hint: corr(feature, shap)
corrs = []
for i, col in enumerate(feature_cols):
    try:
        corrs.append(np.corrcoef(X_plot[col].values, shap_mat[:, i])[0, 1])
    except Exception:
        corrs.append(np.nan)
global_imp_df["corr_feat_shap"] = corrs
global_imp_df.to_csv(RUN_DIR / "shap_global_importance_with_sign.csv", index=False)
log(RUN_DIR / "shap_global_importance_with_sign.csv")

print("\n=== Top by mean(|SHAP|) ===")
print(global_imp_df.head(10).to_string(index=False))

# ── Plots (bar, beeswarm, dependence top-5) ─────────────────────────────
plt.figure(figsize=(7.5, 5.8))
shap.summary_plot(shap_mat, X_plot, plot_type="bar", show=False)
plt.title("SHAP Global Feature Importance (5% sample)")
plt.tight_layout()
plt.savefig(RUN_DIR / "shap_summary_bar.png", dpi=300)
plt.close(); log(RUN_DIR / "shap_summary_bar.png")

plt.figure(figsize=(8.8, 6))
shap.summary_plot(shap_mat, X_plot, show=False)
plt.title("SHAP Beeswarm (5% sample)")
plt.tight_layout()
plt.savefig(RUN_DIR / "shap_beeswarm.png", dpi=300)
plt.close(); log(RUN_DIR / "shap_beeswarm.png")

topk = list(global_imp.index[:5])
for col in topk:
    plt.figure(figsize=(6.2, 5))
    shap.dependence_plot(ind=col, shap_values=shap_mat, features=X_plot, interaction_index=None, show=False)
    plt.title(f"Dependence: {col} (5% sample)")
    plt.tight_layout()
    outp = RUN_DIR / f"shap_dependence_{col}.png"
    plt.savefig(outp, dpi=300)
    plt.close(); log(outp)

# Local explanations for first few rows
n_local = min(8, len(X_plot))
rows = []
for i in range(n_local):
    row = X_plot.iloc[i:i+1]
    sv = shap_mat[i, :]
    pos_idx = np.argsort(-sv)[:3]
    neg_idx = np.argsort(sv)[:3]
    rows.append({
        "row_index": int(X_plot.index[i]),
        "top_pos": [(feature_cols[j], float(sv[j]), float(row.iloc[0, j])) for j in pos_idx],
        "top_neg": [(feature_cols[j], float(sv[j]), float(row.iloc[0, j])) for j in neg_idx],
    })
with open(RUN_DIR / "local_explanations.json", "w", encoding="utf-8") as f:
    json.dump(rows, f, indent=2)
log(RUN_DIR / "local_explanations.json")

# Manifest
with open(RUN_DIR / "manifest.json", "w", encoding="utf-8") as f:
    json.dump({
        "data_file": str(Path(DATA_FILE).resolve()),
        "target": USE_TARGET,
        "feature_count": len(feature_cols),
        "sample_frac": SAMPLE_FRAC,
        "outputs": sorted([p.name for p in RUN_DIR.glob("*")])
    }, f, indent=2)
log(RUN_DIR / "manifest.json")

print("\nDone.")
