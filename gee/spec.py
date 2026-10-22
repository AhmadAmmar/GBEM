"""Specification of the Earth Engine exports (gbem_composites.js), shared by ingest, preprocess and extract.

Grids, products, expected bands and scale factors are defined here once. check_js() confirms that the extents in the
Earth Engine script are the same as here.
"""
import pathlib, re

ROOT = pathlib.Path(__file__).resolve().parents[2]          # PhD folder
DATA = ROOT / "data"
JS = pathlib.Path(__file__).with_name("gbem_composites.js")
METHOD = "v2_0_1"                                            # method version in the file names

AREAS = {
    "london": {"epsg": 27700, "core": (501000, 153000, 564000, 204000), "context": (492000, 144000, 573000, 213000),
               "boundary": DATA / "london/SHP/london.shp"},
    "belfast": {"epsg": 29902, "core": (315000, 357000, 351000, 390000), "context": (309000, 351000, 357000, 399000),
                "boundary": DATA / "belfast/belfast-dissolved/belfast-dissolved.shp"},
}

NODATA_INT, NODATA_FLOAT = -32768, -9999.0
S2_BANDS = ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"]
EVENTS = {"heat2022": 2022, "cold2022": 2022}
WINDOWS = {"s2": ["annual", "summer"], "s1": ["annual"], "landsat": ["annual", "summer", "winter"],
           "modis": ["annual", "summer", "winter"], "era5": ["annual", "summer", "winter"], "viirs": ["annual"]}
EVENT_PRODUCTS = ["landsat", "modis", "era5"]

# per window: band stems in export order, and the divisor that turns stored values into physical units
PRODUCTS = {
    "s2": {"scale": 10, "extent": "core", "stems": S2_BANDS + ["n"], "div": {b: 10000 for b in S2_BANDS}},   # reflectance 0-1
    "s1": {"scale": 10, "extent": "core", "stems": ["VV", "VH", "angle", "n"], "div": {"VV": 100, "VH": 100, "angle": 100}},
    "landsat": {"scale": 30, "extent": "context", "stems": ["LST", "n"], "div": {"LST": 100}},
    "modis": {"scale": 1000, "extent": "context",
              "stems": ["terra_day", "terra_night", "terra_day_n", "terra_night_n", "aqua_day", "aqua_night", "aqua_day_n", "aqua_night_n"],
              "div": {"terra_day": 100, "terra_night": 100, "aqua_day": 100, "aqua_night": 100}},
    "era5": {"scale": 1000, "extent": "context",
             "stems": ["t2m", "d2m", "u10", "v10", "t2m_max_daily", "t2m_min_daily", "precip_mm", "ssrd_MJm2", "HDD", "CDD"], "div": {}},
    "viirs": {"scale": 500, "extent": "context", "stems": ["avg_rad", "n"], "div": {}},
}
MULTI = {   # multi-year thermal composites (batch b5): seasons as windows, all years 2020-2025 together
    "landsat_multi": {"scale": 30, "extent": "context", "stems": ["LST", "n"], "div": {"LST": 100}, "windows": ["annual", "summer", "winter"]},
    "modis_multi": {"scale": 1000, "extent": "context", "stems": PRODUCTS["modis"]["stems"], "div": PRODUCTS["modis"]["div"],
                    "windows": ["annual", "summer", "winter"]},
}
MULTI_YEARS = "2020-2025"
STATIC = {
    "worldcover_10m": {"scale": 10, "extent": "core", "bands": ["worldcover_2021"]},
    "dem_30m": {"scale": 30, "extent": "context", "bands": ["elevation_m"]},
    "ghsl_100m": {"scale": 100, "extent": "context", "bands": ["built_height_2018_m", "built_volume_2020_m3"]},
    # Environment Agency LiDAR composite, London (batch b6); exported in tiles because of its size
    "lidar_ea_2m": {"scale": 2, "extent": "core", "bands": ["height_dm", "height_max_dm", "slope_ddeg", "south_pct", "flat_pct"]},
}

# plausible physical ranges, for the ingest check (values outside are reported, not changed)
RANGES = {"B": (0, 1.6), "VV": (-40, 25), "VH": (-45, 20), "angle": (25, 50), "LST": (-30, 65), "terra_day": (-30, 65),
          "terra_night": (-35, 40), "aqua_day": (-30, 65), "aqua_night": (-35, 40), "t2m": (-15, 35), "d2m": (-20, 25),
          "elevation_m": (-10, 1000), "built_height_2018_m": (0, 300), "avg_rad": (0, 500)}


def windows(product, year):
    w = list(WINDOWS[product])
    if product in EVENT_PRODUCTS:
        w += [e for e, y in EVENTS.items() if y == year]
    return w


def expected_bands(product, year=None):
    if product in STATIC:
        return STATIC[product]["bands"]
    if product in MULTI:
        return [f"{s}_{w}" for w in MULTI[product]["windows"] for s in MULTI[product]["stems"]]
    if product == "modis":       # per window: terra (4 bands) then aqua (4 bands)
        return [f"{s}_{w}" for w in windows(product, year) for s in PRODUCTS[product]["stems"]]
    return [f"{s}_{w}" for w in windows(product, year) for s in PRODUCTS[product]["stems"]]


def parse_name(name):
    """gbem_v2_0_1_london_s2_10m_2024.tif -> dict(method, area, product, scale, year)."""
    # large exports are split by Earth Engine into tiles named <name>-<row offset>-<column offset>.tif
    tile = re.search(r"-(\d{10})-(\d{10})\.tif$", name)
    if tile:
        name = name[:tile.start()] + ".tif"
    m = re.match(r"gbem_(v\d+_\d+_\d+)_(london|belfast)_(.+?)(?:_(\d{4}(?:-\d{4})?))?\.tif$", name)
    if not m:
        return None
    method, area, rest, year = m.groups()
    if rest in STATIC:
        return {"method": method, "area": area, "product": rest, "scale": STATIC[rest]["scale"], "year": None,
                "tile": tile.group(0)[1:-4] if tile else None}
    prod, scale = rest.rsplit("_", 1)
    return {"method": method, "area": area, "product": prod, "scale": int(scale.rstrip("m")),
            "year": year if "-" in str(year) else int(year)}


def grid(area, product):
    spec = STATIC.get(product) or MULTI.get(product) or PRODUCTS[product]
    x0, y0, x1, y1 = AREAS[area][spec["extent"]]
    s = spec["scale"]
    return {"epsg": AREAS[area]["epsg"], "transform": (s, 0.0, x0, 0.0, -s, y1), "width": (x1 - x0) // s, "height": (y1 - y0) // s}


def raw_dir(area):
    return DATA / area / "gee_v2" / "raw"


def derived_dir(area):
    return DATA / area / "gee_v2" / "derived"


def features_dir(area):
    return DATA / area / "gee_v2" / "features"


def raw_path(area, product, year=None):
    s = (STATIC.get(product) or MULTI.get(product) or PRODUCTS[product])["scale"]
    if product in MULTI:
        year = MULTI_YEARS
    name = f"gbem_{METHOD}_{area}_{product}.tif" if product in STATIC else f"gbem_{METHOD}_{area}_{product}_{s}m_{year}.tif"
    return raw_dir(area) / name


def check_js():
    """The extents in gbem_composites.js must equal AREAS."""
    js = JS.read_text(encoding="utf-8")
    for area, a in AREAS.items():
        for key in ("core", "context"):
            m = re.search(area + r":\s*\{[^}]*?" + key + r":\s*\[([\d,\s]+)\]", js, re.S)
            got = tuple(int(v) for v in m.group(1).split(","))
            assert got == a[key], f"{area} {key}: script {got} != spec {a[key]}"
    assert f"version: '{METHOD}'" in js, "method version differs from the Earth Engine script"
    return True
