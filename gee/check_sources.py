"""Check the data sources of gbem_composites.js before an export batch (Earth Engine Python API).

    python check_sources.py --project ee-ahmadammargeo [--year 2024]

For each dataset: does it exist, does it have the bands the script uses, and how many scenes cover each study area in
each time window of the year. Missing datasets or bands, or windows without scenes, are reported before any export
is started.
"""
import argparse
import ee

AREAS = {"london": ("EPSG:27700", [492000, 144000, 573000, 213000]),
         "belfast": ("EPSG:29902", [309000, 351000, 357000, 399000])}
SOURCES = [   # id, kind, bands used by the script
    ("COPERNICUS/S2_SR_HARMONIZED", "col", ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"]),
    ("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED", "col", ["cs_cdf"]),
    ("COPERNICUS/S1_GRD", "col", ["VV", "VH", "angle"]),
    ("LANDSAT/LC08/C02/T1_L2", "col", ["ST_B10", "QA_PIXEL"]),
    ("LANDSAT/LC09/C02/T1_L2", "col", ["ST_B10", "QA_PIXEL"]),
    ("MODIS/061/MOD11A1", "col", ["LST_Day_1km", "LST_Night_1km", "QC_Day", "QC_Night"]),
    ("MODIS/061/MYD11A1", "col", ["LST_Day_1km", "LST_Night_1km", "QC_Day", "QC_Night"]),
    ("ECMWF/ERA5_LAND/DAILY_AGGR", "col", ["temperature_2m", "dewpoint_temperature_2m", "u_component_of_wind_10m",
                                           "v_component_of_wind_10m", "total_precipitation_sum", "surface_solar_radiation_downwards_sum"]),
    ("NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG", "col", ["avg_rad", "cf_cvg"]),
    ("ESA/WorldCover/v200", "col", ["Map"]),
    ("COPERNICUS/DEM/GLO30_2024_1", "col", ["DEM"]),
    ("JRC/GHSL/P2023A/GHS_BUILT_H/2018", "img", ["built_height"]),
    ("JRC/GHSL/P2023A/GHS_BUILT_V/2020", "img", ["built_volume_total"]),
]
TIMED = {"COPERNICUS/S2_SR_HARMONIZED", "COPERNICUS/S1_GRD", "LANDSAT/LC08/C02/T1_L2", "LANDSAT/LC09/C02/T1_L2",
         "MODIS/061/MOD11A1", "MODIS/061/MYD11A1", "ECMWF/ERA5_LAND/DAILY_AGGR", "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG"}


def windows(y):
    w = {"annual": (f"{y}-01-01", f"{y + 1}-01-01"), "summer": (f"{y}-06-01", f"{y}-09-01"), "winter": (f"{y - 1}-12-01", f"{y}-03-01")}
    if y == 2022:
        w.update({"heat2022": ("2022-07-10", "2022-07-26"), "cold2022": ("2022-12-05", "2022-12-20")})
    return w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True); ap.add_argument("--year", type=int, default=2024)
    a = ap.parse_args()
    ee.Initialize(project=a.project)
    problems = []
    for sid, kind, bands in SOURCES:
        try:
            col = ee.ImageCollection(sid) if kind == "col" else None
            if sid == "COPERNICUS/S1_GRD":     # the script uses dual-polarisation IW scenes only
                col = (col.filter(ee.Filter.eq("instrumentMode", "IW"))
                       .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
                       .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
                       .filterBounds(ee.Geometry.Rectangle(AREAS["london"][1], AREAS["london"][0], False)))
            img = ee.Image(sid) if kind == "img" else col.first()
            have = img.bandNames().getInfo()
        except ee.EEException as e:
            problems.append(f"{sid}: {e}"); print(f"MISSING  {sid}: {e}"); continue
        miss = [b for b in bands if b not in have]
        print(("OK       " if not miss else "BANDS    ") + sid + (f"  missing bands: {miss}" if miss else ""))
        if miss:
            problems.append(f"{sid}: missing {miss}")
        if sid in TIMED:
            for area, (crs, r) in AREAS.items():
                reg = ee.Geometry.Rectangle(r, crs, False)
                # event windows are used for the thermal and climate products only, as in the script
                wins = {w: d for w, d in windows(a.year).items() if w in ("annual", "summer", "winter") or sid.startswith(("LANDSAT", "MODIS", "ECMWF"))}
                counts = {w: ee.ImageCollection(sid).filterBounds(reg).filterDate(*d).size() for w, d in wins.items()}
                got = ee.Dictionary(counts).getInfo()
                print(f"           {area:8s} scenes {a.year}: " + ", ".join(f"{w} {n}" for w, n in got.items()))
                problems += [f"{sid} {area} {w}: no scenes" for w, n in got.items() if n == 0]
    print("\nNo problems found." if not problems else "\nProblems:\n  " + "\n  ".join(problems))


if __name__ == "__main__":
    main()
