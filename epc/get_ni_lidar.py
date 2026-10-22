"""Download the OpenDataNI River Basin LiDAR surveys (DTM and DSM, Open Government Licence) that overlap Greater Belfast.

    python get_ni_lidar.py [--dry-run]

Surveys are chosen from the River Basin LiDAR extents (RiverBasin_LIDAR_Extents.zip) by overlap with the Greater
Belfast extent; each survey's zip is looked up by name in the OpenDataNI packages of its year. Files go to
data/belfast/lidar/opendatani_river_basin/<survey>/ with SHA256SUMS.txt and SOURCE.txt; an existing file is never
downloaded again or replaced. The Belfast City 2006 survey is in data/belfast/lidar/opendatani_belfast_city_2006/.
"""
import argparse, datetime, hashlib, json, pathlib, re, urllib.request
import geopandas as gpd
from shapely.geometry import box

PHD = pathlib.Path(__file__).resolve().parents[2]
LIDAR = PHD / "data/belfast/lidar"
EXTENTS = LIDAR / "opendatani_belfast_city_2006/RiverBasin_LIDAR_Extents.zip"
GREATER_BELFAST = box(315000, 357000, 351000, 390000)       # Irish Grid, as code/gee/spec.py
API = "https://admin.opendatani.gov.uk/api/3/action/package_show?id=osni-open-data-river-basin-lidar-{y}-dtms-and-dsms"
UA = {"User-Agent": "Mozilla/5.0"}


def norm(s):
    return re.sub(r"[^a-z]", "", s.lower())


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return json.load(r)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    e = gpd.read_file(f"zip://{EXTENTS.as_posix()}").to_crs(29902)
    e["km2"] = e.intersection(GREATER_BELFAST).area / 1e6
    want = e[(e.km2 > 0.1) & ~e.NAME.str.startswith("Belfast")]          # Belfast City 2006 is downloaded already
    resources = {}
    for y in sorted({d.year for d in want.SurveyDate}):
        for r in get_json(API.format(y=y))["result"]["resources"]:
            fname = r["url"].rsplit("/", 1)[-1].lower()
            # key = file name up to its date; gridded DTM/DSM only (point-cloud variants are skipped)
            if fname.endswith(".zip") and "point" not in fname:
                key = norm(re.split(r"_+\d", fname)[0])
                if key:
                    resources[key] = (y, fname[:-4], r["url"])
    out_root = LIDAR / "opendatani_river_basin"
    log = []
    for _, s in want.sort_values("km2", ascending=False).iterrows():
        key = norm(s.NAME)
        # exact name, else a file whose name begins the survey name (e.g. Lisburn/Dromore -> lisburn_15_03_2010.zip)
        hit = resources.get(key) or next((v for k, v in resources.items() if len(k) >= 5 and key.startswith(k)), None)
        if hit is None:
            print(f"NOT FOUND in the OpenDataNI packages: {s.NAME.strip()} ({s.SurveyDate})"); continue
        y, name, url = hit
        d = out_root / re.sub(r"[^A-Za-z0-9_]+", "_", name); f = d / url.rsplit("/", 1)[-1]
        log.append({"survey": s.NAME.strip(), "date": str(s.SurveyDate), "km2_in_greater_belfast": round(s.km2, 1), "url": url})
        if a.dry_run or (f.exists() and f.stat().st_size > 0):
            print(("would download" if a.dry_run else "already there"), f.name, f"({s.km2:.1f} km2)"); continue
        d.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(f.suffix + ".part")
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=600) as r, open(tmp, "wb") as o:
            while chunk := r.read(1 << 22):
                o.write(chunk)
        tmp.rename(f)
        h = hashlib.sha256(f.read_bytes()).hexdigest()
        (d / "SHA256SUMS.txt").write_text(f"{h}  {f.name}\n", encoding="utf-8")
        (d / "SOURCE.txt").write_text(f"OSNI Open Data: River Basin LIDAR {y} - DTMs and DSMs (OpenDataNI), Open Government "
                                      f"Licence.\n{url}\ndownloaded {datetime.date.today()}\n", encoding="utf-8")
        print(f"downloaded {f.name}: {f.stat().st_size / 1e6:.0f} MB", flush=True)
    if not a.dry_run:
        (out_root / "surveys.json").write_text(json.dumps(log, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
