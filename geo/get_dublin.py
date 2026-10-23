"""Open data for Dublin, the third test area (Republic of Ireland, outside the UK EPC system):
  boundaries   CSO Small Areas 2022, ungeneralised (Tailte Éireann / CSO, CC BY 4.0)
  census       CSO Census 2022 Small Area Population Statistics, complete set, with the glossary (CC BY 4.0)
  postcodes    Dublin postal district boundaries (autoaddress.ie, Zenodo 10.5281/zenodo.4589220, CC BY 4.0), in the
               same spelling as the BER Research Tool county field ("Dublin 6", "Co. Dublin")
  buildings    Overture Maps buildings within the Dublin region extent (release 2026-09-23.1, as London and
               Belfast; ODbL / CDLA); geometry as WKB in EPSG:4326
The BER Research Tool file itself needs a registered SEAI login: put BERPublicsearch.zip (unchanged) in
data/dublin/ber/raw/. The public BER file has no address, Eircode or Small Area code, so Dublin is an area-level
test (postal districts), not a dwelling-level one.

    python get_dublin.py

Raw files are kept unchanged in data/dublin/<layer>/raw/ with SOURCE.txt and SHA256SUMS.txt; an existing download is
never replaced. Outputs:
  data/dublin/boundaries/small_areas_2022.gpkg     Small Areas within the Dublin region (EPSG:2157)
  data/dublin/boundaries/postal_districts.gpkg     postal districts (EPSG:2157)
"""
import datetime, hashlib, pathlib, sys, urllib.error, urllib.request
import geopandas as gpd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

PHD = pathlib.Path(__file__).resolve().parents[2]
D = PHD / "data" / "dublin"
EPSG = 2157                                  # Irish Transverse Mercator
BBOX = (-6.55, 53.18, -6.00, 53.64)          # Dublin region: Dublin City, Dún Laoghaire-Rathdown, Fingal, South Dublin
COUNCILS = ("DUBLIN CITY", "DÚN LAOGHAIRE", "DUN LAOGHAIRE", "FINGAL", "SOUTH DUBLIN")
SA = "https://data-osi.opendata.arcgis.com/api/download/v1/items/70a33cbb8bd7406da0d571be28624721/geoPackage?layers=0"
SRC = {
    "boundaries": {"cso_small_areas_2022_ungeneralised.gpkg": SA},
    "census": {"Complete_set_of_Census_2022_SAPs.zip":
               "https://www.cso.ie/en/media/csoie/census/census2022/Complete_set_of_Census_2022_SAPs.zip",
               "Glossary_Saps_2022_REVISED_21102024.xlsx":
               "https://www.cso.ie/en/media/csoie/census/census2022/Glossary_Saps_2022_REVISED_21102024.xlsx"},
    "postcodes": {"dublin_postcode_boundaries_autoaddress.geojson":
                  "https://zenodo.org/api/records/4589220/files/dublin_postcode_boundaries_autoaddress.geojson/content"},
}
CREDIT = {"boundaries": "Central Statistics Office and Tailte Éireann, Small Areas National Statistical Boundaries 2022. CC BY 4.0.",
          "census": "Central Statistics Office, Census 2022 Small Area Population Statistics. CC BY 4.0.",
          "postcodes": "autoaddress.ie and R. Molony, Dublin Postcode Boundaries, Zenodo, doi:10.5281/zenodo.4589220. CC BY 4.0.",
          "buildings": "Overture Maps Foundation, buildings theme (OpenStreetMap contributors, ODbL; Microsoft and "
                       "Google machine-learned footprints, CDLA Permissive 2.0 / CC BY 4.0)."}


def record(raw, name, url, layer):
    p = raw / name
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    with open(raw / "SHA256SUMS.txt", "a", encoding="utf-8") as f:
        f.write(f"{h}  {name}\n")
    with open(raw / "SOURCE.txt", "a", encoding="utf-8") as f:
        f.write(f"{name}\n  url: {url}\n  downloaded: {datetime.date.today()}\n  credit: {CREDIT[layer]}\n")


def download():
    for layer, files in SRC.items():
        raw = D / layer / "raw"; raw.mkdir(parents=True, exist_ok=True)
        for name, url in files.items():
            if (raw / name).exists():
                print(f"kept   {layer}/{name}"); continue
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research download)"})
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    body = r.read()
            except urllib.error.URLError as e:          # a later run tries again
                print(f"FAILED {layer}/{name}: {e}"); continue
            (raw / name).write_bytes(body)
            record(raw, name, url, layer)
            print(f"got    {layer}/{name}  {(raw / name).stat().st_size / 1e6:.1f} MB")


def buildings(release="2026-09-23.1"):
    """Overture buildings in the extent, same release as London and Belfast (the overturemaps CLI points at a removed
    release, so the release is read directly with DuckDB)"""
    import duckdb
    raw = D / "buildings" / "raw"; raw.mkdir(parents=True, exist_ok=True)
    name = "overture_buildings_dublin.parquet"
    if (raw / name).exists():
        print(f"kept   buildings/{name}"); return
    src = f"s3://overturemaps-us-west-2/release/{release}/theme=buildings/type=building/*"
    x0, y0, x1, y1 = BBOX
    c = duckdb.connect(); c.sql("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET s3_region='us-west-2';")
    c.sql(f"""COPY (SELECT id, sources[1].dataset AS dataset, height, num_floors, subtype, class, ST_AsWKB(geometry) AS geometry
              FROM read_parquet('{src}', hive_partitioning=1)
              WHERE bbox.xmin < {x1} AND bbox.xmax > {x0} AND bbox.ymin < {y1} AND bbox.ymax > {y0})
              TO '{(raw / name).as_posix()}' (FORMAT parquet)""")
    record(raw, name, src + f" bbox {BBOX}", "buildings")
    print(f"got    buildings/{name}  {(raw / name).stat().st_size / 1e6:.1f} MB")


def boundaries():
    sa = gpd.read_file(D / "boundaries/raw/cso_small_areas_2022_ungeneralised.gpkg").to_crs(EPSG)
    la = next(c for c in sa.columns if c.upper() in ("COUNTY_ENGLISH", "COUNTY", "LA_ENGLISH", "COUNTYNAME"))
    keep_ = sa[la].astype(str).str.upper().str.contains("|".join(COUNCILS))
    out = sa[keep_]
    out.to_file(keep(D / "boundaries/small_areas_2022.gpkg"), driver="GPKG")
    print(f"Small Areas in the Dublin region: {len(out):,} {out[la].value_counts().to_dict()}")
    pcf = D / "postcodes/raw/dublin_postcode_boundaries_autoaddress.geojson"
    if pcf.exists():
        pc = gpd.read_file(pcf).to_crs(EPSG)
        pc.to_file(keep(D / "boundaries/postal_districts.gpkg"), driver="GPKG")
        print(f"postal districts: {len(pc)}")


if __name__ == "__main__":
    download()
    buildings()
    boundaries()
