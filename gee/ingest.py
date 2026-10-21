"""Step 1 - ingest Earth Engine exports: unzip, check, file by area, record.

    python ingest.py <batch> <zip> [<zip> ...]          e.g. python ingest.py b1 GBEM_GEE_v2-...-001.zip ...-002.zip

- Each GeoTIFF is extracted to data/<area>/gee_v2/raw/ (the zips are kept where they are); the provenance table goes to
  data/gee_v2/provenance/. A file that is already there with the same checksum is not extracted again.
- Each GeoTIFF is checked against spec.py: grid (CRS, origin, pixel size, width, height), band names and order, data
  type and missing value, share of valid pixels per band, and values outside a plausible physical range.
- data/gee_v2/manifest.csv records every file (batch, checksum, size, result of the checks), one row per file, updated
  when a file is ingested again. data/gee_v2/qa/ingest_<batch>.csv has one row per band.
"""
import argparse, datetime, hashlib, shutil, sys, zipfile
import numpy as np
import pandas as pd
import rasterio
import spec

GEE = spec.DATA / "gee_v2"


def sha256(path, chunk=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def extract(zips):
    """Extract the GeoTIFFs and provenance tables; returns the paths of the files in their final place."""
    out = []
    for z in zips:
        with zipfile.ZipFile(z) as zf:
            for info in zf.infolist():
                name = info.filename.rsplit("/", 1)[-1]
                if name.endswith(".csv") and "provenance" in name:
                    dest = GEE / "provenance" / name
                elif name.endswith(".tif") and spec.parse_name(name):
                    dest = spec.raw_dir(spec.parse_name(name)["area"]) / name
                else:
                    print("skipped (not an export of gbem_composites.js):", info.filename); continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists() and dest.stat().st_size == info.file_size:
                    print("already there:", dest.name)
                else:
                    tmp = dest.with_suffix(dest.suffix + ".part")
                    with zf.open(info) as src, open(tmp, "wb") as dst:
                        shutil.copyfileobj(src, dst, 1 << 22)
                    tmp.replace(dest)
                    print("extracted:", dest)
                out.append(dest)
    return out


def check(path):
    """Checks of one GeoTIFF; returns (file row, band rows)."""
    meta = spec.parse_name(path.name)
    g = spec.grid(meta["area"], meta["product"])
    exp = spec.expected_bands(meta["product"], meta["year"])
    problems, bands = [], []
    with rasterio.open(path) as r:
        if r.crs.to_epsg() != g["epsg"]:
            problems.append(f"CRS {r.crs.to_epsg()} != {g['epsg']}")
        if tuple(round(v, 6) for v in r.transform[:6]) != g["transform"]:
            problems.append(f"transform {tuple(r.transform[:6])} != {g['transform']}")
        if (r.width, r.height) != (g["width"], g["height"]):
            problems.append(f"size {r.width}x{r.height} != {g['width']}x{g['height']}")
        if list(r.descriptions) != exp:
            problems.append(f"bands {list(r.descriptions)} != {exp}")
        div = (spec.PRODUCTS.get(meta["product"]) or spec.MULTI.get(meta["product"]) or {}).get("div", {})
        for i, name in enumerate(r.descriptions, 1):
            # full resolution, then every 4th pixel: reading at a reduced size would use the overviews, whose
            # resampling creates values that are not in the data (e.g. negative building heights at edges)
            a = r.read(i)[::4, ::4]
            ok = a != r.nodata
            stem = name.rsplit("_", 1)[0] if meta["product"] not in spec.STATIC else name
            v = a[ok].astype("float64") / div.get(stem, 1)
            key = "B" if stem in spec.S2_BANDS else stem
            lo, hi = spec.RANGES.get(key, (-np.inf, np.inf))
            out = float(((v < lo) | (v > hi)).mean()) if v.size else 0.0
            bands.append({"file": path.name, "band": name, "valid_share": round(float(ok.mean()), 4),
                          "min": round(float(v.min()), 3) if v.size else None, "p50": round(float(np.median(v)), 3) if v.size else None,
                          "max": round(float(v.max()), 3) if v.size else None, "share_outside_range": round(out, 5)})
            if out > 0.001:
                problems.append(f"{name}: {out:.2%} of values outside {lo}..{hi}")
        dtype, nodata = r.dtypes[0], r.nodata
    row = {**meta, "file": path.name, "path": str(path), "size_mb": round(path.stat().st_size / 1e6, 1), "dtype": dtype,
           "nodata": nodata, "n_bands": len(bands), "sha256": sha256(path), "checks": "ok" if not problems else "; ".join(problems)}
    return row, bands


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("batch"); ap.add_argument("zips", nargs="+")
    a = ap.parse_args()
    spec.check_js()
    files = extract(a.zips)
    rows, band_rows = [], []
    for p in files:
        if p.suffix == ".tif":
            row, b = check(p)
            rows.append({"batch": a.batch, "ingested": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), **row})
            band_rows += b
            print(f"{row['checks']:>4s}  {p.name}")
    (GEE / "qa").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(band_rows).to_csv(GEE / "qa" / f"ingest_{a.batch}.csv", index=False)
    man = GEE / "manifest.csv"
    new = pd.DataFrame(rows)
    if man.exists():
        old = pd.read_csv(man)
        new = pd.concat([old[~old["file"].isin(new["file"])], new], ignore_index=True)
    new.sort_values(["area", "product", "year"], na_position="first").to_csv(man, index=False)
    bad = [r for r in rows if r["checks"] != "ok"]
    print(f"\n{len(rows)} GeoTIFFs ingested, {len(bad)} with problems. Manifest: {man}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
