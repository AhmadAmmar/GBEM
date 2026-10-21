"""Step 2 - preprocess the ingested rasters: derived layers that do not depend on the buildings.

    python preprocess.py [--areas london belfast] [--years 2024]

Static (once per area), in data/<area>/gee_v2/derived/:
  terrain_30m.tif        elevation (DEM values below -5 m masked: water artefacts of the surface model), slope (deg),
                         eastness sin(aspect), northness cos(aspect), terrain ruggedness index (mean absolute
                         difference to the 8 neighbours, m)
  landcover_100m.tif     share of each WorldCover 2021 class in each 100 m cell: built-up, tree, grassland, cropland,
                         water, bare (core extent; 10 x 10 blocks of the 10 m map)
Per year:
  era5_derived_1000m_<year>.tif   wind speed and direction (degrees the wind blows from) of the mean wind vector,
                         per window; sea pixels (no ERA5-Land value) are missing in every band
  uhi_reference_<year>.csv        rural reference surface temperature per product and window: median over pixels of
                         the context extent outside the core extent, without built-up volume (GHSL 2020) and above
                         2 m elevation (to leave out sea and estuaries). The surface urban heat island of a pixel is
                         its temperature minus this reference; extract.py computes it.
A record of the parameters is written to derived/preprocess_log.json.
"""
import argparse, json, datetime
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import rowcol
import spec

PROFILE = {"driver": "GTiff", "dtype": "float32", "nodata": spec.NODATA_FLOAT, "compress": "deflate", "predictor": 3,
           "tiled": True, "blockxsize": 256, "blockysize": 256}
DEM_MIN = -5.0
WC_CLASSES = {"built": 50, "tree": 10, "grass": 30, "crop": 40, "water": 80, "bare": 60}


def read(path, band=None):
    with rasterio.open(path) as r:
        names = list(r.descriptions)
        idx = range(1, r.count + 1) if band is None else [names.index(band) + 1]
        out = {names[i - 1]: np.where(r.read(i) == r.nodata, np.nan, r.read(i).astype("float32")) for i in idx}
        return out, r.profile


def write(path, bands, profile):
    p = {**profile, **PROFILE, "count": len(bands)}
    with rasterio.open(path, "w", **p) as dst:
        for i, (name, a) in enumerate(bands.items(), 1):
            dst.write(np.where(np.isnan(a), spec.NODATA_FLOAT, a).astype("float32"), i)
            dst.set_band_description(i, name)
    print("written", path)


def terrain(area):
    d, prof = read(spec.raw_path(area, "dem_30m"))
    z = d["elevation_m"]
    z[z < DEM_MIN] = np.nan
    res = prof["transform"].a
    gy, gx = np.gradient(z, res)                    # rows increase southwards
    dzdx, dzdy = gx, -gy                            # east and north components
    slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    aspect = np.arctan2(-dzdx, -dzdy)               # direction the slope faces, clockwise from north
    pad = np.pad(z, 1, constant_values=np.nan)
    diffs = [np.abs(pad[1 + dy:pad.shape[0] - 1 + dy, 1 + dx:pad.shape[1] - 1 + dx] - z)
             for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0)]
    tri = np.nanmean(np.stack(diffs), axis=0)
    flat = slope < 0.5                              # aspect is undefined on flat ground
    write(spec.derived_dir(area) / "terrain_30m.tif",
          {"elevation_m": z, "slope_deg": slope, "eastness": np.where(flat, 0, np.sin(aspect)),
           "northness": np.where(flat, 0, np.cos(aspect)), "tri_m": np.where(np.isnan(z), np.nan, tri)}, prof)


def landcover(area):
    with rasterio.open(spec.raw_path(area, "worldcover_10m")) as r:
        wc, prof = r.read(1), r.profile
    h, w = (wc.shape[0] // 10) * 10, (wc.shape[1] // 10) * 10
    blocks = wc[:h, :w].reshape(h // 10, 10, w // 10, 10)
    bands = {f"frac_{k}": (blocks == v).mean(axis=(1, 3)).astype("float32") for k, v in WC_CLASSES.items()}
    t = prof["transform"]
    prof.update(width=w // 10, height=h // 10, transform=rasterio.Affine(t.a * 10, 0, t.c, 0, t.e * 10, t.f))
    write(spec.derived_dir(area) / "landcover_100m.tif", bands, prof)


def era5(area, year):
    d, prof = read(spec.raw_path(area, "era5", year))
    land = ~np.isnan(d[f"t2m_annual"])
    out = {}
    for w in spec.windows("era5", year):
        u, v = d[f"u10_{w}"], d[f"v10_{w}"]
        out[f"wind_speed_{w}"] = np.where(land, np.hypot(u, v), np.nan)
        out[f"wind_from_deg_{w}"] = np.where(land, (np.degrees(np.arctan2(-u, -v)) + 360) % 360, np.nan)
    write(spec.derived_dir(area) / f"era5_derived_1000m_{year}.tif", out, prof)


def rural_mask(area, path):
    """Pixels of the raster at `path` that serve as rural reference (see module text)."""
    a = spec.AREAS[area]
    with rasterio.open(path) as r:
        h, w, t = r.height, r.width, r.transform
    rows, cols = np.mgrid[0:h, 0:w]
    xs, ys = t.c + (cols + 0.5) * t.a, t.f + (rows + 0.5) * t.e
    x0, y0, x1, y1 = a["core"]
    outside_core = ~((xs >= x0) & (xs < x1) & (ys >= y0) & (ys < y1))

    def sample(p, band):
        with rasterio.open(p) as s:
            arr = s.read(list(s.descriptions).index(band) + 1)
            rr, cc = rowcol(s.transform, xs.ravel(), ys.ravel())
            rr, cc = np.clip(rr, 0, s.height - 1), np.clip(cc, 0, s.width - 1)
            v = arr[rr, cc].reshape(h, w).astype("float32")
            v[v == s.nodata] = np.nan
            return v
    vol = sample(spec.raw_path(area, "ghsl_100m"), "built_volume_2020_m3")
    dem = sample(spec.derived_dir(area) / "terrain_30m.tif", "elevation_m")
    return outside_core & (vol == 0) & (dem > 2)


def uhi_reference(area, year):
    rows = []
    for prod, scale in (("landsat", 30), ("modis", 1000)):
        path = spec.raw_path(area, prod, year)
        mask = rural_mask(area, path)
        d, _ = read(path)
        for name, a in d.items():
            stem = name.rsplit("_", 1)[0]
            if stem.endswith("_n") or stem == "n":
                continue
            v = a[mask & ~np.isnan(a)] / spec.PRODUCTS[prod]["div"][stem]
            rows.append({"area": area, "year": year, "product": prod, "band": name, "n_rural_pixels": int(v.size),
                         "rural_median_C": round(float(np.median(v)), 3) if v.size else None,
                         "rural_iqr_C": round(float(np.subtract(*np.percentile(v, [75, 25]))), 3) if v.size else None})
    df = pd.DataFrame(rows)
    out = spec.derived_dir(area) / f"uhi_reference_{year}.csv"
    df.to_csv(out, index=False)
    print("written", out)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--areas", nargs="+", default=list(spec.AREAS)); ap.add_argument("--years", nargs="+", type=int, default=[2024])
    a = ap.parse_args()
    for area in a.areas:
        spec.derived_dir(area).mkdir(parents=True, exist_ok=True)
        terrain(area)
        landcover(area)
        for y in a.years:
            era5(area, y)
            print(uhi_reference(area, y).to_string(index=False))
        log = {"run": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "method": spec.METHOD, "years": a.years,
               "dem_min_m": DEM_MIN, "worldcover_classes": WC_CLASSES,
               "rural_reference": "context extent outside core extent, GHSL built volume 2020 = 0, elevation > 2 m; median"}
        (spec.derived_dir(area) / "preprocess_log.json").write_text(json.dumps(log, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
