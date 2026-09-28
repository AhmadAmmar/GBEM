# -*- coding: utf-8 -*-
"""
EPC 2023 subset (Belfast):
1) Filter NI EPC master to year 2023 (best date column).
2) Join XY via UPRN from union file(s).
3) Keep only points inside Belfast building footprints.
4) Write outputs + stats.

Follows your existing patterns: encoding sniffing, canonical UPRN, chunked IO,
CRS auto-detect against footprints extent, A–G summaries.

Requires: pandas, geopandas, shapely, fiona, pyproj
"""

from __future__ import annotations
import re, json
from pathlib import Path
from datetime import datetime

import pandas as pd

try:
    import geopandas as gpd
    from shapely.geometry import Point
except Exception as e:
    raise SystemExit("Please install geopandas, shapely, fiona, pyproj") from e

# ───────────────────────── CONFIG ─────────────────────────
EPC_CSV = Path(r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-epc\NI_Domestic_Master_to 01_2025.csv")
FOOTPRINTS_SHP = Path(r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-buildings\Belfast_Building_Footprints.shp")

# Will try these (first existing wins):
UNION_CANDIDATES = [
    r"D:\OneDrive - Ulster University\PhD\data\belfast\uprn\BELFS_20250829_F\uprn_union_with_xy_v2.csv",
    r"D:\OneDrive - Ulster University\PhD\data\belfast\uprn\BELFS_20250829_F\uprn_union_with_xy_clean.csv",
    r"D:\OneDrive - Ulster University\PhD\data\belfast\uprn\BELFS_20250829_F\uprn_union_with_xy_updated.csv",
    r"D:\OneDrive - Ulster University\PhD\data\belfast\uprn\BELFS_20250829_F\uprn_union_with_xy.csv",
]

# Output names (written beside EPC_CSV)
OUT_XY               = EPC_CSV.with_name("NI_EPC_2023_with_XY.csv")
OUT_IN_FOOTPRINTS    = EPC_CSV.with_name("NI_EPC_2023_with_XY_in_footprints.csv")
OUT_UNMATCHED_SAMPLE = EPC_CSV.with_name("NI_EPC_2023_no_XY_sample.csv")
OUT_STATS            = EPC_CSV.with_name("NI_EPC_2023_stats.txt")

# Chunking + parsing
CHUNK = 200_000
CANDIDATE_ENCODINGS = ("utf-8", "utf-8-sig", "cp1252", "latin1")

# Date columns (preference order)
PREFERRED_DATE_COLUMNS = [
    "INSPECTION_DATE", "LODGEMENT_DATE", "REGISTRATION_DATE",
    "DATE_REGISTERED", "DATE_OF_ASSESSMENT", "DATE"
]

# Candidate CRSs for EPC XY (Pointer NI, OSGB, ITM); we’ll auto-score against footprints bbox
EPC_CRS_CANDIDATES = ["EPSG:29902", "EPSG:27700", "EPSG:2157"]

# ────────────────────── HELPERS ──────────────────────
def sniff_encoding(path: Path) -> str:
    for enc in CANDIDATE_ENCODINGS:
        try:
            pd.read_csv(path, nrows=1, encoding=enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin1"

def find_uprn_col_in_file(path: Path, enc: str) -> str:
    cols = pd.read_csv(path, nrows=0, encoding=enc).columns
    for c in cols:
        if "uprn" in c.lower():
            return c
    raise ValueError(f"No UPRN-like column found in {path}\nColumns: {list(cols)}")

def canonical_uprn(val):
    """Digits-only, drop leading zeros; handles 'UPRN-000...123'."""
    if pd.isna(val): return None
    s = str(val).strip().replace("UPRN-","").replace("uprn-","")
    s = re.sub(r"\D", "", s)
    if not s: return None
    try: return str(int(s))
    except ValueError: return None

def detect_best_date_column(path: Path, enc: str, uprn_col: str) -> str:
    cols = pd.read_csv(path, nrows=0, encoding=enc).columns
    candidates = [c for c in cols if "date" in c.lower()]
    for p in PREFERRED_DATE_COLUMNS:
        if p in cols and p not in candidates:
            candidates.append(p)
    if not candidates:
        raise ValueError("No date-like columns found in EPC CSV.")

    sample = pd.read_csv(path, nrows=100_000, dtype=str, low_memory=False,
                         encoding=enc, usecols=[uprn_col]+candidates)
    scores = {}
    for c in candidates:
        ser = pd.to_datetime(sample[c], errors="coerce", infer_datetime_format=True, dayfirst=True)
        n_nonnull = sample[c].notna().sum()
        n_parsed  = ser.notna().sum()
        scores[c] = (n_parsed / n_nonnull) if n_nonnull else 0.0

    best = max(scores, key=lambda k: (scores[k],
                                      -PREFERRED_DATE_COLUMNS.index(k) if k in PREFERRED_DATE_COLUMNS else -9999,
                                      k))
    print("Date column candidate parse rates:")
    for k, v in sorted(scores.items(), key=lambda kv: -kv[1]):
        print(f"  {k}: {v:.3f}")
    print(f"=> Using date column for 2023 filter: {best}")
    return best

def rating_column(cols) -> str | None:
    pref = ["CURRENT_ENERGY_RATING", "EPC_RATING", "ENERGY_RATING"]
    for p in pref:
        if p in cols: return p
    for c in cols:
        if "rating" in c.lower(): return c
    return None

def pick_union_file() -> Path:
    for p in UNION_CANDIDATES:
        path = Path(p)
        if path.exists():
            return path
    raise FileNotFoundError("No UPRN union-with-XY file found. Expected one of:\n" + "\n".join(UNION_CANDIDATES))

def summarize_ag(series: pd.Series) -> dict:
    order = list("ABCDEFG")
    return {k:int(v) for k,v in series.value_counts().reindex(order, fill_value=0).items()}

# ────────────────────── MAIN ──────────────────────
def main():
    t0 = datetime.now()
    print(f"=== EPC 2023 pipeline — {t0:%Y-%m-%d %H:%M} ===")

    # 0) Inputs + encodings
    if not EPC_CSV.exists():
        raise FileNotFoundError(f"EPC CSV not found: {EPC_CSV}")
    if not FOOTPRINTS_SHP.exists():
        raise FileNotFoundError(f"Footprints SHP not found: {FOOTPRINTS_SHP}")

    union_path = pick_union_file()
    union_enc  = sniff_encoding(union_path)
    epc_enc    = sniff_encoding(EPC_CSV)

    print(f"[IN] EPC:   {EPC_CSV}  (enc={epc_enc})")
    print(f"[IN] UNION: {union_path} (enc={union_enc})")
    print(f"[IN] FOOT:  {FOOTPRINTS_SHP}")

    # 1) Load union XY and prep join table
    union = pd.read_csv(union_path, dtype=str, low_memory=False, encoding=union_enc)
    uprn_union_col = "UPRN_key" if "UPRN_key" in union.columns else find_uprn_col_in_file(union_path, union_enc)

    # detect X/Y columns (allow variants)
    xcol = "X_COR" if "X_COR" in union.columns else next((c for c in union.columns if c.upper().startswith("X")), None)
    ycol = "Y_COR" if "Y_COR" in union.columns else next((c for c in union.columns if c.upper().startswith("Y")), None)
    if not (xcol and ycol):
        raise ValueError("Union XY file is missing X/Y columns.")

    union["UPRN_key"] = union[uprn_union_col].map(canonical_uprn)
    union = union.dropna(subset=["UPRN_key", xcol, ycol]).copy()
    union = union.drop_duplicates(subset=["UPRN_key"])
    union = union[["UPRN_key", xcol, ycol] + ([c for c in ("xy_source","sources") if c in union.columns])]
    union = union.rename(columns={xcol:"X_COR", ycol:"Y_COR"})
    print(f"[UNION] UPRNs with XY: {len(union):,}")

    # 2) Detect best EPC date column, then stream and keep only 2023 rows joined to XY
    uprn_epc_col = find_uprn_col_in_file(EPC_CSV, epc_enc)
    date_col     = detect_best_date_column(EPC_CSV, epc_enc, uprn_epc_col)

    first_write = True
    unmatched_samples = []
    total_epc_rows = 0
    total_epc_2023_rows = 0
    matched_rows = 0

    # A–G counters
    rat_counts_2023 = {}
    rat_counts_matched = {}

    for chunk in pd.read_csv(EPC_CSV, dtype=str, chunksize=CHUNK, low_memory=False, encoding=epc_enc):
        total_epc_rows += len(chunk)

        # Canonical UPRN + year=2023
        chunk["UPRN_key"] = chunk[uprn_epc_col].map(canonical_uprn)
        dt = pd.to_datetime(chunk[date_col], errors="coerce", infer_datetime_format=True, dayfirst=True)
        chunk["_year"] = dt.dt.year
        c23 = chunk[chunk["_year"] == 2023].copy()
        total_epc_2023_rows += len(c23)

        # quick rating col detection for tallies
        rcol = rating_column(c23.columns)
        if rcol:
            # accumulate rating counts for 2023 before join
            rat_counts_2023 = (pd.Series(rat_counts_2023) + c23[rcol].value_counts()).fillna(0).to_dict()

        # Join to UNION XY
        if not c23.empty:
            merged = c23.merge(union, on="UPRN_key", how="inner")
            if not merged.empty:
                matched_rows += len(merged)
                if rcol:
                    rat_counts_matched = (pd.Series(rat_counts_matched) + merged[rcol].value_counts()).fillna(0).to_dict()

                merged.to_csv(OUT_XY, index=False, mode="w" if first_write else "a",
                              header=first_write, encoding="utf-8")
                first_write = False

            # collect a small unmatched sample (for QA)
            if len(unmatched_samples) < 5000:
                um = c23[c23["UPRN_key"].isna() | ~c23["UPRN_key"].isin(union["UPRN_key"])]
                take = max(0, 5000 - sum(len(x) for x in unmatched_samples))
                if take > 0 and not um.empty:
                    unmatched_samples.append(um.head(take).drop(columns=["_year"]))

    if unmatched_samples:
        pd.concat(unmatched_samples, ignore_index=True).to_csv(OUT_UNMATCHED_SAMPLE, index=False, encoding="utf-8")

    print("\n[STAGE 1] 2023 filter + XY join")
    print(f"  EPC total rows scanned:        {total_epc_rows:,}")
    print(f"  EPC rows in 2023:              {total_epc_2023_rows:,}")
    print(f"  2023 rows matched to XY:       {matched_rows:,}")
    print(f"  Written: {OUT_XY}")
    if Path(OUT_UNMATCHED_SAMPLE).exists():
        print(f"  Unmatched sample: {OUT_UNMATCHED_SAMPLE}")

    if matched_rows == 0:
        raise SystemExit("No 2023 rows matched to XY; stop here.")

    # 3) Footprints: keep only points inside polygons
    foot = gpd.read_file(FOOTPRINTS_SHP)
    if foot.crs is None:
        raise ValueError("Footprints layer has no CRS defined; set its CRS in GIS first.")
    fp_crs = foot.crs
    minx, miny, maxx, maxy = foot.total_bounds

    df_xy = pd.read_csv(OUT_XY, dtype=str, low_memory=False)
    rcol2 = rating_column(df_xy.columns)
    df_xy["_X"] = pd.to_numeric(df_xy["X_COR"], errors="coerce")
    df_xy["_Y"] = pd.to_numeric(df_xy["Y_COR"], errors="coerce")
    df_xy = df_xy.dropna(subset=["_X","_Y"]).copy()

    # auto-CRS detection against footprints extent
    sample = df_xy.sample(n=min(20000, len(df_xy)), random_state=42)
    scores = {}
    for crs in EPC_CRS_CANDIDATES:
        try:
            g = gpd.GeoDataFrame(sample.copy(),
                                 geometry=gpd.points_from_xy(sample["_X"], sample["_Y"]),
                                 crs=crs).to_crs(fp_crs)
            inside_bbox = ((g.geometry.x >= minx) & (g.geometry.x <= maxx) &
                           (g.geometry.y >= miny) & (g.geometry.y <= maxy)).mean()
            scores[crs] = float(inside_bbox)
        except Exception:
            scores[crs] = -1.0

    best_crs = max(scores, key=scores.get)
    print("\n[CRS detect] share of sample within footprints extent:")
    for k,v in scores.items():
        print(f"  {k}: {v:.3f}")
    print(f"=> Selected EPC XY CRS: {best_crs}")

    g_pts = gpd.GeoDataFrame(df_xy.copy(),
                             geometry=gpd.points_from_xy(df_xy["_X"], df_xy["_Y"]),
                             crs=best_crs).to_crs(fp_crs)
    matched = gpd.sjoin(g_pts, foot[["geometry"]], how="inner", predicate="intersects")

    out_df = pd.DataFrame(matched.drop(columns=["geometry","index_right"], errors="ignore"))
    out_df.to_csv(OUT_IN_FOOTPRINTS, index=False, encoding="utf-8")

    print("\n[STAGE 2] Inside/on footprints")
    print(f"  Points with XY (2023):          {len(df_xy):,}")
    print(f"  Points inside footprints:       {len(out_df):,}")
    print(f"  Written: {OUT_IN_FOOTPRINTS}")

    # 4) Stats summary (A–G at each stage)
    def tidy_counts(raw_dict):
        order = list("ABCDEFG")
        dd = {k:int(raw_dict.get(k, 0)) for k in order}
        return dd, sum(dd.values())

    c_2023, n_2023 = tidy_counts(rat_counts_2023)
    c_xy,    n_xy  = tidy_counts(rat_counts_matched)
    c_in = {}
    if rcol2 and rcol2 in out_df.columns:
        c_in, n_in = tidy_counts(out_df[rcol2].value_counts().to_dict())
    else:
        n_in = len(out_df)

    lines = []
    lines.append(f"Run: {datetime.now():%Y-%m-%d %H:%M}")
    lines.append(f"EPC CSV: {EPC_CSV}")
    lines.append(f"Union XY: {union_path}")
    lines.append(f"Footprints: {FOOTPRINTS_SHP}\n")
    lines.append("[Totals]")
    lines.append(f"  EPC rows scanned:          {total_epc_rows:,}")
    lines.append(f"  EPC rows in 2023:          {total_epc_2023_rows:,}")
    lines.append(f"  2023 matched to XY:        {matched_rows:,}")
    lines.append(f"  Inside footprints:         {len(out_df):,}\n")

    lines.append("[A–G counts] (missing letters show as 0)")
    lines.append(f"  2023 (pre-join):           {json.dumps(c_2023)}")
    lines.append(f"  2023 (with XY):            {json.dumps(c_xy)}")
    lines.append(f"  2023 (inside footprints):  {json.dumps(c_in) if c_in else 'N/A (rating col not found)'}")

    Path(OUT_STATS).write_text("\n".join(lines), encoding="utf-8")

    print("\n[STATS]")
    for L in lines[4:]:
        print(L)

    print("\n=== Done ===")

if __name__ == "__main__":
    main()
