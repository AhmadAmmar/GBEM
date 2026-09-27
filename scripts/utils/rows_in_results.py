# -*- coding: utf-8 -*-
"""
Row counts for key EPC artifacts (CSV/XLS/XLSX/JSON/GEOJSON) with D:\ path overrides.

- Uses only the project files you listed.
- For the four specified files, paths are swapped from
  'C:\\Users\\B00996107\\...' -> 'D:\\...'
- Prints a table and writes a CSV summary.
"""

import os, json, datetime
from pathlib import Path
import pandas as pd
import geopandas as gpd

# -------------------------
# 1) File list (with overrides applied)
# -------------------------
FILES = [
    # Core inputs / artifacts we want to inspect
    r"D:\OneDrive - Ulster University\PhD\data\london\Output\satellite_samples_with_all_indices.csv",
    r"D:\OneDrive - Ulster University\PhD\data\london_samples_indices_binary_2024.csv",               # OVERRIDDEN
    r"D:\OneDrive - Ulster University\PhD\data\london\london_2024_epc_with_polygons.geojson",         # OVERRIDDEN
    r"D:\OneDrive - Ulster University\PhD\data\london\london_2024_epc_predictions.geojson",           # OVERRIDDEN
    r"D:\OneDrive - Ulster University\PhD\data\london\london_2024_epc_predictions_test.geojson",      # OVERRIDDEN

    # Intermediate JSON/CSV created by the A4 report script (these may be dict-like JSONs)
    r"D:\OneDrive - Ulster University\PhD\Maps\confirm_report\london_epc_rf_maps\run_20251008_1314\dataset_stats.json",
    r"D:\OneDrive - Ulster University\PhD\Maps\confirm_report\london_epc_rf_maps\run_20251008_1314\confusion_matrix_counts.csv",
    r"D:\OneDrive - Ulster University\PhD\Maps\confirm_report\london_epc_rf_maps\run_20251008_1314\metrics.json",
    r"D:\OneDrive - Ulster University\PhD\Maps\confirm_report\london_epc_rf_maps\run_20251008_1314\rf_feature_importances.csv",
    r"D:\OneDrive - Ulster University\PhD\Maps\confirm_report\london_epc_rf_maps\run_20251008_1314\model_meta.json",
    r"D:\OneDrive - Ulster University\PhD\Maps\confirm_report\london_epc_rf_maps\run_20251008_1314\figure_inputs_manifest.json",
]

# Deduplicate (case-insensitive on Windows)
_seen = set()
_unique = []
for f in FILES:
    k = Path(f).as_posix().lower()
    if k not in _seen:
        _seen.add(k)
        _unique.append(f)
FILES = _unique

ALLOWED_EXTS = {".csv", ".xls", ".xlsx", ".json", ".geojson"}

# -------------------------
# 2) Helpers
# -------------------------
def count_rows(path: Path):
    """Return (count:int|None, note:str) for supported file types."""
    ext = path.suffix.lower()
    try:
        if ext == ".csv":
            df = pd.read_csv(path)
            return len(df), ""
        if ext in {".xls", ".xlsx"}:
            xl = pd.ExcelFile(path)
            per_sheet = {s: len(pd.read_excel(xl, sheet_name=s)) for s in xl.sheet_names}
            total = sum(per_sheet.values())
            note = "sheets -> " + " | ".join(f"{s}:{n}" for s, n in per_sheet.items())
            return total, note
        if ext == ".geojson":
            gdf = gpd.read_file(path)
            return len(gdf), ""
        if ext == ".json":
            with open(path, "r", encoding="utf-8") as f:
                obj = json.load(f)
            if isinstance(obj, list):
                return len(obj), "top-level JSON array"
            if isinstance(obj, dict):
                for key in ("features", "rows", "data", "records", "items"):
                    if key in obj and isinstance(obj[key], list):
                        return len(obj[key]), f"JSON dict: '{key}' list"
                return len(obj), "JSON dict (count = top-level keys)"
        return None, "skipped"
    except Exception as e:
        return None, f"ERROR: {e}"

def exists(path: Path) -> bool:
    try:
        return path.exists()
    except Exception:
        return False

# -------------------------
# 3) Process
# -------------------------
records = []
for p in FILES:
    path = Path(p)
    ext = path.suffix.lower()
    if ext not in ALLOWED_EXTS:
        continue
    if not exists(path):
        records.append({"file": str(path), "ext": ext, "exists": False, "row_count": None, "note": "MISSING"})
        continue
    n, note = count_rows(path)
    records.append({"file": str(path), "ext": ext, "exists": True, "row_count": n, "note": note})

summary = pd.DataFrame(records).sort_values(["exists", "ext", "file"], ascending=[False, True, True])

# Reference files for percentages
REF_POLY = r"D:\OneDrive - Ulster University\PhD\data\london\london_2024_epc_with_polygons.geojson"
REF_PRED = r"D:\OneDrive - Ulster University\PhD\data\london\london_2024_epc_predictions.geojson"

def _get_ref_count(summary_df: pd.DataFrame, path: str):
    row = summary_df.loc[summary_df["file"].str.lower() == Path(path).as_posix().lower()]
    if not row.empty and pd.notna(row.iloc[0]["row_count"]):
        try:
            return int(row.iloc[0]["row_count"])
        except Exception:
            return None
    return None

poly_n = _get_ref_count(summary, REF_POLY)
pred_n = _get_ref_count(summary, REF_PRED)

summary["pct_vs_polygons"] = (summary["row_count"] / poly_n * 100.0).round(2) if poly_n and poly_n > 0 else pd.NA
summary["pct_vs_predictions"] = (summary["row_count"] / pred_n * 100.0).round(2) if pred_n and pred_n > 0 else pd.NA

# -------------------------
# 4) Output
# -------------------------
pd.set_option("display.max_colwidth", 140)
print("\n=== Row Counts (only requested file types) ===\n")
print(summary.to_string(index=False))

out_dir = Path(r"D:\OneDrive - Ulster University\PhD\Maps\confirm_report")
out_dir.mkdir(parents=True, exist_ok=True)
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
out_csv = out_dir / f"file_row_counts_D_override_{ts}.csv"
summary.to_csv(out_csv, index=False)
print(f"\nSaved: {out_csv}")
