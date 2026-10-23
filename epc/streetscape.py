"""Streetscape: street canyon measures for every building footprint.

    python streetscape.py --area belfast|london

Roads: OpenStreetMap (Geofabrik, gis_osm_roads_free_1) of the classes cars and people use in residential areas.
Each footprint is assigned to its nearest road segment (within 100 m). Per road segment, from the buildings assigned
to it (its frontage):
  st_width_m       street width between building fronts: twice the median setback (footprint edge to road centre line)
                   of the fronting buildings (both sides together)
  st_height_m      median building height along the street (LiDAR median height; footprint data where missing)
  st_hw            height / width ratio (canyon aspect ratio; > 1 deep canyons, < 0.3 open streets)
  st_frontage      fronting buildings per 100 m of street
  st_orient_deg    street orientation, 0-180 (0 = north-south)
  st_class         OSM road class
Per footprint: st_setback_m (distance to the road centre line), and the measures of its street.
Output: data/<area>/epc/streetscape_fp.parquet (fp_id, st_*); assemble.py adds them to the group "streets".
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

PHD = pathlib.Path(__file__).resolve().parents[2]
DATA = PHD / "data"
EPSG = {"london": 27700, "belfast": 29902}
OSM = {"london": DATA / "osm/geofabrik_greater-london_2026-10-20/greater-london-261020-free.shp.zip",
       "belfast": DATA / "osm/geofabrik_ireland_2026-10-20/ireland-and-northern-ireland-261020-free.shp.zip"}
CLASSES = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
           "service", "pedestrian", "road", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True)
    a = ap.parse_args()
    e = DATA / a.area / "epc"
    fp = gpd.read_parquet(e / "footprints.parquet", columns=["fp_id", "geometry"])
    x0, y0, x1, y1 = fp.total_bounds
    bb = gpd.GeoSeries([shapely.box(x0 - 200, y0 - 200, x1 + 200, y1 + 200)], crs=EPSG[a.area]).to_crs(4326).total_bounds
    r = gpd.read_file(f"zip://{OSM[a.area].as_posix()}!gis_osm_roads_free_1.shp", bbox=tuple(bb), columns=["osm_id", "fclass"])
    r = r[r["fclass"].isin(CLASSES)].to_crs(EPSG[a.area]).reset_index(drop=True)
    r = r[r.geometry.length > 0].reset_index(drop=True)
    print(f"{a.area}: {len(fp):,} footprints, {len(r):,} road segments", flush=True)
    # footprint -> nearest road segment; distance from the footprint edge (setback) and from its centroid
    tree = shapely.STRtree(r.geometry.values)
    (ifp, ird), dist = tree.query_nearest(fp.geometry.values, max_distance=100, return_distance=True, all_matches=False)
    d = pd.DataFrame({"fp_id": fp["fp_id"].to_numpy()[ifp], "seg": ird, "st_setback_m": dist})
    cen = shapely.centroid(fp.geometry.values[ifp])
    d["dist_c"] = shapely.distance(cen, r.geometry.values[ird])
    lid = pd.read_parquet(e / "lidar_fp.parquet", columns=["fp_id", "lidar_height_med_m", "lidar_valid_share"]) if (e / "lidar_fp.parquet").exists() else None
    morph = pd.read_parquet(e / "morphology.parquet", columns=["fp_id", "height_m"])
    d = d.merge(morph, on="fp_id", how="left")
    if lid is not None:
        d = d.merge(lid, on="fp_id", how="left")
        d["h"] = d["lidar_height_med_m"].where(d["lidar_valid_share"] >= 0.5).fillna(d["height_m"])
    else:
        d["h"] = d["height_m"]
    seg = d.groupby("seg").agg(n=("fp_id", "size"), half=("st_setback_m", "median"), st_height_m=("h", "median"))
    geom = r.geometry.values[seg.index.to_numpy()]
    length = shapely.length(geom)
    seg["st_width_m"] = (2 * seg["half"]).clip(4, 120)
    seg["st_hw"] = seg["st_height_m"] / seg["st_width_m"]
    seg["st_frontage"] = seg["n"] / np.maximum(length, 10) * 100
    start, end = shapely.get_point(geom, 0), shapely.get_point(geom, -1)
    ang = np.degrees(np.arctan2(shapely.get_x(end) - shapely.get_x(start), shapely.get_y(end) - shapely.get_y(start))) % 180
    seg["st_orient_deg"] = ang
    seg["st_class"] = r["fclass"].to_numpy()[seg.index.to_numpy()]
    out = d[["fp_id", "seg", "st_setback_m"]].merge(seg[["st_width_m", "st_height_m", "st_hw", "st_frontage", "st_orient_deg", "st_class"]],
                                                     left_on="seg", right_index=True, how="left").drop(columns="seg")
    out.to_parquet(keep(e / "streetscape_fp.parquet"), index=False)
    print(f"  {len(out):,} footprints with a street ({len(out) / len(fp):.1%}); median width {out['st_width_m'].median():.1f} m, "
          f"H/W {out['st_hw'].median():.2f}, setback {out['st_setback_m'].median():.1f} m -> {e / 'streetscape_fp.parquet'}")


if __name__ == "__main__":
    main()
