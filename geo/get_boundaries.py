"""Download London LSOA 2021 boundaries (ONS Open Geography Portal, Open Government Licence v3.0).

    python get_boundaries.py

Source: Lower layer Super Output Areas (December 2021) Boundaries EW BGC (V5), generalised (20 m), clipped to the
coastline, British National Grid; the feature service is queried by the London context extent in pages of 2000.
Output: data/london/boundaries_ons/lsoa21_bgc_v5_london.gpkg (LSOAs whose centroid is inside Greater London), with
SOURCE.txt and SHA256SUMS.txt. An existing download is never replaced: delete or rename it to download again.
"""
import datetime, hashlib, json, pathlib, sys, urllib.parse, urllib.request
import geopandas as gpd
import pandas as pd

PHD = pathlib.Path(__file__).resolve().parents[2]
OUT = PHD / "data/london/boundaries_ons"
SERVICE = ("https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
           "Lower_layer_Super_Output_Areas_December_2021_Boundaries_EW_BGC_V5/FeatureServer/0/query")
EXTENT = (492000, 144000, 573000, 213000)                  # London context extent (gee/spec.py), EPSG:27700


def page(offset):
    q = {"where": "1=1", "outFields": "LSOA21CD,LSOA21NM", "geometry": ",".join(map(str, EXTENT)),
         "geometryType": "esriGeometryEnvelope", "inSR": 27700, "spatialRel": "esriSpatialRelIntersects",
         "outSR": 27700, "f": "geojson", "resultOffset": offset, "resultRecordCount": 2000, "orderByFields": "LSOA21CD"}
    with urllib.request.urlopen(SERVICE + "?" + urllib.parse.urlencode(q), timeout=120) as r:
        return json.loads(r.read())


def main():
    dest = OUT / "lsoa21_bgc_v5_london.gpkg"
    if dest.exists():
        sys.exit(f"{dest} exists: not downloaded again")
    OUT.mkdir(parents=True, exist_ok=True)
    feats, off = [], 0
    while True:
        js = page(off)
        feats += js["features"]
        print(f"{len(feats)} features", flush=True)
        if len(js["features"]) < 2000:
            break
        off += 2000
    g = gpd.GeoDataFrame.from_features(feats, crs=27700)
    london = gpd.read_file(PHD / "data/london/SHP/london.shp").to_crs(27700).union_all()
    g = g[g.representative_point().within(london)].reset_index(drop=True)
    g.to_file(dest, driver="GPKG")
    (OUT / "SOURCE.txt").write_text(
        f"Lower layer Super Output Areas (December 2021) Boundaries EW BGC (V5)\nOffice for National Statistics, "
        f"Open Geography Portal. Contains OS data © Crown copyright and database right {datetime.date.today().year}. "
        f"Source: Office for National Statistics licensed under the Open Government Licence v3.0.\n"
        f"Service: {SERVICE}\nDownloaded {datetime.datetime.now():%Y-%m-%d %H:%M}; {len(g)} LSOAs with centroid in Greater London.\n",
        encoding="utf-8")
    (OUT / "SHA256SUMS.txt").write_text(f"{hashlib.sha256(dest.read_bytes()).hexdigest()}  {dest.name}\n", encoding="utf-8")
    print(f"{len(g)} London LSOAs -> {dest}")


if __name__ == "__main__":
    main()
