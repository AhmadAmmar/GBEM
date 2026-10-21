"""Step 4 - morphology of every footprint and its surroundings, and distance to streets.

    python morphology.py [--areas london belfast]

Per footprint (area grid, metres):
  area_m2, perimeter_m, compactness      4 pi area / perimeter^2 (1 = circle)
  convexity                              area / area of the convex hull
  elongation                             1 - short / long side of the minimum rotated rectangle
  orientation_deg                        bearing of the long side, 0-180 (0 = north-south)
  n_vertices
  shared_wall_m, shared_wall_ratio       length of the outline within 0.5 m of another footprint, and its share of
                                         the perimeter (0 detached ... high terraced or enclosed)
  n_adjacent                             footprints within 0.5 m
  nn_dist_m                              distance to the nearest other footprint (0 if adjoining)
Surroundings, within 100 m and 250 m of the footprint centroid (centroids weighted by footprint area on a 10 m grid,
summed over a disc):
  bcov_<r>     building coverage ratio (footprint area / disc area)
  bcount_<r>   number of buildings
  barea_<r>    mean footprint area
Streets (OpenStreetMap roads of the same Geofabrik extract):
  road_dist_m        distance from the footprint to the nearest road open to motor vehicles
  major_road_dist_m  distance to the nearest motorway, trunk, primary or secondary road (and links)
  road_density_250   length of roads open to motor vehicles within 250 m, km per km2
Source attributes kept: source and src_dataset (OSNI, or the Overture dataset: OpenStreetMap / Microsoft ML Buildings),
height_m and num_floors (Overture, where given), volume_m3 = area x height, bldg_class (Overture), osni_typecode
(Belfast, OSNI dwelling type).
Output: data/<area>/epc/morphology.parquet
"""
import argparse, datetime, json, pathlib
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from scipy.signal import fftconvolve
from footprints import OSM, EXTENT

PHD = pathlib.Path(__file__).resolve().parents[2]
DATA = PHD / "data"
CELL = 10.0
DRIVABLE = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link",
            "tertiary", "tertiary_link", "unclassified", "residential", "living_street", "service", "road"}
MAJOR = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link"}


def shape_metrics(geoms):
    area, per = shapely.area(geoms), shapely.length(geoms)
    hull = shapely.area(shapely.convex_hull(geoms))
    mrr = shapely.minimum_rotated_rectangle(geoms)
    ok = shapely.get_type_id(mrr) == 3                 # degenerate footprints give a line or point, not a rectangle
    s1 = np.full(len(geoms), np.nan); s2 = s1.copy(); orient = s1.copy()
    coords, idx = shapely.get_coordinates(shapely.get_exterior_ring(mrr[ok]), return_index=True)
    first = np.searchsorted(idx, np.arange(ok.sum()))
    p0, p1, p2 = coords[first], coords[first + 1], coords[first + 2]
    a, b = np.hypot(*(p1 - p0).T), np.hypot(*(p2 - p1).T)
    long_vec = np.where((a >= b)[:, None], p1 - p0, p2 - p1)
    s1[ok], s2[ok] = a, b
    orient[ok] = (np.degrees(np.arctan2(long_vec[:, 0], long_vec[:, 1])) + 180) % 180
    short, long_ = np.minimum(s1, s2), np.maximum(s1, s2)
    return {"area_m2": area, "perimeter_m": per, "compactness": 4 * np.pi * area / per ** 2, "convexity": area / hull,
            "elongation": np.where(long_ > 0, 1 - short / long_, 0), "orientation_deg": orient,
            "n_vertices": shapely.get_num_coordinates(geoms)}


def adjacency(geoms, per):
    tree = shapely.STRtree(geoms)
    buf = shapely.buffer(geoms, 0.5, quad_segs=2)
    i, j = tree.query(buf, predicate="intersects")
    keep = i != j
    i, j = i[keep], j[keep]
    shared = np.zeros(len(geoms))
    for s in range(0, len(i), 500_000):           # in chunks to limit memory
        a, b = i[s:s + 500_000], j[s:s + 500_000]
        np.add.at(shared, a, shapely.length(shapely.intersection(shapely.boundary(geoms[a]), buf[b])))
    n_adj = np.bincount(i, minlength=len(geoms))
    _, nn = tree.query_nearest(geoms, exclusive=True, return_distance=True, all_matches=False)
    return {"shared_wall_m": shared, "shared_wall_ratio": np.minimum(1, shared / per), "n_adjacent": n_adj, "nn_dist_m": nn[1] if isinstance(nn, tuple) else nn}


def disc(r):
    k = int(round(r / CELL))
    yy, xx = np.mgrid[-k:k + 1, -k:k + 1]
    return (xx ** 2 + yy ** 2 <= k ** 2).astype("float32")


def grid_index(xs, ys, ext):
    x0, y0, x1, y1 = ext
    nx, ny = int((x1 - x0) / CELL), int((y1 - y0) / CELL)
    c = np.clip(((xs - x0) / CELL).astype(int), 0, nx - 1)
    r = np.clip(((y1 - ys) / CELL).astype(int), 0, ny - 1)
    return r, c, (ny, nx)


def surroundings(cent, area, ext):
    r, c, shape = grid_index(cent[:, 0], cent[:, 1], ext)
    A = np.zeros(shape, "float32"); N = np.zeros(shape, "float32")
    np.add.at(A, (r, c), area); np.add.at(N, (r, c), 1)
    out = {}
    for rad in (100, 250):
        k = disc(rad)
        sa, sn = fftconvolve(A, k, mode="same"), fftconvolve(N, k, mode="same")
        disc_area = k.sum() * CELL ** 2
        out[f"bcov_{rad}"] = np.clip(sa[r, c] / disc_area, 0, None)
        out[f"bcount_{rad}"] = np.round(sn[r, c])
        out[f"barea_{rad}"] = np.where(sn[r, c] > 0.5, sa[r, c] / np.maximum(sn[r, c], 1), np.nan)
    return out


def streets(area, geoms, cent, ext):
    epsg, _ = EXTENT[area]
    bb = gpd.GeoSeries([shapely.box(*ext)], crs=epsg).to_crs(4326).total_bounds
    roads = gpd.read_file(f"zip://{OSM[area].as_posix()}!gis_osm_roads_free_1.shp", bbox=tuple(bb)).to_crs(epsg)
    drv = roads[roads["fclass"].isin(DRIVABLE)].geometry.values
    maj = roads[roads["fclass"].isin(MAJOR)].geometry.values
    out = {}
    for name, lines in (("road_dist_m", drv), ("major_road_dist_m", maj)):
        t = shapely.STRtree(lines)
        _, d = t.query_nearest(geoms, return_distance=True, all_matches=False)
        out[name] = d
    # road length density: points every 10 m along the drivable roads, counted on the 10 m grid, summed over 250 m
    pts = shapely.get_coordinates(shapely.segmentize(drv, CELL))
    r, c, shape = grid_index(pts[:, 0], pts[:, 1], ext)
    L = np.zeros(shape, "float32"); np.add.at(L, (r, c), CELL)
    k = disc(250)
    dens = fftconvolve(L, k, mode="same") / 1000 / (k.sum() * CELL ** 2 / 1e6)
    rr, cc, _ = grid_index(cent[:, 0], cent[:, 1], ext)
    out["road_density_250"] = np.clip(dens[rr, cc], 0, None)
    return out, {"roads_drivable": int(len(drv)), "roads_major": int(len(maj))}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--areas", nargs="+", default=["london", "belfast"])
    for area in ap.parse_args().areas:
        d = DATA / area / "epc"
        fp = gpd.read_parquet(d / "footprints.parquet")
        _, ext = EXTENT[area]
        geoms = fp.geometry.values
        cent = shapely.get_coordinates(shapely.centroid(geoms))
        m = shape_metrics(geoms)
        m.update(adjacency(geoms, m["perimeter_m"]))
        m.update(surroundings(cent, m["area_m2"], ext))
        s, slog = streets(area, geoms, cent, ext)
        m.update(s)
        out = pd.DataFrame({"fp_id": fp["fp_id"].values, "source": fp["source"].values,
                            **{c: fp[c].values for c in ("src_dataset", "bldg_class", "osni_typecode", "height_m", "num_floors") if c in fp},
                            **{k: np.round(np.asarray(v, dtype="float64"), 4) for k, v in m.items()}})
        if "height_m" in out:
            out["volume_m3"] = out["area_m2"] * pd.to_numeric(out["height_m"], errors="coerce")
        out.to_parquet(d / "morphology.parquet", index=False)
        log = {"run": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "footprints": len(out), **slog,
               "medians": {k: round(float(np.nanmedian(out[k])), 3) for k in m}}
        (d / "morphology_log.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
        print(area, json.dumps(log))


if __name__ == "__main__":
    main()
