"""Step 3 - values of the Earth Engine products for each building (certificate), for one year.

    python extract.py --area london --year 2024 --buildings <polygons> --id <col> [--lon <col> --lat <col>]
                      [--points <csv with id, lon, lat>] --tag <name>

For every record of the buildings file (one row per certificate; several may share a footprint), three values are
computed per variable where the resolution allows:
  _pt     at the point: the certificate's coordinates (WGS84 lon/lat columns or --points file), or else a point inside
          the footprint
  _fp     mean over the footprint: pixels whose centre lies in the footprint polygon (identical footprints are
          rasterised once); a footprint without such a pixel takes the point value, and fp_px_<grid> = 0 records it
  _nb100  mean over the square neighbourhood of about 100 m centred on the point (11 x 11 pixels at 10 m, 3 x 3 at 30 m)
Products and variables:
  s2 (10 m)       reflectance B2-B12 and indices per pixel, then averaged: NDVI, GNDVI, NDRE1 (B8A, B5), NDRE2 (B8A,
                  B6), NDWI (B3, B8), MNDWI (B3, B11), NDMI (B8, B11), NDBI (B11, B8), UI (B12, B8), BSI, EVI, SAVI,
                  MSAVI2, BUI (NDBI - NDVI), NIRv (NDVI x B8), VARI
  s1 (10 m)       VV and VH averaged in linear power, then in dB; VVminusVH_dB = 10 log10(VV/VH); span_dB = 10 log10(VV+VH)
  landsat (30 m)  LST (deg C) and sUHI = LST minus the rural reference of preprocess.py (point and neighbourhood
                  only: almost no footprint contains a 30 m pixel centre)
  point only      modis day/night LST and sUHI (1 km); era5 climate, wind speed and direction (1 km grid); viirs night
                  lights (500 m); ghsl building height and volume (100 m); landcover shares (100 m); terrain (30 m);
                  WorldCover class at the point (10 m)
Output: data/<area>/gee_v2/features/<tag>_<year>.parquet and .csv, and <tag>_<year>_log.json.
"""
import argparse, json, datetime
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio import features as rfeatures
from rasterio.windows import Window
from scipy.ndimage import uniform_filter
from shapely import force_2d
import spec

STRIP = 512          # rows per strip for the 10 m and 30 m rasters
NB_M = 100           # neighbourhood size in metres


def nb_px(scale):
    k = max(3, int(round(NB_M / scale)))
    return k if k % 2 else k + 1


def s2_indices(b):
    """Indices from decoded Sentinel-2 reflectance (dict of arrays)."""
    nd = lambda a, c: (a - c) / (a + c)
    B2, B3, B4, B5, B6, B8, B8A, B11, B12 = (b[k] for k in ("B2", "B3", "B4", "B5", "B6", "B8", "B8A", "B11", "B12"))
    ndvi, ndbi, mndwi = nd(B8, B4), nd(B11, B8), nd(B3, B11)
    savi = 1.5 * (B8 - B4) / (B8 + B4 + 0.5)
    out = {"NDVI": ndvi, "GNDVI": nd(B8, B3), "NDRE1": nd(B8A, B5), "NDRE2": nd(B8A, B6), "NDWI": nd(B3, B8),
           "MNDWI": mndwi, "NDMI": nd(B8, B11), "NDBI": ndbi, "UI": nd(B12, B8),
           "BSI": ((B11 + B4) - (B8 + B2)) / ((B11 + B4) + (B8 + B2)),
           "EVI": 2.5 * (B8 - B4) / (B8 + 6 * B4 - 7.5 * B2 + 1), "SAVI": savi,
           "MSAVI2": (2 * B8 + 1 - np.sqrt(np.maximum((2 * B8 + 1) ** 2 - 8 * (B8 - B4), 0))) / 2,
           "BUI": ndbi - ndvi, "NIRv": ndvi * B8, "VARI": (B3 - B4) / (B3 + B4 - B2)}
    # IBI is not derived: its denominator can be close to zero (earlier values reached +-30 000), and its parts
    # (NDBI, SAVI, MNDWI) are features already
    return {k: np.where(np.isfinite(v), v, np.nan).astype("float32") for k, v in out.items()}


def load_buildings(a, epsg):
    g = gpd.read_file(a.buildings)
    g["geometry"] = force_2d(g.geometry.values)
    g = g.to_crs(epsg)
    g["rec_id"] = g[a.id].astype(str)
    if a.points:
        p = pd.read_csv(a.points)
        p["rec_id"] = p[a.id].astype(str)
        g = g.merge(p[["rec_id", a.lon, a.lat]], on="rec_id", how="left")
    if a.lon and a.lon in g:
        pts = gpd.GeoSeries(gpd.points_from_xy(g[a.lon], g[a.lat]), crs=4326).to_crs(epsg)
        rep = g.geometry.representative_point()
        g["pt"] = [p if p is not None and not p.is_empty else r for p, r in zip(pts, rep)]
        g["pt_source"] = np.where(g[a.lon].notna(), "certificate", "footprint")
    else:
        g["pt"] = g.geometry.representative_point(); g["pt_source"] = "footprint"
    g["fp_key"] = g.geometry.to_wkb()
    keys = {k: i + 1 for i, k in enumerate(pd.unique(g["fp_key"]))}   # identical footprints share one label
    g["fp_label"] = g["fp_key"].map(keys).astype("int32")
    uniq = g.drop_duplicates("fp_label")[["fp_label", "geometry"]]
    return g.drop(columns=["fp_key"]), uniq


class Grid:
    """Footprint labels and point positions on one raster grid."""

    def __init__(self, path, uniq, pts):
        with rasterio.open(path) as r:
            self.t, self.h, self.w, self.scale = r.transform, r.height, r.width, r.transform.a
        self.labels = rfeatures.rasterize(((geom, lab) for geom, lab in zip(uniq.geometry, uniq.fp_label)),
                                          out_shape=(self.h, self.w), transform=self.t, fill=0, dtype="int32")
        self.n_lab = int(uniq.fp_label.max()) + 1
        self.px = np.bincount(self.labels.ravel(), minlength=self.n_lab)
        rows = np.floor((np.array([p.y for p in pts]) - self.t.f) / self.t.e).astype(int)
        cols = np.floor((np.array([p.x for p in pts]) - self.t.c) / self.t.a).astype(int)
        self.inside = (rows >= 0) & (rows < self.h) & (cols >= 0) & (cols < self.w)
        self.rows, self.cols = np.where(self.inside, rows, 0), np.where(self.inside, cols, 0)


def zonal_strips(path, grid, compute, recs, k):
    """Point, footprint and neighbourhood means of the variables returned by compute(band dict) for each record."""
    half = k // 2
    sums, cnts, pt, nb = {}, {}, {}, {}
    with rasterio.open(path) as r:
        names = list(r.descriptions)
        for r0 in range(0, grid.h, STRIP):
            r1 = min(grid.h, r0 + STRIP)
            a0, a1 = max(0, r0 - half), min(grid.h, r1 + half)        # strip with a halo for the neighbourhood
            raw = r.read(window=Window(0, a0, grid.w, a1 - a0))
            bands = {n: np.where(raw[i] == r.nodata, np.nan, raw[i].astype("float32")) for i, n in enumerate(names)}
            vars_ = compute(bands)
            lab = grid.labels[r0:r1]
            sel = grid.inside & (grid.rows >= r0) & (grid.rows < r1)
            rr, cc = grid.rows[sel] - a0, grid.cols[sel]
            for name, v in vars_.items():
                core = v[r0 - a0:r1 - a0]
                ok = ~np.isnan(core) & (lab > 0)
                sums.setdefault(name, np.zeros(grid.n_lab)); cnts.setdefault(name, np.zeros(grid.n_lab))
                sums[name] += np.bincount(lab[ok], weights=core[ok], minlength=grid.n_lab)
                cnts[name] += np.bincount(lab[ok], minlength=grid.n_lab)
                pt.setdefault(name, np.full(len(recs), np.nan))[sel] = v[rr, cc]
                valid = ~np.isnan(v)
                s = uniform_filter(np.where(valid, v, 0), size=k, mode="constant")
                c = uniform_filter(valid.astype("float32"), size=k, mode="constant")
                nb.setdefault(name, np.full(len(recs), np.nan))[sel] = np.where(c[rr, cc] > 0, s[rr, cc] / np.maximum(c[rr, cc], 1e-9), np.nan)
    out = {}
    lab_rec = recs["fp_label"].to_numpy()
    for name in sums:
        fp = np.where(cnts[name] > 0, sums[name] / np.maximum(cnts[name], 1), np.nan)[lab_rec]
        out[name] = {"pt": pt[name], "fp": np.where(np.isnan(fp), pt[name], fp), "nb": nb[name]}
    return out


def point_values(path, recs, epsg, div=None):
    div = div or {}
    pts = recs["pt"]
    with rasterio.open(path) as r:
        names = list(r.descriptions)
        rows, cols = rasterio.transform.rowcol(r.transform, [p.x for p in pts], [p.y for p in pts])
        rows, cols = np.array(rows), np.array(cols)
        inside = (rows >= 0) & (rows < r.height) & (cols >= 0) & (cols < r.width)
        out = {}
        for i, n in enumerate(names, 1):
            a = r.read(i)
            v = np.full(len(pts), np.nan, dtype="float64")
            v[inside] = a[rows[inside], cols[inside]]
            v[v == r.nodata] = np.nan
            stem = n.rsplit("_", 1)[0]
            out[n] = v / div.get(stem, 1)
        return out


def run(a):
    epsg = spec.AREAS[a.area]["epsg"]
    recs, uniq = load_buildings(a, epsg)
    y = a.year
    cols = {"rec_id": recs["rec_id"].values, "year": y, "pt_source": recs["pt_source"].values}
    log = {"run": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "method": spec.METHOD, "area": a.area, "year": y,
           "buildings": a.buildings, "points": a.points, "n_records": len(recs), "n_footprints": len(uniq), "nb_m": NB_M}

    # Sentinel-2
    p = spec.raw_path(a.area, "s2", y)
    g10 = Grid(p, uniq, recs["pt"])
    cols["fp_px_10m"] = g10.px[recs["fp_label"].to_numpy()]

    def s2_vars(b):
        out = {}
        for w in spec.WINDOWS["s2"]:
            refl = {k: b[f"{k}_{w}"] / 10000 for k in spec.S2_BANDS}
            out.update({f"s2_{k}_{w}": v for k, v in refl.items()})
            out.update({f"s2_{k}_{w}": v for k, v in s2_indices(refl).items()})
        return out
    for name, st in zonal_strips(p, g10, s2_vars, recs, nb_px(10)).items():
        for s, v in st.items():
            cols[f"{name}_{s if s != 'nb' else 'nb100'}"] = v
    print("s2 done")

    # Sentinel-1: linear power first, dB after averaging
    p = spec.raw_path(a.area, "s1", y)

    def s1_vars(b):
        return {f"s1_{pol}lin_{w}": 10 ** (b[f"{pol}_{w}"] / 100 / 10) for w in spec.WINDOWS["s1"] for pol in ("VV", "VH")}
    s1 = zonal_strips(p, g10, s1_vars, recs, nb_px(10))
    for w in spec.WINDOWS["s1"]:
        for s in ("pt", "fp", "nb"):
            suf = s if s != "nb" else "nb100"
            vv, vh = s1[f"s1_VVlin_{w}"][s], s1[f"s1_VHlin_{w}"][s]
            with np.errstate(divide="ignore", invalid="ignore"):
                cols[f"s1_VV_dB_{w}_{suf}"] = 10 * np.log10(vv)
                cols[f"s1_VH_dB_{w}_{suf}"] = 10 * np.log10(vh)
                cols[f"s1_VVminusVH_dB_{w}_{suf}"] = 10 * np.log10(vv / vh)
                cols[f"s1_span_dB_{w}_{suf}"] = 10 * np.log10(vv + vh)
    print("s1 done")

    # Landsat LST and sUHI
    p = spec.raw_path(a.area, "landsat", y)
    g30 = Grid(p, uniq, recs["pt"])
    cols["fp_px_30m"] = g30.px[recs["fp_label"].to_numpy()]
    ref = pd.read_csv(spec.derived_dir(a.area) / f"uhi_reference_{y}.csv").set_index("band")["rural_median_C"]

    def ls_vars(b):
        return {f"landsat_LST_{w}": b[f"LST_{w}"] / 100 for w in spec.windows("landsat", y)}
    for name, st in zonal_strips(p, g30, ls_vars, recs, nb_px(30)).items():
        w = name.split("_")[-1]
        # no footprint mean at 30 m: almost no footprint contains a 30 m pixel centre, so it would repeat the point value
        for s, v in ((s, v) for s, v in st.items() if s != "fp"):
            suf = s if s != "nb" else "nb100"
            cols[f"{name}_{suf}"] = v
            cols[f"landsat_sUHI_{w}_{suf}"] = v - ref[f"LST_{w}"]
    print("landsat done")

    # point-only products
    for name, v in point_values(spec.raw_path(a.area, "modis", y), recs, epsg, spec.PRODUCTS["modis"]["div"]).items():
        cols[f"modis_{name}_pt"] = v
        if name in ref.index:                       # temperature bands (not the counts) have a rural reference
            cols[f"modis_sUHI_{name}_pt"] = v - ref[name]
    for prod, path in (("era5", spec.raw_path(a.area, "era5", y)), ("era5", spec.derived_dir(a.area) / f"era5_derived_1000m_{y}.tif"),
                       ("viirs", spec.raw_path(a.area, "viirs", y)), ("ghsl", spec.raw_path(a.area, "ghsl_100m")),
                       ("lc", spec.derived_dir(a.area) / "landcover_100m.tif"), ("terrain", spec.derived_dir(a.area) / "terrain_30m.tif")):
        for name, v in point_values(path, recs, epsg).items():
            cols[f"{prod}_{name}_pt"] = v
    cols["worldcover_class_pt"] = point_values(spec.raw_path(a.area, "worldcover_10m"), recs, epsg)["worldcover_2021"]
    # ERA5-Land has no values over the sea: mask every ERA5 band where temperature is missing
    sea = np.isnan(cols["era5_t2m_annual_pt"])
    for c in [c for c in cols if c.startswith("era5_")]:
        cols[c] = np.where(sea, np.nan, cols[c])
    print("point products done")

    out = pd.DataFrame(cols)
    d = spec.features_dir(a.area); d.mkdir(parents=True, exist_ok=True)
    base = d / f"{a.tag}_{y}"
    out.to_parquet(base.with_suffix(".parquet"), index=False)
    out.to_csv(base.with_suffix(".csv"), index=False)
    log.update({"n_features": out.shape[1] - 3, "fp_without_pixel_10m": int((out["fp_px_10m"] == 0).sum()),
                "fp_without_pixel_30m": int((out["fp_px_30m"] == 0).sum()),
                "missing_share": {c: round(float(out[c].isna().mean()), 4) for c in out.columns if out[c].isna().any()}})
    base.with_name(base.name + "_log.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
    print(f"written {base}.parquet: {len(out)} records, {out.shape[1] - 3} features")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True, choices=list(spec.AREAS)); ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--buildings", required=True); ap.add_argument("--id", required=True)
    ap.add_argument("--lon"); ap.add_argument("--lat"); ap.add_argument("--points"); ap.add_argument("--tag", required=True)
    run(ap.parse_args())
