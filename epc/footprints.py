"""Step 2 - one building-footprint layer per study area.

    python footprints.py [--areas london belfast]

London   Overture Maps buildings, release 2026-09-23.1 (OpenStreetMap plus Microsoft machine-learned footprints where
         OpenStreetMap has none), inside the core extent of the Earth Engine exports (Greater London Authority area +
         1 km). OpenStreetMap alone misses many buildings in outer London (up to 70% of the certificates' UPRNs
         unmatched in Harrow), which would bias the sample towards inner London.
Belfast  OSNI building footprints inside Belfast City Council area (with the OSNI dwelling type, TYPECODE), and
         Overture Maps buildings (same release) for the rest of the Greater Belfast extent. An Overture building is
         used only if its representative point lies outside the council area, so the two sources do not overlap.
Overture attributes kept: dataset of origin, height (m) and number of floors where given.
Geometries are made valid and projected to the area grid (EPSG:27700 / EPSG:29902). Every footprint gets an id
(fp_id), its source and the source id.
Output: data/<area>/epc/footprints.parquet (GeoParquet) and footprints_log.json
"""
import argparse, datetime, json, pathlib
import geopandas as gpd
import pandas as pd
import shapely
from shapely.geometry import box
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

PHD = pathlib.Path(__file__).resolve().parents[2]
DATA = PHD / "data"
OSM = {"london": DATA / "osm/geofabrik_greater-london_2026-10-20/greater-london-261020-free.shp.zip",          # roads
       "belfast": DATA / "osm/geofabrik_ireland_2026-10-20/ireland-and-northern-ireland-261020-free.shp.zip"}
OVERTURE = {a: DATA / f"overture/2026-09-23.1/{a}_buildings.parquet" for a in ("london", "belfast")}
EXTENT = {"london": (27700, (501000, 153000, 564000, 204000)), "belfast": (29902, (315000, 357000, 351000, 390000))}
OSNI = DATA / "belfast/belfast-buildings/Belfast_Building_Footprints.shp"
COUNCIL = DATA / "belfast/belfast-dissolved/belfast-dissolved.shp"


def overture_buildings(area):
    epsg, ext = EXTENT[area]
    o = pd.read_parquet(OVERTURE[area])
    g = gpd.GeoDataFrame(o.drop(columns="geometry_wkb"), geometry=gpd.GeoSeries.from_wkb(o["geometry_wkb"]), crs=4326).to_crs(epsg)
    g = g[g.intersects(box(*ext))]
    return pd.DataFrame({"source": "overture", "src_id": g["id"].values,
                         "src_dataset": [d[0] if d is not None and len(d) else None for d in g["datasets"]],
                         "height_m": g["height"].values, "num_floors": g["num_floors"].values,
                         "bldg_class": g["class"].values, "geometry": g.geometry.values})


def clean(df, epsg):
    g = gpd.GeoDataFrame(df, geometry="geometry", crs=epsg)
    g["geometry"] = shapely.make_valid(shapely.force_2d(g.geometry.values))
    g = g[g.geometry.type.isin(["Polygon", "MultiPolygon", "GeometryCollection"])]
    g["geometry"] = [geom if geom.geom_type != "GeometryCollection" else
                     shapely.unary_union([p for p in geom.geoms if p.geom_type in ("Polygon", "MultiPolygon")]) for geom in g.geometry]
    g = g[~g.geometry.is_empty & (g.geometry.area > 0)]
    return g.reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--areas", nargs="+", default=["london", "belfast"])
    for area in ap.parse_args().areas:
        epsg, _ = EXTENT[area]
        log = {"run": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
        osm = overture_buildings(area)
        log["overture_in_extent"] = len(osm)
        if area == "belfast":
            council = gpd.read_file(COUNCIL).to_crs(epsg).union_all()
            o = gpd.GeoDataFrame(osm, geometry="geometry", crs=epsg)
            outside = ~o.geometry.representative_point().within(council)
            osm = osm[outside.values]
            n = gpd.read_file(OSNI).to_crs(epsg)
            osni = pd.DataFrame({"source": "osni", "src_id": n["FUSIONID"], "osni_typecode": n["TYPECODE"], "geometry": n.geometry.values})
            log.update({"overture_outside_council_area": len(osm), "osni": len(osni)})
            df = pd.concat([osni, osm], ignore_index=True)
        else:
            df = osm
        g = clean(df, epsg)
        g.insert(0, "fp_id", [f"{area[0].upper()}{i:07d}" for i in range(len(g))])
        log.update({"footprints": len(g), "by_source": g["source"].value_counts().to_dict(),
                    "by_dataset": g.get("src_dataset", pd.Series(dtype=str)).value_counts().to_dict(),
                    "with_height": int(g.get("height_m", pd.Series(dtype=float)).notna().sum()),
                    "overture_release": "2026-09-23.1"})
        out = DATA / area / "epc"; out.mkdir(parents=True, exist_ok=True)
        g.to_parquet(keep(out / "footprints.parquet"), index=False)
        keep((out / "footprints_log.json")).write_text(json.dumps(log, indent=1), encoding="utf-8")
        print(area, json.dumps(log))


if __name__ == "__main__":
    main()
