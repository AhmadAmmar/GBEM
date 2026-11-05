"""The satellite composites of gbem_composites.js, built without Earth Engine, from open STAC archives.

    python composites_stac.py --area belfast --year 2024 --products s2 s1 landsat modis [--extent core] [--box x0 y0 x1 y1]
    python composites_stac.py --area belfast --year 2024 --products s2 --box 330000 370000 334000 374000 --compare

Same areas, windows, bands, scaling and no-data values as gbem_composites.js (method v2_0_1), so either source can feed
gee/ingest.py. Files go to data/<area>/gee_v2/raw_stac/ with the same names, and are never mixed with raw/ silently.

Differences from the Earth Engine source, which compare() measures on a small box before use:
  s2       Planetary Computer sentinel-2-l2a. Clouds masked with the scene classification (SCL 4-7), not Cloud Score+,
           which is not published elsewhere. From processing baseline 04.00 the 1000 offset is removed, as Earth
           Engine's harmonised collection does.
  s1       Planetary Computer sentinel-1-rtc: radiometrically terrain-corrected gamma nought, converted to dB here.
           Earth Engine holds sigma nought without terrain flattening, so values differ on slopes.
  landsat  landsat-c2-l2, the same USGS product: lwir11 is ST_B10. Same QA bits. Tier 1 only (the archive also holds Tier 2).
  modis    modis-11A1-061, the same NASA product, collection 6.1. Terra and Aqua kept apart by item id; quality as in
           Earth Engine (LST produced, error at most 2 K).
  era5     Copernicus Climate Data Store (needs a free key in ~/.cdsapirc); not done here yet.
  viirs    Colorado School of Mines (needs a free login); not done here yet.
"""
import argparse
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path.home() / "dev/research-helpers/src"))
from research_helpers import eodata

PHD = pathlib.Path(__file__).resolve().parents[2]
VERSION = "v2_0_1"
AREAS = {"london": ("EPSG:27700", [501000, 153000, 564000, 204000], [492000, 144000, 573000, 213000]),
         "belfast": ("EPSG:29902", [315000, 357000, 351000, 390000], [309000, 351000, 357000, 399000]),
         "dublin": ("EPSG:2157", [693000, 714000, 735000, 768000], [684000, 705000, 744000, 777000])}
WINDOWS = {"s2": ["annual", "summer"], "s1": ["annual"], "landsat": ["annual", "summer", "winter"], "modis": ["annual", "summer", "winter"]}
EVENTS = {"heat2022": ("2022-07-10", "2022-07-26"), "cold2022": ("2022-12-05", "2022-12-20")}
RES = {"s2": 10, "s1": 10, "landsat": 30, "modis": 1000}
S2 = ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"]
NODATA = -32768


def window(win, year):
    if win == "annual":
        return f"{year}-01-01", f"{year}-12-31"
    if win == "summer":
        return f"{year}-06-01", f"{year}-08-31"
    if win == "winter":
        return f"{year - 1}-12-01", f"{year}-02-28"
    return EVENTS[win]


def windows(product, year):
    w = list(WINDOWS[product])
    if product in ("landsat", "modis"):
        w += [k for k, (s, _) in EVENTS.items() if s.startswith(str(year))]
    return w


def geobox(crs, box, res):
    from odc.geo.geobox import GeoBox
    return GeoBox.from_bbox(box, crs=crs, resolution=res)


def lonlat(crs, box):
    from pyproj import Transformer
    t = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    xs, ys = t.transform([box[0], box[2], box[0], box[2]], [box[1], box[1], box[3], box[3]])
    return min(xs), min(ys), max(xs), max(ys)


def load(gee_id, crs, box, dates, bands, res, route=0, keep=None, **query):
    import odc.stac
    r = [x for x in eodata.routes(gee_id) if x.kind == "stac"][route]
    items = eodata.search(gee_id, lonlat(crs, box), f"{dates[0]}/{dates[1]}", route, **query)
    if keep:                                    # e.g. one satellite of a collection that holds two
        items = [i for i in items if keep(i)]
    if not items:
        return None, items
    names = [r.bands.get(b, b) for b in bands]
    cube = odc.stac.load(items, bands=names, geobox=geobox(crs, box, res), chunks={"x": 1024, "y": 1024}, groupby="solar_day")
    return cube.rename({n: b for n, b in zip(names, bands)}), items


def s2(crs, box, year):
    out = {}
    for win in windows("s2", year):
        cube, items = load("COPERNICUS/S2_SR_HARMONIZED", crs, box, window(win, year), S2 + ["SCL"], 10, query={"eo:cloud_cover": {"lt": 80}})
        if cube is None:
            continue
        baseline = np.array([float(i.properties.get("s2:processing_baseline", "0") or 0) for i in items])
        clear = cube.SCL.isin([4, 5, 6, 7])
        offset = 1000.0 if (baseline >= 4).all() else 0.0    # all items share one offset after 25 January 2022
        for b in S2:
            v = cube[b].where(clear & (cube[b] > 0)).astype("float32") - offset
            out[f"{b}_{win}"] = v.median("time")
        out[f"n_{win}"] = clear.sum("time")
    return out


def s1(crs, box, year):
    out = {}
    for win in windows("s1", year):
        cube, _ = load("COPERNICUS/S1_GRD", crs, box, window(win, year), ["VV", "VH"], 10, query={"sat:orbit_state": {"in": ["ascending", "descending"]}})
        if cube is None:
            continue
        for b in ("VV", "VH"):
            db = 10 * np.log10(cube[b].where(cube[b] > 0))
            out[f"{b}_{win}"] = db.median("time") * 100
        out[f"n_{win}"] = cube.VV.notnull().sum("time")
    return out


def landsat(crs, box, year):
    out = {}
    for win in windows("landsat", year):
        cube, _ = load("LANDSAT/LC08/C02/T1_L2", crs, box, window(win, year), ["ST_B10", "QA_PIXEL"], 30,
                         # Tier 1 only, as in Earth Engine's T1_L2 collections; the open archive also holds Tier 2
                         query={"platform": {"in": ["landsat-8", "landsat-9"]}, "landsat:collection_category": {"eq": "T1"}})
        if cube is None:
            continue
        qa = cube.QA_PIXEL.astype("int64")
        clear = ((qa & (1 << 1)) == 0) & ((qa & (1 << 3)) == 0) & ((qa & (1 << 4)) == 0) & ((qa & (1 << 5)) == 0) & (cube.ST_B10 > 0)
        lst = (cube.ST_B10 * 0.00341802 + 149.0 - 273.15).where(clear)
        out[f"LST_{win}"] = lst.median("time") * 100
        out[f"n_{win}"] = clear.sum("time")
    return out


def modis(crs, box, year):
    """Terra (MOD11A1) and Aqua (MYD11A1) kept apart, as in Earth Engine: the open collection holds both, told apart
    only by the item id. Quality as in gbem_composites.js: LST produced (QC bits 0-1 at most 1) and error at most
    2 K (bits 6-7 at most 1)."""
    out = {}
    for sat, prefix in (("terra", "MOD11A1"), ("aqua", "MYD11A1")):
        for win in windows("modis", year):
            cube, _ = load("MODIS/006/MOD11A1", crs, box, window(win, year), ["LST_Day_1km", "QC_Day", "LST_Night_1km", "QC_Night"], 1000,
                           keep=lambda it, p=prefix: it.id.startswith(p))
            if cube is None:
                continue
            for part, qc in (("Day", "QC_Day"), ("Night", "QC_Night")):
                flags = cube[qc].astype("int64")
                good = ((flags & 3) <= 1) & (((flags >> 6) & 3) <= 1) & (cube[f"LST_{part}_1km"] > 0)
                v = (cube[f"LST_{part}_1km"] * 0.02 - 273.15).where(good)
                out[f"{sat}_{part.lower()}_{win}"] = v.median("time") * 100
                out[f"{sat}_{part.lower()}_n_{win}"] = good.sum("time")
    return out


PRODUCTS = {"s2": s2, "s1": s1, "landsat": landsat, "modis": modis}


def write(bands, path):
    import rioxarray  # noqa: F401, adds .rio to xarray
    import xarray as xr
    stack = xr.concat([v.astype("float32") for v in bands.values()], dim="band").assign_coords(band=list(bands))
    stack = stack.compute()
    data = np.where(np.isfinite(stack.values), np.round(stack.values), NODATA).astype("int16")
    out = stack.copy(data=data).rio.write_nodata(NODATA)
    out.attrs["long_name"] = tuple(bands)          # becomes the band descriptions, as in the Earth Engine files
    path.parent.mkdir(parents=True, exist_ok=True)
    out.rio.to_raster(path, driver="COG")
    return out


def compare(area, product, year, path):
    """Against the Earth Engine file of the same name, for the bands both have."""
    import rasterio
    from rasterio.warp import Resampling, reproject
    ee_file = PHD / "data" / area / "gee_v2/raw" / path.name.replace("_box", "")
    if not ee_file.exists():
        print("no Earth Engine file to compare:", ee_file.name)
        return
    with rasterio.open(path) as a, rasterio.open(ee_file) as b:
        names_b = list(b.descriptions)
        for i, name in enumerate(a.descriptions, 1):
            if name not in names_b:
                continue
            x = a.read(i).astype(float)
            y = np.full(x.shape, np.nan)
            reproject(rasterio.band(b, names_b.index(name) + 1), y, dst_transform=a.transform, dst_crs=a.crs, resampling=Resampling.nearest, dst_nodata=np.nan)
            x[x == NODATA] = np.nan
            y[(y == NODATA) | (y == -9999)] = np.nan
            print(product, name, eodata.compare(y, x))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True, choices=AREAS); ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--products", nargs="+", default=list(PRODUCTS)); ap.add_argument("--extent", default="core", choices=["core", "context"])
    ap.add_argument("--box", nargs=4, type=float, help="a smaller box, in the area's projected coordinates"); ap.add_argument("--compare", action="store_true")
    a = ap.parse_args()
    crs, core, context = AREAS[a.area]
    box = a.box or (core if a.extent == "core" else context)
    for p in a.products:
        bands = PRODUCTS[p](crs, box, a.year)
        if not bands:
            print(p, "no scenes")
            continue
        name = f"gbem_{VERSION}_{a.area}_{p}_{RES[p]}m_{a.year}{'_box' if a.box else ''}.tif"
        path = PHD / "data" / a.area / "gee_v2/raw_stac" / name
        write(bands, path)
        print("wrote", path)
        if a.compare:
            compare(a.area, p, a.year, path)


if __name__ == "__main__":
    main()
