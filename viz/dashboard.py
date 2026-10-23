"""Interactive dashboard of EPC ratings, model predictions and their errors: one self-contained HTML file per area and
model run (replaces the Folium maps of April 2025 in maps/, whose predictions were in-sample).

    python dashboard.py --area belfast --tag 2024

Reads, from data/<area>/model/:
  results/oof_<tag>.parquet        out-of-fold predictions (code/models/baseline.py, spatial validation)
  results/baseline_<tag>.csv       cross-validated metrics;  results/importance_<tag>.csv  LightGBM importance
  results/reproduce_old.csv        reproduction of the earlier set-up (code/models/reproduce_old.py), if present
  dataset_<year>.parquet           certificate attributes and selected features of the same certificates
Writes maps/dashboard/gbem_dashboard_<area>_<tag>.html (template: dashboard_template.html). The page holds
property-level data: it is kept local, never committed (.gitignore) or published.
The page loads deck.gl from unpkg and the Esri grey canvas basemaps, so it needs an internet connection.
URL options: ?theme=light|dark&view=0|250|500|1000 (0 = properties)&left=<variable>&right=<variable>.
"""
import argparse, base64, datetime, json, pathlib, re, sys
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from pyproj import Transformer
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

CODE = pathlib.Path(__file__).resolve().parents[1]
DATA = CODE.parent / "data"
EPSG = {"london": 27700, "belfast": 29902}
BANDS = list("ABCDEFG")
CATS = {"epc_property_type": "Property type", "epc_built_form": "Built form", "epc_construction_age_band": "Age band",
        "epc_tenure": "Tenure", "epc_main_fuel": "Main fuel"}
NUMS = [("epc_total_floor_area", "Floor area (m²)"), ("lidar_height_med_m", "LiDAR height, median (m)"),
        ("morph_height_m", "Building height, footprint data (m)"), ("morph_n_uprn", "Addresses in the footprint"),
        ("morph_shared_wall_ratio", "Shared wall ratio"), ("morph_bcov_100", "Building cover within 100 m"),
        ("landsatmulti_LST_summer_fp", "Summer LST 2020–2025, footprint (°C)"),
        ("landsatmulti_sUHI_summer_fp", "Summer surface UHI 2020–2025 (°C)"),
        ("landsatmulti_LST_winter_fp", "Winter LST 2020–2025, footprint (°C)")]
MODELS = {"lgbm": "LightGBM", "rf": "Random forest"}
SETS = {"eo": "EO only", "eo_morph": "EO + morphology", "eo_morph_ctx": "EO + morphology + context",
        "all": "All, incl. certificate attributes"}


def b64(a):
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()


def u1(codes, missing):
    a = np.asarray(codes, dtype="float64")
    return np.where(np.isnan(a) | missing, 255, a).astype("uint8")


def quad_fit(epsg, x, y):
    """National grid -> lon/lat as quadratics in x and y (for grid cells drawn in the page); returns coefficients and the
    largest error in metres over the data extent."""
    t = Transformer.from_crs(epsg, 4326, always_xy=True)
    gx, gy = np.meshgrid(np.linspace(np.nanmin(x) - 1000, np.nanmax(x) + 1000, 40), np.linspace(np.nanmin(y) - 1000, np.nanmax(y) + 1000, 40))
    gx, gy = gx.ravel(), gy.ravel()
    lon, lat = t.transform(gx, gy)
    x0, y0 = float(gx.mean()), float(gy.mean())
    u, v = (gx - x0) / 1e4, (gy - y0) / 1e4
    A = np.column_stack([np.ones_like(u), u, v, u * u, u * v, v * v])
    clon = np.linalg.lstsq(A, lon, rcond=None)[0]; clat = np.linalg.lstsq(A, lat, rcond=None)[0]
    err = np.hypot((A @ clon - lon) * 111320 * np.cos(np.radians(lat)), (A @ clat - lat) * 110540).max()
    return {"x0": x0, "y0": y0, "lon": clon.tolist(), "lat": clat.tolist()}, float(err)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--tag", required=True)
    a = ap.parse_args()
    res = DATA / a.area / "model" / "results"
    oof = pd.read_parquet(res / f"oof_{a.tag}.parquet")
    oof["id_cert"] = oof["id_cert"].astype(str)
    years = sorted(oof["year"].unique().tolist())
    want = ["id_cert"] + list(CATS) + [c for c, _ in NUMS]
    frames = []
    for yr in years:
        p = DATA / a.area / "model" / f"dataset_{yr}.parquet"
        have = [c for c in want if c in pq.ParquetFile(p).schema.names]
        frames.append(pd.read_parquet(p, columns=have))
    att = pd.concat(frames, ignore_index=True)
    att["id_cert"] = att["id_cert"].astype(str)
    d = oof.merge(att.drop_duplicates("id_cert"), on="id_cert", how="left")
    d = d[d["x"].notna()].reset_index(drop=True)
    lon, lat = Transformer.from_crs(EPSG[a.area], 4326, always_xy=True).transform(d["x"].to_numpy(), d["y"].to_numpy())
    cols = {"lon": ("f4", np.asarray(lon, "float32")), "lat": ("f4", np.asarray(lat, "float32")),
            "x": ("f4", d["x"].to_numpy("float32")), "y": ("f4", d["y"].to_numpy("float32")),
            "year": ("u1", (d["year"].astype(int) - 2000).to_numpy("uint8"))}
    band = lambda s: pd.Series(s).map({b: i for i, b in enumerate(BANDS)}).to_numpy("float64")
    cols["actual"] = ("u1", u1(band(d["actual"]), False))
    sap = lambda s: np.where(np.isnan(s), -32768, np.round(s)).astype("int16")
    cols["sap_actual"] = ("i2", sap(d["actual_sap"].to_numpy("float64")))
    runs = []
    for c in [c for c in oof.columns if c.startswith("pred_")]:
        m, fs = c[5:].split("_", 1)
        key = f"{m}_{fs}"
        cols[f"pred_{key}"] = ("u1", u1(band(d[c]), False))
        if f"conf_{key}" in d:
            cols[f"conf_{key}"] = ("u1", u1(np.round(d[f"conf_{key}"].to_numpy() * 100), False))
        if f"sap_{key}" in d:
            cols[f"sap_{key}"] = ("i2", sap(d[f"sap_{key}"].to_numpy("float64")))
        runs.append({"key": key, "model": m, "featureset": fs, "label": f"{MODELS.get(m, m)} · {SETS.get(fs, fs)}",
                     "has_sap": f"sap_{key}" in d, "has_conf": f"conf_{key}" in d})
    cats = {}
    for c, label in CATS.items():
        if c not in d:
            continue
        s = d[c].astype("string").str.replace(r"^(Northern Ireland|England and Wales):\s*", "", regex=True).str.strip()
        s = s.where(~s.isin(["", "NO DATA!", "INVALID!", "Not applicable", "nan", "None"]))
        vc = s.value_counts()
        keep_vals = vc.index[:30].tolist()                       # rarer values are folded into "Other"
        s = s.where(s.isin(keep_vals) | s.isna(), "Other")
        values = sorted(s.dropna().unique().tolist())
        codes = s.map({v: i for i, v in enumerate(values)}).to_numpy("float64")
        cols[c] = ("u1", u1(codes, False)); cats[c] = {"label": label, "values": values}
    nums = []
    for c, label in NUMS:
        if c not in d or d[c].notna().mean() < 0.05:
            continue
        v = pd.to_numeric(d[c], errors="coerce").to_numpy("float32")
        lo, hi = np.nanpercentile(v, [2, 98])
        cols[c] = ("f4", v); nums.append({"key": c, "label": label, "domain": [round(float(lo), 2), round(float(hi), 2)],
                                          "valid": round(float(np.isfinite(v).mean()), 3)})
    metrics = pd.read_csv(res / f"baseline_{a.tag}.csv")
    imp = pd.read_csv(res / f"importance_{a.tag}.csv") if (res / f"importance_{a.tag}.csv").exists() else pd.DataFrame()
    imp = imp.sort_values("gain", ascending=False).groupby("featureset").head(15) if len(imp) else imp
    old = pd.read_csv(res / "reproduce_old.csv") if (res / "reproduce_old.csv").exists() else pd.DataFrame()
    quad, qerr = quad_fit(EPSG[a.area], d["x"].to_numpy(), d["y"].to_numpy())
    payload = {
        "area": a.area, "tag": a.tag, "years": [int(y) for y in years], "n": len(d), "built": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "center": [float(np.nanmedian(lon)), float(np.nanmedian(lat))], "quad": quad,
        "bounds": [float(np.nanpercentile(lon, 0.5)), float(np.nanpercentile(lat, 0.5)),
                   float(np.nanpercentile(lon, 99.5)), float(np.nanpercentile(lat, 99.5))],
        "cols": {k: {"t": t, "b64": b64(v)} for k, (t, v) in cols.items()},
        "runs": runs, "cats": cats, "nums": nums,
        "metrics": json.loads(metrics.to_json(orient="records")), "importance": json.loads(imp.to_json(orient="records")),
        "old": json.loads(old.to_json(orient="records")),
    }
    html = (pathlib.Path(__file__).with_name("dashboard_template.html").read_text(encoding="utf-8")
            .replace("/*__DATA__*/null", json.dumps(payload, separators=(",", ":"))))
    out = CODE / "maps" / "dashboard" / f"gbem_dashboard_{a.area}_{a.tag}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    keep(out).write_text(html, encoding="utf-8")
    print(f"{a.area} {a.tag}: {len(d):,} certificates, {len(runs)} model runs, grid-cell fit error {qerr:.1f} m; "
          f"{out.stat().st_size / 1e6:.1f} MB -> {out}")


if __name__ == "__main__":
    main()
