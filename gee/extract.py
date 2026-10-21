"""Step 3 - values of the Earth Engine products for each certificate (or building), for one imagery year.

Version 2 (21 October 2026): area-weighted footprint means; neighbourhoods at several scales with standard deviation;
certificate mode.

    certificates (normal use): the linked certificate table of code/epc, certificates inspected in --year
        python extract.py --area belfast --year 2024 --certificates [--tag certs]
    any buildings file (used for the comparison with the earlier samples):
        python extract.py --area london --year 2024 --buildings <polygons> --id <col> [--lon <col> --lat <col>]
                          [--points <csv with id, lon, lat>] --tag <name>

Values per variable, where the resolution allows:
  _pt          at the point: the certificate's UPRN location (or the given coordinates, else a point in the footprint)
  _fp          area-weighted mean over the footprint: every pixel the footprint touches counts in proportion to the
               share of the pixel it covers (footprints rasterised on a 5 x 5 sub-grid, i.e. 2 m for 10 m pixels);
               certificates without a linked footprint take the point value; fp_px_<grid> = footprint area in pixels
  _nb<m>       mean over a square neighbourhood of about <m> metres centred on the point
  _nb<m>sd     standard deviation over that neighbourhood (heterogeneity); not at 50 m
  scales       10 m products: 50, 100, 250, 500 m (5, 11, 25, 51 pixels); 30 m products: 100, 250, 500 m (3, 9, 17)
Products and variables:
  s2 (10 m)       reflectance B2-B12 and indices per pixel, then averaged: NDVI, GNDVI, NDRE1 (B8A, B5), NDRE2 (B8A,
                  B6), NDWI (B3, B8), MNDWI (B3, B11), NDMI (B8, B11), NDBI (B11, B8), UI (B12, B8), BSI, EVI, SAVI,
                  MSAVI2, BUI (NDBI - NDVI), NIRv (NDVI x B8), VARI
  s1 (10 m)       VV and VH averaged in linear power, then in dB; VVminusVH_dB = 10 log10(VV/VH); span_dB = 10 log10(VV+VH);
                  neighbourhood SD of VV and VH in dB (texture)
  landsat (30 m)  LST (deg C) and sUHI = LST minus the rural reference of preprocess.py (point and neighbourhoods)
  point only      modis day/night LST and sUHI (1 km); era5 climate, wind speed and direction (1 km grid); viirs night
                  lights (500 m); ghsl building height and volume (100 m); landcover shares (100 m); terrain (30 m);
                  WorldCover class at the point (10 m)
Output: data/<area>/gee_v2/features/<tag>_<year>.parquet (and .csv), <tag>_<year>_log.json
"""
import argparse, json, datetime
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio import features as rfeatures
from rasterio.windows import Window
from scipy.ndimage import uniform_filter
import shapely
from shapely import force_2d
import spec
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

STRIP = 256                                          # rows per strip
SUB = 5                                              # sub-grid factor for the footprint coverage
SCALES = {10: {50: 5, 100: 11, 250: 25, 500: 51}, 30: {100: 3, 250: 9, 500: 17}}
SD_MIN_M = 100                                       # no standard deviation in neighbourhoods smaller than this
EPC = spec.DATA                                      # data/<area>/epc/


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
    with np.errstate(all="ignore"):
        return {k: np.where(np.isfinite(v), v, np.nan).astype("float32") for k, v in out.items()}


def load_certificates(area, year):
    """Certificates inspected in `year`, with UPRN point and linked footprint (code/epc)."""
    c = pd.read_parquet(EPC / area / "epc" / "certificates_linked.parquet",
                        columns=["cert_id", "UPRN", "year", "x", "y", "fp_id", "link_method"])
    c = c[c["year"] == year].reset_index(drop=True)
    fp = gpd.read_parquet(EPC / area / "epc" / "footprints.parquet", columns=["fp_id", "geometry"])
    fp = fp[fp["fp_id"].isin(c["fp_id"].dropna().unique())].reset_index(drop=True)
    fp["fp_label"] = np.arange(1, len(fp) + 1, dtype="int32")
    c = c.merge(fp[["fp_id", "fp_label"]], on="fp_id", how="left")
    c["fp_label"] = c["fp_label"].fillna(0).astype("int32")
    recs = pd.DataFrame({"rec_id": c["cert_id"].astype(str), "UPRN": c["UPRN"], "fp_id": c["fp_id"],
                         "link_method": c["link_method"], "fp_label": c["fp_label"], "pt_source": "uprn"})
    recs["pt"] = list(shapely.points(c["x"].to_numpy(), c["y"].to_numpy()))
    return recs, fp[["fp_label", "geometry"]]


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
    """Footprint coverage (label, pixel, covered share) per strip, and point positions, on one raster grid."""

    def __init__(self, path, uniq, pts):
        with rasterio.open(path) as r:
            self.t, self.h, self.w = r.transform, r.height, r.width
        self.n_lab = int(uniq["fp_label"].max()) + 1 if len(uniq) else 1
        self.px = np.zeros(self.n_lab)
        self.cover = {}
        geoms, labs = uniq.geometry.values, uniq["fp_label"].to_numpy()
        tree = shapely.STRtree(geoms)
        t = self.t
        for r0 in range(0, self.h, STRIP):
            r1 = min(self.h, r0 + STRIP)
            ytop, ybot = t.f + r0 * t.e, t.f + r1 * t.e
            q = tree.query(shapely.box(t.c, ybot, t.c + self.w * t.a, ytop))
            if not len(q):
                continue
            fine = rasterio.Affine(t.a / SUB, 0, t.c, 0, t.e / SUB, ytop)
            L = rfeatures.rasterize(zip(geoms[q], labs[q]), out_shape=((r1 - r0) * SUB, self.w * SUB), transform=fine,
                                    fill=0, dtype="int32")
            rr, cc = np.nonzero(L)
            n_px = (r1 - r0) * self.w
            key = L[rr, cc].astype("int64") * n_px + (rr // SUB) * self.w + cc // SUB
            k, cnt = np.unique(key, return_counts=True)
            lab, pix, wgt = (k // n_px).astype("int32"), (k % n_px).astype("int64"), cnt / SUB ** 2
            self.cover[r0] = (lab, pix, wgt)
            np.add.at(self.px, lab, wgt)
        rows = np.floor((np.array([p.y for p in pts]) - t.f) / t.e).astype(int)
        cols = np.floor((np.array([p.x for p in pts]) - t.c) / t.a).astype(int)
        self.inside = (rows >= 0) & (rows < self.h) & (cols >= 0) & (cols < self.w)
        self.rows, self.cols = np.where(self.inside, rows, 0), np.where(self.inside, cols, 0)


def zonal_strips(path, grid, compute, recs, scales, sd_vars=None):
    """Point, area-weighted footprint, and neighbourhood mean (and SD) of the variables of compute(bands)."""
    half = max(scales.values()) // 2
    n = len(recs)
    sums, wts, out = {}, {}, {}
    with rasterio.open(path) as r:
        names = list(r.descriptions)
        for r0 in range(0, grid.h, STRIP):
            r1 = min(grid.h, r0 + STRIP)
            a0, a1 = max(0, r0 - half), min(grid.h, r1 + half)          # strip with a halo for the neighbourhoods
            raw = r.read(window=Window(0, a0, grid.w, a1 - a0))
            bands = {nm: np.where(raw[i] == r.nodata, np.nan, raw[i].astype("float32")) for i, nm in enumerate(names)}
            vars_ = compute(bands)
            sel = grid.inside & (grid.rows >= r0) & (grid.rows < r1)
            rr, cc = grid.rows[sel] - a0, grid.cols[sel]
            cov = grid.cover.get(r0)
            for name, v in vars_.items():
                o = out.setdefault(name, {})
                o.setdefault("pt", np.full(n, np.nan))[sel] = v[rr, cc]
                if cov is not None:
                    lab, pix, wgt = cov
                    core = v[r0 - a0:r1 - a0].ravel()[pix]
                    ok = ~np.isnan(core)
                    sums.setdefault(name, np.zeros(grid.n_lab)); wts.setdefault(name, np.zeros(grid.n_lab))
                    sums[name] += np.bincount(lab[ok], weights=wgt[ok] * core[ok], minlength=grid.n_lab)
                    wts[name] += np.bincount(lab[ok], weights=wgt[ok], minlength=grid.n_lab)
                valid = ~np.isnan(v)
                v0 = np.where(valid, v, 0).astype("float64")
                for m, k in scales.items():
                    c = uniform_filter(valid.astype("float64"), size=k, mode="constant")[rr, cc]
                    s = uniform_filter(v0, size=k, mode="constant")[rr, cc]
                    mean = np.where(c > 0, s / np.maximum(c, 1e-12), np.nan)
                    o.setdefault(f"nb{m}", np.full(n, np.nan))[sel] = mean
                    if m >= SD_MIN_M and (sd_vars is None or name in sd_vars):
                        s2 = uniform_filter(v0 ** 2, size=k, mode="constant")[rr, cc]
                        var = np.where(c > 0, s2 / np.maximum(c, 1e-12) - mean ** 2, np.nan)
                        o.setdefault(f"nb{m}sd", np.full(n, np.nan))[sel] = np.sqrt(np.clip(var, 0, None))
    lab_rec = recs["fp_label"].to_numpy()
    for name, o in out.items():
        if name in sums:
            fp = np.where(wts[name] > 0, sums[name] / np.maximum(wts[name], 1e-12), np.nan)[lab_rec]
            fp[lab_rec == 0] = np.nan
            o["fp"] = np.where(np.isnan(fp), o["pt"], fp)
        else:
            o["fp"] = o["pt"].copy()
    return out


def point_values(path, recs, div=None):
    div = div or {}
    pts = recs["pt"]
    with rasterio.open(path) as r:
        names = list(r.descriptions)
        rows, cols = rasterio.transform.rowcol(r.transform, [p.x for p in pts], [p.y for p in pts])
        rows, cols = np.array(rows), np.array(cols)
        inside = (rows >= 0) & (rows < r.height) & (cols >= 0) & (cols < r.width)
        out = {}
        for i, nm in enumerate(names, 1):
            a = r.read(i)
            v = np.full(len(pts), np.nan, dtype="float64")
            v[inside] = a[rows[inside], cols[inside]]
            v[v == r.nodata] = np.nan
            out[nm] = v / div.get(nm.rsplit("_", 1)[0], 1)
        return out


def run(a):
    epsg = spec.AREAS[a.area]["epsg"]
    y = a.year
    if a.certificates:
        recs, uniq = load_certificates(a.area, y)
        tag = a.tag or "certs"
    else:
        recs, uniq = load_buildings(a, epsg)
        tag = a.tag
    cols = {"rec_id": recs["rec_id"].values, "year": y, "pt_source": recs["pt_source"].values}
    for c in ("UPRN", "fp_id", "link_method"):
        if c in recs:
            cols[c] = recs[c].values
    log = {"run": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "extract_version": 2, "method": spec.METHOD,
           "area": a.area, "year": y, "input": "certificates" if a.certificates else a.buildings,
           "n_records": len(recs), "n_footprints": len(uniq), "scales": SCALES, "sub_grid": SUB}
    lab = recs["fp_label"].to_numpy()

    # Sentinel-2
    p = spec.raw_path(a.area, "s2", y)
    g10 = Grid(p, uniq, recs["pt"])
    cols["fp_px_10m"] = np.where(lab > 0, g10.px[lab], 0)

    def s2_vars(b):
        out = {}
        for w in spec.WINDOWS["s2"]:
            refl = {k: b[f"{k}_{w}"] / 10000 for k in spec.S2_BANDS}
            out.update({f"s2_{k}_{w}": v for k, v in refl.items()})
            out.update({f"s2_{k}_{w}": v for k, v in s2_indices(refl).items()})
        return out
    for name, st in zonal_strips(p, g10, s2_vars, recs, SCALES[10]).items():
        for s, v in st.items():
            cols[f"{name}_{s}"] = v
    print("s2 done", flush=True)

    # Sentinel-1: means in linear power, converted to dB; SD of the dB values in the neighbourhoods
    p = spec.raw_path(a.area, "s1", y)

    def s1_vars(b):
        out = {}
        for w in spec.WINDOWS["s1"]:
            for pol in ("VV", "VH"):
                db = b[f"{pol}_{w}"] / 100
                out[f"s1_{pol}lin_{w}"] = 10 ** (db / 10)
                out[f"s1_{pol}dB_{w}"] = db
        return out
    sd_vars = {f"s1_{pol}dB_{w}" for w in spec.WINDOWS["s1"] for pol in ("VV", "VH")}
    s1 = zonal_strips(p, g10, s1_vars, recs, SCALES[10], sd_vars=sd_vars)
    for w in spec.WINDOWS["s1"]:
        for s in s1[f"s1_VVlin_{w}"]:
            if s.endswith("sd"):
                continue
            vv, vh = s1[f"s1_VVlin_{w}"][s], s1[f"s1_VHlin_{w}"][s]
            with np.errstate(divide="ignore", invalid="ignore"):
                cols[f"s1_VV_dB_{w}_{s}"] = 10 * np.log10(vv)
                cols[f"s1_VH_dB_{w}_{s}"] = 10 * np.log10(vh)
                cols[f"s1_VVminusVH_dB_{w}_{s}"] = 10 * np.log10(vv / vh)
                cols[f"s1_span_dB_{w}_{s}"] = 10 * np.log10(vv + vh)
        for pol in ("VV", "VH"):
            for s, v in s1[f"s1_{pol}dB_{w}"].items():
                if s.endswith("sd"):
                    cols[f"s1_{pol}_dB_{w}_{s}"] = v
    print("s1 done", flush=True)

    # Landsat LST and sUHI (30 m): point and neighbourhoods; the area-weighted footprint mean is kept as well
    p = spec.raw_path(a.area, "landsat", y)
    g30 = Grid(p, uniq, recs["pt"])
    cols["fp_px_30m"] = np.where(lab > 0, g30.px[lab], 0)
    ref = pd.read_csv(spec.derived_dir(a.area) / f"uhi_reference_{y}.csv").set_index("band")["rural_median_C"]

    def ls_vars(b):
        return {f"landsat_LST_{w}": b[f"LST_{w}"] / 100 for w in spec.windows("landsat", y)}
    for name, st in zonal_strips(p, g30, ls_vars, recs, SCALES[30]).items():
        w = name.split("_")[-1]
        for s, v in st.items():
            cols[f"{name}_{s}"] = v
            if not s.endswith("sd"):
                cols[f"landsat_sUHI_{w}_{s}"] = v - ref[f"LST_{w}"]
    print("landsat done", flush=True)

    # point-only products
    for name, v in point_values(spec.raw_path(a.area, "modis", y), recs, spec.PRODUCTS["modis"]["div"]).items():
        cols[f"modis_{name}_pt"] = v
        if name in ref.index:                       # temperature bands (not the counts) have a rural reference
            cols[f"modis_sUHI_{name}_pt"] = v - ref[name]
    for prod, path in (("era5", spec.raw_path(a.area, "era5", y)), ("era5", spec.derived_dir(a.area) / f"era5_derived_1000m_{y}.tif"),
                       ("viirs", spec.raw_path(a.area, "viirs", y)), ("ghsl", spec.raw_path(a.area, "ghsl_100m")),
                       ("lc", spec.derived_dir(a.area) / "landcover_100m.tif"), ("terrain", spec.derived_dir(a.area) / "terrain_30m.tif")):
        for name, v in point_values(path, recs).items():
            cols[f"{prod}_{name}_pt"] = v
    cols["worldcover_class_pt"] = point_values(spec.raw_path(a.area, "worldcover_10m"), recs)["worldcover_2021"]
    sea = np.isnan(cols["era5_t2m_annual_pt"])      # ERA5-Land has no values over the sea
    for c in [c for c in cols if c.startswith("era5_")]:
        cols[c] = np.where(sea, np.nan, cols[c])
    print("point products done", flush=True)

    out = pd.DataFrame(cols)
    d = spec.features_dir(a.area); d.mkdir(parents=True, exist_ok=True)
    base = d / f"{tag}_{y}"
    out.to_parquet(keep(base.with_suffix(".parquet")), index=False)
    if not a.no_csv:
        out.to_csv(keep(base.with_suffix(".csv")), index=False)
    meta = {"rec_id", "year", "pt_source", "UPRN", "fp_id", "link_method", "fp_px_10m", "fp_px_30m"}
    log.update({"n_features": int(sum(c not in meta for c in out.columns)),
                "fp_px_10m_median": float(np.median(out["fp_px_10m"])),
                "records_without_footprint": int((lab == 0).sum()),
                "missing_share": {c: round(float(out[c].isna().mean()), 4) for c in out.columns if out[c].isna().any()}})
    keep(base.with_name(base.name + "_log.json")).write_text(json.dumps(log, indent=1, default=str), encoding="utf-8")
    print(f"written {base}.parquet: {len(out)} records, {log['n_features']} features")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True, choices=list(spec.AREAS)); ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--certificates", action="store_true")
    ap.add_argument("--buildings"); ap.add_argument("--id")
    ap.add_argument("--lon"); ap.add_argument("--lat"); ap.add_argument("--points"); ap.add_argument("--tag")
    ap.add_argument("--no-csv", action="store_true")
    run(ap.parse_args())
