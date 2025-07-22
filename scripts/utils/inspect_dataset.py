#!/usr/bin/env python3
"""Utility for inspecting dataset files."""

import argparse
import json
import os
from datetime import datetime

try:
    import pandas as pd
except ImportError:  # pragma: no cover - optional dependency
    pd = None

try:
    import geopandas as gpd
except ImportError:  # pragma: no cover - optional dependency
    gpd = None

try:
    import pyarrow.parquet as pq
except ImportError:  # pragma: no cover - optional dependency
    pq = None

try:
    import fiona
except ImportError:  # pragma: no cover - optional dependency
    fiona = None


def _csv_info(path):
    """Return row count and columns for a CSV file."""
    rows = sum(1 for _ in open(path, encoding="utf-8")) - 1
    if pd:
        cols = pd.read_csv(path, nrows=0).columns.tolist()
    else:
        with open(path, encoding="utf-8") as f:
            cols = f.readline().strip().split(',')
    return rows, cols


def _parquet_info(path):
    """Return row count and columns for a Parquet file."""
    if pq is None:
        raise RuntimeError("pyarrow is required for parquet support")
    parquet = pq.ParquetFile(path)
    rows = parquet.metadata.num_rows
    cols = parquet.schema.names
    return rows, cols


def _json_info(path):
    """Return row count and columns for a JSON or GeoJSON file."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and "features" in data:
        rows = len(data["features"])
        if rows:
            cols = list(data["features"][0].get("properties", {}).keys())
        else:
            cols = []
        return rows, cols

    if isinstance(data, list):
        rows = len(data)
        cols = list(data[0].keys()) if rows and isinstance(data[0], dict) else []
        return rows, cols

    rows = len(data)
    cols = list(data.keys()) if isinstance(data, dict) else []
    return rows, cols


def _gis_info(path):
    """Return row count, columns and CRS for spatial files using GeoPandas."""
    if gpd is None:
        raise RuntimeError("geopandas is required for GIS formats")
    read_path = path
    if path.lower().endswith(".zip"):
        # Assume zipped Shapefile
        read_path = f"zip://{path}"
    gdf = gpd.read_file(read_path)
    rows = len(gdf)
    cols = gdf.columns.tolist()
    crs = gdf.crs.to_string() if gdf.crs else None
    return rows, cols, crs


SUPPORTED = {
    ".csv": _csv_info,
    ".parquet": _parquet_info,
    ".json": _json_info,
    ".geojson": _json_info,
    ".shp": _gis_info,
    ".zip": _gis_info,
    ".gpkg": _gis_info,
    ".fgb": _gis_info,
    ".pbf": _gis_info,
}


def inspect_file(path):
    """Inspect a single dataset file."""
    info = {
        "path": path,
        "name": os.path.basename(path),
        "size_bytes": os.path.getsize(path),
        "modified": datetime.fromtimestamp(os.path.getmtime(path)).isoformat(),
    }
    ext = os.path.splitext(path)[1].lower()
    func = SUPPORTED.get(ext)
    if func:
        try:
            result = func(path)
        except Exception as exc:  # pragma: no cover - runtime errors
            info["error"] = str(exc)
        else:
            info["rows"] = result[0]
            info["columns"] = result[1]
            if len(result) > 2 and result[2]:
                info["crs"] = result[2]
    return info


def inspect_path(path, recursive=False):
    """Inspect a file or all supported files in a directory."""
    results = []
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for name in files:
                full = os.path.join(root, name)
                if os.path.splitext(name)[1].lower() in SUPPORTED:
                    results.append(inspect_file(full))
            if not recursive:
                break
    else:
        results.append(inspect_file(path))
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect dataset files")
    parser.add_argument("path", help="File or directory to inspect")
    parser.add_argument("-o", "--output", help="Optional JSON file to write results")
    parser.add_argument("-r", "--recursive", action="store_true", help="Recursively search directories")
    args = parser.parse_args(argv)

    results = inspect_path(args.path, recursive=args.recursive)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
    else:
        for res in results:
            print(f"\nFile: {res['name']}")
            print(f"Path: {res['path']}")
            print(f"Size: {res['size_bytes']} bytes")
            print(f"Modified: {res['modified']}")
            if "rows" in res:
                print(f"Rows: {res['rows']}")
            if "columns" in res:
                print("Columns:")
                for col in res['columns']:
                    print(f"  - {col}")
            if "crs" in res:
                print(f"CRS: {res['crs']}")
            if "error" in res:
                print(f"Error: {res['error']}")


if __name__ == "__main__":  # pragma: no cover
    main()
