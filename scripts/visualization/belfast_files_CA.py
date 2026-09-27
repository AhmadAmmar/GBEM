# inventory_belfast.py
# Quick data inventory for Belfast folder (recursive).
# Produces a CSV (+ markdown summary) with file types, row counts, columns, and small heads.

import os, sys, re, json, math, warnings
from pathlib import Path
from datetime import datetime
from itertools import islice

warnings.filterwarnings("ignore")

# --- Config ---
ROOT = Path(r"D:\OneDrive - Ulster University\PhD\data\belfast")  # change if needed
SAMPLE_ROWS = 3           # how many sample rows to read
CSV_CHUNK = 200_000       # chunk size for counting CSV rows memory-safely
MAX_JSON_BYTES = 25 * 1024 * 1024  # skip parsing generic JSON bigger than this
OUTPUT_DIR = None         # auto: <ROOT>/_inventory
PRINT_TO_CONSOLE = True   # show a terse preview while scanning

# --- Optional deps (best-effort) ---
try:
    import pandas as pd
except Exception as e:
    print("ERROR: pandas is required. Please install pandas.", file=sys.stderr)
    raise

try:
    import openpyxl   # for .xlsx metadata/row counts
except Exception:
    openpyxl = None

try:
    import xlrd       # for .xls metadata/row counts
except Exception:
    xlrd = None

try:
    from dbfread import DBF
except Exception:
    DBF = None

try:
    import fiona      # to stream geojson features
except Exception:
    fiona = None

try:
    import geopandas as gpd  # fallback small-slice reading
except Exception:
    gpd = None


def human_mb(bytes_):
    return round(bytes_ / (1024 * 1024), 3)


def safe_read_csv_head_and_count(path: Path, sample_rows=SAMPLE_ROWS, chunk=CSV_CHUNK):
    cols, head_df, nrows, error = [], None, None, None
    # Header & sample
    try:
        head_df = pd.read_csv(path, nrows=sample_rows, dtype=str, low_memory=False, encoding="utf-8")
    except Exception:
        try:
            head_df = pd.read_csv(path, nrows=sample_rows, dtype=str, low_memory=False, encoding="latin-1")
        except Exception as e:
            error = f"read_csv_failed: {e}"
            return cols, None, None, error
    cols = list(head_df.columns)

    # Row count via streaming chunks (does not load whole file)
    try:
        total = 0
        for chunk_df in pd.read_csv(path, chunksize=chunk, dtype=str, low_memory=False, encoding="utf-8"):
            total += len(chunk_df)
        nrows = total
    except Exception:
        try:
            total = 0
            for chunk_df in pd.read_csv(path, chunksize=chunk, dtype=str, low_memory=False, encoding="latin-1"):
                total += len(chunk_df)
            nrows = total
        except Exception as e:
            error = f"rowcount_failed: {e}"
    return cols, head_df, nrows, error


def safe_excel_info(path: Path, sample_rows=SAMPLE_ROWS):
    """
    Returns a list of dicts, one per sheet:
    [{'sheet': name, 'nrows': int|None, 'cols': [...], 'head_df': DataFrame|None, 'error': str|None}, ...]
    """
    out = []
    ext = path.suffix.lower()
    if ext == ".xlsx" and openpyxl:
        try:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            sheet_names = wb.sheetnames
        except Exception as e:
            return [{"sheet": None, "nrows": None, "cols": [], "head_df": None, "error": f"openpyxl_load_failed: {e}"}]
        for s in sheet_names:
            info = {"sheet": s, "nrows": None, "cols": [], "head_df": None, "error": None}
            try:
                ws = wb[s]
                info["nrows"] = ws.max_row
            except Exception as e:
                info["error"] = f"openpyxl_ws_failed: {e}"
            # sample via pandas
            try:
                df = pd.read_excel(path, sheet_name=s, nrows=sample_rows, dtype=str, engine="openpyxl")
                info["head_df"] = df
                info["cols"] = list(df.columns)
            except Exception as e:
                info["error"] = (info["error"] + " | " if info["error"] else "") + f"read_excel_failed: {e}"
            out.append(info)
        return out

    elif ext == ".xls" and xlrd:
        try:
            book = xlrd.open_workbook(path, on_demand=True)
            sheet_names = book.sheet_names()
        except Exception as e:
            return [{"sheet": None, "nrows": None, "cols": [], "head_df": None, "error": f"xlrd_open_failed: {e}"}]
        for s in sheet_names:
            info = {"sheet": s, "nrows": None, "cols": [], "head_df": None, "error": None}
            try:
                sh = book.sheet_by_name(s)
                info["nrows"] = sh.nrows
            except Exception as e:
                info["error"] = f"xlrd_sheet_failed: {e}"
            try:
                df = pd.read_excel(path, sheet_name=s, nrows=sample_rows, dtype=str, engine="xlrd")
                info["head_df"] = df
                info["cols"] = list(df.columns)
            except Exception as e:
                info["error"] = (info["error"] + " | " if info["error"] else "") + f"read_excel_failed: {e}"
            out.append(info)
        return out
    else:
        return [{"sheet": None, "nrows": None, "cols": [], "head_df": None,
                 "error": "No engine for Excel. Install openpyxl (xlsx) / xlrd (xls)."}]


def safe_dbf_info(path: Path, sample_rows=SAMPLE_ROWS):
    if DBF is None:
        return [], None, None, "dbfread not installed"
    try:
        table = DBF(path, load=False, ignore_missing_memofile=True)
        cols = list(table.field_names)
        # sample
        sample = list(islice(iter(table), sample_rows))
        # count (dbfread iterates lazily; len() triggers full read, so stream)
        count = 0
        for _ in table:
            count += 1
        return cols, sample, count, None
    except Exception as e:
        return [], None, None, f"dbf_failed: {e}"


def safe_geojson_info(path: Path, sample_rows=SAMPLE_ROWS):
    """
    Prefer fiona to stream feature count and schema without loading all geometry.
    Fallback to geopandas reading a small slice (rows=).
    """
    cols, head_props, nrows, geom_types, error = [], None, None, None, None

    if fiona:
        try:
            with fiona.open(path) as src:
                nrows = len(src)  # fast for many drivers
                schema = src.schema or {}
                props = schema.get("properties", {})
                cols = list(props.keys())
                geom_types = schema.get("geometry")
                # sample first few feature properties
                head_props = []
                for feat in islice(src, SAMPLE_ROWS):
                    head_props.append({k: feat["properties"].get(k) for k in cols})
            return cols, head_props, nrows, geom_types, None
        except Exception as e:
            error = f"fiona_failed: {e}"

    if gpd:
        try:
            # geopandas supports rows=slice(...) with Fiona >= 1.9
            df = gpd.read_file(path, rows=slice(0, SAMPLE_ROWS))
            cols = [c for c in df.columns if c != "geometry"]
            nrows = None  # unknown without full scan; try fiona len above first
            geom_types = ",".join(sorted(set(df.geometry.geom_type.astype(str)))) if "geometry" in df else None
            head_props = df[cols].astype(str).to_dict(orient="records") if cols else None
            return cols, head_props, nrows, geom_types, error
        except Exception as e:
            error = (error + " | " if error else "") + f"geopandas_failed: {e}"

    # Last-ditch: try tiny JSON parse (may load whole file—guard by size)
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            return [], None, None, None, (error or "") + " | skipped_large_geojson_no_streaming"
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, dict) and obj.get("type") == "FeatureCollection":
            feats = obj.get("features", [])
            nrows = len(feats)
            if feats:
                props = feats[0].get("properties", {}) or {}
                cols = list(props.keys())
                head_props = [{k: feats[i].get("properties", {}).get(k) for k in cols}
                              for i in range(min(SAMPLE_ROWS, len(feats)))]
        else:
            error = (error or "") + " | not_a_featurecollection"
    except Exception as e:
        error = (error or "") + f" | json_fallback_failed: {e}"
    return cols, head_props, nrows, geom_types, error


def safe_json_info(path: Path, sample_rows=SAMPLE_ROWS):
    """
    Generic JSON (non-geo): attempts to infer a tabular shape from a list of dicts.
    Skips very large files (to avoid loading into memory).
    """
    cols, head_rows, nrows, error = [], None, None, None
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            return [], None, None, "skipped_large_json"
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, list) and obj and isinstance(obj[0], dict):
            cols = sorted({k for row in obj[:1000] for k in row.keys()})
            head_rows = [{k: obj[i].get(k) for k in cols} for i in range(min(SAMPLE_ROWS, len(obj)))]
            nrows = len(obj)
        elif isinstance(obj, dict):
            # try a common pattern like {'data':[...]}
            for key, val in obj.items():
                if isinstance(val, list) and val and isinstance(val[0], dict):
                    cols = sorted({k for row in val[:1000] for k in row.keys()})
                    head_rows = [{k: val[i].get(k) for k in cols} for i in range(min(SAMPLE_ROWS, len(val)))]
                    nrows = len(val)
                    break
            if not cols:
                error = "json_dict_non_tabular"
        else:
            error = "json_unknown_structure"
    except Exception as e:
        error = f"json_parse_failed: {e}"
    return cols, head_rows, nrows, error


def detect_flags(colnames, filename):
    colset = {c.lower() for c in colnames}
    has_uprn = any(c in colset for c in ["uprn", "propertyuprn", "udprn"])
    has_coords = any(c in colset for c in ["x", "y", "lon", "lat", "longitude", "latitude",
                                           "easting", "northing"])
    epc_cols = ["current_energy_rating", "energy_rating", "epc", "lodgement_date",
                "current_energy_efficiency", "property_type", "inspection_date"]
    has_epc = any(c in colset or any(x in c for x in epc_cols) for c in colset)
    has_2023 = bool(re.search(r"\b2023\b", filename))
    return has_epc, has_uprn, has_coords, has_2023


def abbreviate_cols(cols, limit=25):
    if not cols:
        return ""
    if len(cols) <= limit:
        return ", ".join(cols)
    return ", ".join(cols[:limit]) + f" … (+{len(cols)-limit} more)"


def df_to_markdown(df, max_rows=30):
    # small human-readable summary
    head = df.head(max_rows).copy()
    with pd.option_context("display.max_colwidth", 50):
        return head.to_markdown(index=False)


def main():
    root = ROOT
    if not root.exists():
        print(f"Root not found: {root}", file=sys.stderr)
        sys.exit(1)

    out_dir = root / "_inventory"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    out_csv = out_dir / f"inventory_{ts}.csv"
    out_md = out_dir / f"inventory_{ts}.md"

    records = []
    exts = {".csv", ".xlsx", ".xls", ".dbf", ".json", ".geojson"}

    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            path = Path(dirpath) / fname
            if path.suffix.lower() not in exts:
                continue

            rel = str(path.relative_to(root))
            size = path.stat().st_size
            ext = path.suffix.lower()
            base = path.name
            filetype = ext.lstrip(".").upper()
            note = None

            try:
                if ext == ".csv":
                    cols, head_df, nrows, err = safe_read_csv_head_and_count(path)
                    has_epc, has_uprn, has_coords, has_2023 = detect_flags(cols, base)
                    rec = {
                        "rel_path": rel,
                        "file_type": "CSV",
                        "sheet": "",
                        "size_mb": human_mb(size),
                        "rows": nrows,
                        "cols": len(cols),
                        "columns_sample": abbreviate_cols(cols, 30),
                        "flags_epc": has_epc,
                        "flags_uprn": has_uprn,
                        "flags_coords": has_coords,
                        "flags_year_2023": has_2023,
                        "note": err or "",
                    }
                    records.append(rec)
                    if PRINT_TO_CONSOLE:
                        print(f"[CSV] {rel} | rows≈{nrows} | cols={len(cols)} | {rec['columns_sample']}")

                elif ext in (".xlsx", ".xls"):
                    infos = safe_excel_info(path)
                    for info in infos:
                        cols = info["cols"] or []
                        nrows = info["nrows"]
                        err = info["error"]
                        has_epc, has_uprn, has_coords, has_2023 = detect_flags(cols, base)
                        rec = {
                            "rel_path": rel,
                            "file_type": "XLSX" if ext == ".xlsx" else "XLS",
                            "sheet": info["sheet"] or "",
                            "size_mb": human_mb(size),
                            "rows": nrows,
                            "cols": len(cols),
                            "columns_sample": abbreviate_cols(cols, 30),
                            "flags_epc": has_epc,
                            "flags_uprn": has_uprn,
                            "flags_coords": has_coords,
                            "flags_year_2023": has_2023,
                            "note": err or "",
                        }
                        records.append(rec)
                        if PRINT_TO_CONSOLE:
                            print(f"[XLS*] {rel} :: {rec['sheet']} | rows≈{nrows} | cols={len(cols)} | {rec['columns_sample']}")

                elif ext == ".dbf":
                    cols, sample, nrows, err = safe_dbf_info(path)
                    has_epc, has_uprn, has_coords, has_2023 = detect_flags(cols, base)
                    rec = {
                        "rel_path": rel,
                        "file_type": "DBF",
                        "sheet": "",
                        "size_mb": human_mb(size),
                        "rows": nrows,
                        "cols": len(cols),
                        "columns_sample": abbreviate_cols(cols, 30),
                        "flags_epc": has_epc,
                        "flags_uprn": has_uprn,
                        "flags_coords": has_coords,
                        "flags_year_2023": has_2023,
                        "note": err or "",
                    }
                    records.append(rec)
                    if PRINT_TO_CONSOLE:
                        print(f"[DBF] {rel} | rows≈{nrows} | cols={len(cols)} | {rec['columns_sample']} | {err or ''}")

                elif ext == ".geojson":
                    cols, head_props, nrows, geom_types, err = safe_geojson_info(path)
                    has_epc, has_uprn, has_coords, has_2023 = detect_flags(cols, base)
                    rec = {
                        "rel_path": rel,
                        "file_type": "GEOJSON",
                        "sheet": "",
                        "size_mb": human_mb(size),
                        "rows": nrows,
                        "cols": len(cols),
                        "columns_sample": abbreviate_cols(cols, 30),
                        "geom_types": geom_types,
                        "flags_epc": has_epc,
                        "flags_uprn": has_uprn,
                        "flags_coords": has_coords,
                        "flags_year_2023": has_2023,
                        "note": err or "",
                    }
                    records.append(rec)
                    if PRINT_TO_CONSOLE:
                        print(f"[GEOJSON] {rel} | rows≈{nrows} | cols={len(cols)} | geom={geom_types} | {rec['columns_sample']} | {err or ''}")

                elif ext == ".json":
                    cols, head_rows, nrows, err = safe_json_info(path)
                    has_epc, has_uprn, has_coords, has_2023 = detect_flags(cols, base)
                    rec = {
                        "rel_path": rel,
                        "file_type": "JSON",
                        "sheet": "",
                        "size_mb": human_mb(size),
                        "rows": nrows,
                        "cols": len(cols),
                        "columns_sample": abbreviate_cols(cols, 30),
                        "flags_epc": has_epc,
                        "flags_uprn": has_uprn,
                        "flags_coords": has_coords,
                        "flags_year_2023": has_2023,
                        "note": err or "",
                    }
                    records.append(rec)
                    if PRINT_TO_CONSOLE:
                        print(f"[JSON] {rel} | rows≈{nrows} | cols={len(cols)} | {rec['columns_sample']} | {err or ''}")

            except Exception as e:
                # catch-all so one bad file doesn't stop the crawl
                records.append({
                    "rel_path": rel, "file_type": filetype, "sheet": "",
                    "size_mb": human_mb(size), "rows": None, "cols": None,
                    "columns_sample": "", "flags_epc": "", "flags_uprn": "",
                    "flags_coords": "", "flags_year_2023": "",
                    "note": f"unhandled_error: {e}",
                })
                if PRINT_TO_CONSOLE:
                    print(f"[ERROR] {rel} -> {e}")

    # Build DataFrame and export
    df = pd.DataFrame.from_records(records)
    # Helpful ordered columns
    col_order = [c for c in [
        "rel_path", "file_type", "sheet", "size_mb", "rows", "cols",
        "columns_sample", "geom_types",
        "flags_epc", "flags_uprn", "flags_coords", "flags_year_2023", "note"
    ] if c in df.columns]
    df = df[col_order]

    df.to_csv(out_csv, index=False, encoding="utf-8")
    # Simple markdown summary
    summary = []
    summary.append(f"# Belfast Data Inventory — {datetime.now():%Y-%m-%d %H:%M}\n")
    summary.append(f"- Root: `{root}`")
    summary.append(f"- Files scanned: **{len(df)}**")
    summary.append(f"- Saved CSV: `{out_csv}`\n")
    # counts by type
    counts = df.groupby("file_type")["rel_path"].count().reset_index(name="count")
    summary.append("## Counts by type\n")
    summary.append(counts.to_markdown(index=False))
    summary.append("\n## First 30 rows preview\n")
    summary.append(df_to_markdown(df, max_rows=30))
    Path(out_md).write_text("\n".join(summary), encoding="utf-8")

    print("\n=== Done ===")
    print(f"Inventory CSV: {out_csv}")
    print(f"Summary MD :  {out_md}")
    print("Tip: open the Markdown in VS Code or convert to HTML for a quick read.")

if __name__ == "__main__":
    main()
