"""Open 3D building model of Greater Belfast from open data only: Overture building footprints (ODbL) with heights and
roof form from the OpenDataNI LiDAR (Open Government Licence), as a GeoPackage and as 1 km CityJSON tiles (LoD1.2).

    python open3d_belfast.py [--version v0.1] [--relidar] [--tiles-only]

Why: there is no open 3D building model for Northern Ireland; England, the Netherlands and others have one. This model
is built only from openly licensed inputs, so that it can be published as an open dataset. It uses no Energy
Performance Certificates, no addresses and no OSNI Fusion footprints.

Steps (outputs in data/belfast/open3d/<version>/):
1. Footprints: all Overture buildings (release in OVERTURE) in the Greater Belfast extent, cleaned to valid polygons in
   the Irish Grid (EPSG:29902); the Overture id (GERS) is kept as the building id.
2. LiDAR: epc/lidar_ni.py on these footprints (all OpenDataNI surveys, Belfast City 2006 and River Basin 2007-2014):
   median and 90th percentile of the height above ground, median ground height, roof slope, south-facing and flat
   shares, survey and year, share of the footprint covered (cached in lidar_fp.parquet; --relidar recomputes).
3. Height of each building, with its source: the LiDAR median where the footprint is at least 50% covered and the
   building existed at the survey (median at least 2 m); otherwise the Overture height; otherwise Overture floors x 3 m;
   otherwise no height (kept in the GeoPackage, left out of the 3D tiles). Ground: the LiDAR ground median, else the
   Copernicus DEM (30 m).
4. Outputs:
     buildings.gpkg              every footprint with its attributes (layer "buildings")
     tiles/IG_<E>_<N>.city.json  CityJSON 2.0, LoD1.2, one file per 1 km tile (Irish Grid kilometre of the
                                 south-west corner), buildings assigned by their representative point
     quality.json                coverage, height sources, and agreement of LiDAR heights with Overture heights and
                                 floors where both exist
     metadata.json, README.md, LICENSE.txt   description, sources, licence (ODbL 1.0) and attribution
Heights are as at the LiDAR survey (2006-2014): buildings changed since then keep their surveyed height (flags show the
survey year). LoD1.2: flat roofs at the median height; the 90th percentile is an attribute.
"""
import argparse, datetime, json, pathlib, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from shapely.geometry import box
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "epc"))
from safeio import keep                      # existing outputs are archived, never overwritten
from export_cityjson import Vertices, clean_polygons, solid, SCALE

CODE = pathlib.Path(__file__).resolve().parents[1]
DATA = CODE.parent / "data"
OVERTURE_RELEASE = "2026-09-23.1"
OVERTURE = DATA / f"overture/{OVERTURE_RELEASE}/belfast_buildings.parquet"
EXTENT = (315000, 357000, 351000, 390000)     # Greater Belfast, Irish Grid (code/gee/spec.py)
EPSG = 29902
TILE = 1000


def footprints(out):
    """Overture buildings in the extent as valid polygons in EPSG:29902, with their Overture attributes"""
    p = out / "footprints_overture.parquet"
    if p.exists():
        return gpd.read_parquet(p)
    o = pd.read_parquet(OVERTURE)
    g = gpd.GeoDataFrame(o.drop(columns="geometry_wkb"), geometry=gpd.GeoSeries.from_wkb(o["geometry_wkb"]), crs=4326).to_crs(EPSG)
    g = g[g.intersects(box(*EXTENT))].copy()
    g["geometry"] = shapely.make_valid(shapely.force_2d(g.geometry.values))
    g["geometry"] = [x if x.geom_type in ("Polygon", "MultiPolygon") else
                     shapely.unary_union([q for q in getattr(x, "geoms", []) if q.geom_type in ("Polygon", "MultiPolygon")]) for x in g.geometry]
    g = g[~g.geometry.is_empty & (g.geometry.area >= 4.0)]                 # under 4 m2: not a building
    g = gpd.GeoDataFrame({"fp_id": g["id"].values, "overture_height_m": g["height"].values, "overture_floors": g["num_floors"].values,
                          "overture_class": g["class"].values, "overture_subtype": g["subtype"].values,
                          "footprint_source": [d[0] if d is not None and len(d) else None for d in g["datasets"]]},
                         geometry=g.geometry.values, crs=EPSG).drop_duplicates("fp_id").reset_index(drop=True)
    g.to_parquet(p)
    return g


def dem_heights(points):
    dem = next((DATA / "belfast/gee_v2/raw").glob("*_dem_30m.tif"), None)
    if dem is None:
        return np.full(len(points), np.nan)
    import rasterio
    with rasterio.open(dem) as r:
        z = np.array([v[0] for v in r.sample([(p.x, p.y) for p in points])], dtype=float)
        if r.nodata is not None:
            z[z == r.nodata] = np.nan
    return z


def heights(g, lid):
    d = g.merge(lid, on="fp_id", how="left")
    ok_lidar = (d["lidar_valid_share"] >= 0.5) & (d["lidar_height_med_m"] >= 2.0)
    h = pd.Series(np.nan, index=d.index); src = pd.Series("none", index=d.index)
    h[ok_lidar], src[ok_lidar] = d.loc[ok_lidar, "lidar_height_med_m"], "lidar"
    m = h.isna() & (d["overture_height_m"] > 2)
    h[m], src[m] = d.loc[m, "overture_height_m"], "overture_height"
    m = h.isna() & (d["overture_floors"] >= 1)
    h[m], src[m] = d.loc[m, "overture_floors"] * 3.0, "overture_floors_x3m"
    d["height_m"], d["height_source"] = h.round(2), src
    rp = d.geometry.representative_point()
    zg = d["lidar_ground_med_m"].where(d["lidar_valid_share"] >= 0.5)
    miss = zg.isna()
    zg[miss] = dem_heights(rp[miss].values)
    d["ground_m"], d["ground_source"] = zg.round(2), np.where(miss, "copernicus_dem_30m", "lidar_dtm")
    d["tile"] = [f"IG_{int(p.x // TILE)}_{int(p.y // TILE)}" for p in rp]
    d["changed_since_survey"] = d["lidar_built_after_survey"].fillna(False).astype(bool)
    return d


def write_tiles(d, out, version):
    tiles = out / "tiles"; tiles.mkdir(exist_ok=True)
    sem = {"surfaces": [{"type": "GroundSurface"}, {"type": "RoofSurface"}, {"type": "WallSurface"}]}
    n_tiles, n_bldg = 0, 0
    for tid, t in d[d["height_m"].notna() & d["ground_m"].notna()].groupby("tile"):
        V = Vertices((float(t.total_bounds[0]), float(t.total_bounds[1]), float(np.floor(t["ground_m"].min()))))
        objs = {}
        for _, r in t.iterrows():
            polys = clean_polygons(r.geometry)
            if not polys:
                continue
            z0, z1 = float(r["ground_m"]), float(r["ground_m"] + r["height_m"])
            parts = [solid(p, z0, z1, V) for p in polys]
            geom = ({"type": "Solid", "lod": "1.2", "boundaries": parts[0][0], "semantics": {**sem, "values": parts[0][1]}} if len(parts) == 1 else
                    {"type": "MultiSolid", "lod": "1.2", "boundaries": [p[0] for p in parts], "semantics": {**sem, "values": [p[1] for p in parts]}})
            att = {"overtureId": r["fp_id"], "measuredHeight": float(r["height_m"]), "heightSource": r["height_source"],
                   "heightP90": None if pd.isna(r.get("lidar_height_p90_m")) else round(float(r["lidar_height_p90_m"]), 2),
                   "groundHeight": float(r["ground_m"]), "groundSource": r["ground_source"],
                   "roofSlope": None if pd.isna(r.get("lidar_roof_slope_med_deg")) else round(float(r["lidar_roof_slope_med_deg"]), 1),
                   "roofFlatShare": None if pd.isna(r.get("lidar_roof_flat_share")) else round(float(r["lidar_roof_flat_share"]), 3),
                   "roofSouthShare": None if pd.isna(r.get("lidar_roof_south_share")) else round(float(r["lidar_roof_south_share"]), 3),
                   "lidarSurvey": r.get("lidar_survey") if isinstance(r.get("lidar_survey"), str) else None,
                   "lidarYear": None if pd.isna(r.get("lidar_survey_year")) else int(r["lidar_survey_year"]),
                   "lidarCoverage": None if pd.isna(r.get("lidar_valid_share")) else round(float(r["lidar_valid_share"]), 3),
                   "changedSinceSurvey": bool(r["changed_since_survey"]),
                   "footprintSource": r["footprint_source"], "overtureClass": r["overture_class"] if isinstance(r["overture_class"], str) else None}
            objs[r["fp_id"]] = {"type": "Building", "attributes": {k: v for k, v in att.items() if v is not None}, "geometry": [geom]}
        if not objs:
            continue
        real = np.array(V.list) * SCALE + np.array(V.origin)
        cj = {"type": "CityJSON", "version": "2.0", "transform": {"scale": [SCALE] * 3, "translate": list(map(float, V.origin))},
              "metadata": {"referenceSystem": f"https://www.opengis.net/def/crs/EPSG/0/{EPSG}",
                           "geographicalExtent": [*map(float, real.min(0)), *map(float, real.max(0))],
                           "title": f"Open 3D buildings of Greater Belfast {version}, tile {tid} (LoD1.2)",
                           "referenceDate": datetime.date.today().isoformat(), "identifier": f"belfast-open3d-{version}-{tid}"},
              "CityObjects": objs, "vertices": V.list}
        (tiles / f"{tid}.city.json").write_text(json.dumps(cj, separators=(",", ":")), encoding="utf-8")
        n_tiles += 1; n_bldg += len(objs)
    return n_tiles, n_bldg


def quality(d):
    both = d[(d["height_source"] == "lidar") & (d["overture_height_m"] > 2)]
    fl = d[(d["height_source"] == "lidar") & (d["overture_floors"] >= 1)]
    q = {"buildings": int(len(d)), "height_sources": d["height_source"].value_counts().to_dict(),
         "ground_sources": pd.Series(d["ground_source"]).value_counts().to_dict(),
         "footprint_sources": d["footprint_source"].value_counts(dropna=False).to_dict(),
         "changed_since_survey": int(d["changed_since_survey"].sum()),
         "lidar_survey_years": d["lidar_survey_year"].value_counts().sort_index().to_dict(),
         "lidar_vs_overture_height": {"n": int(len(both)),
                                      "mean_difference_m": round(float((both["lidar_height_med_m"] - both["overture_height_m"]).mean()), 2) if len(both) else None,
                                      "median_abs_difference_m": round(float((both["lidar_height_med_m"] - both["overture_height_m"]).abs().median()), 2) if len(both) else None,
                                      "spearman": round(float(both["lidar_height_med_m"].corr(both["overture_height_m"], method="spearman")), 3) if len(both) > 2 else None},
         "lidar_vs_floors": {"n": int(len(fl)),
                             "median_height_per_floor_m": round(float((fl["lidar_height_p90_m"] / fl["overture_floors"]).median()), 2) if len(fl) else None,
                             "spearman": round(float(fl["lidar_height_med_m"].corr(fl["overture_floors"], method="spearman")), 3) if len(fl) > 2 else None}}
    return q


README = """# Open 3D buildings of Greater Belfast ({version})

A 3D building model of Greater Belfast (Northern Ireland) built only from open data: {n:,} building footprints from
Overture Maps with heights and roof form from the OpenDataNI airborne LiDAR surveys (2006-2014).

## Files
- `buildings.gpkg`: every footprint (Irish Grid, EPSG:29902) with its height, height source, ground height, roof
  slope, flat and south-facing roof shares, LiDAR survey and year, coverage and flags.
- `tiles/IG_<E>_<N>.city.json`: CityJSON 2.0, LoD1.2 buildings (footprint extruded from the ground to the median roof
  height), one file per 1 km tile; E and N are the kilometres of the tile's south-west corner in the Irish Grid.
- `quality.json`: coverage, height sources and agreement with independent heights.

## Method
Heights are the median of the LiDAR surface model minus the terrain model over each footprint (90th percentile also
given), from the most recent survey covering at least 80% of the footprint, else at least 50%. Where LiDAR is missing
or the building is newer than the survey, the Overture height or floors x 3 m is used, as recorded in `heightSource`.
Ground heights are the LiDAR terrain median (else the Copernicus DEM, 30 m). Heights describe the buildings at the
survey date. Code: https://github.com/AhmadAmmar/GBEM (`code/geo/open3d_belfast.py`, `code/epc/lidar_ni.py`).

## Licence and attribution
Open Database License (ODbL) 1.0: https://opendatacommons.org/licenses/odbl/1-0/ (required because the footprints
come from OpenStreetMap through Overture Maps). Please attribute:
- Building footprints: Overture Maps Foundation, release {release} (buildings theme, ODbL); building data
  (c) OpenStreetMap contributors, Microsoft (machine-learned footprints where OpenStreetMap has none).
- LiDAR: OpenDataNI, Belfast City LiDAR 2006 and River Basin LiDAR 2007-2014, contains public sector information
  licensed under the Open Government Licence v3.0.
- Terrain where LiDAR is missing: Copernicus DEM GLO-30 (c) DLR e.V. 2010-2014 and (c) Airbus Defence and Space GmbH
  2014-2018, provided under COPERNICUS by the European Union and ESA.

Produced by Ahmad Ammar, School of Geography and Environmental Sciences, Ulster University (PhD research funded by a
Vice-Chancellor's Research Scholarship). (c) Ulster University. Draft: not yet published.
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v0.1"); ap.add_argument("--relidar", action="store_true")
    ap.add_argument("--tiles-only", action="store_true")
    a = ap.parse_args()
    out = DATA / "belfast/open3d" / a.version; out.mkdir(parents=True, exist_ok=True)
    g = footprints(out)
    print(f"footprints: {len(g):,}", flush=True)
    if a.relidar or not (out / "lidar_fp.parquet").exists():
        import lidar_ni
        fp_file = out / "_footprints_for_lidar.parquet"
        g[["fp_id", "geometry"]].to_parquet(fp_file)
        lidar_ni.main(footprints=fp_file, out_dir=out)
        fp_file.unlink()
    lid = pd.read_parquet(out / "lidar_fp.parquet")
    d = heights(g, lid)
    if not a.tiles_only:
        cols = [c for c in d.columns if c != "tile"]
        keep(out / "buildings.gpkg")
        gpd.GeoDataFrame(d[cols], geometry="geometry", crs=EPSG).to_file(out / "buildings.gpkg", layer="buildings", driver="GPKG")
    n_tiles, n_bldg = write_tiles(d, out, a.version)
    q = quality(d)
    q.update({"tiles": n_tiles, "buildings_in_tiles": n_bldg})
    keep(out / "quality.json").write_text(json.dumps(q, indent=1, default=str), encoding="utf-8")
    meta = {"title": f"Open 3D buildings of Greater Belfast {a.version}", "created": datetime.datetime.now().isoformat(timespec="minutes"),
            "extent_epsg29902": EXTENT, "crs": f"EPSG:{EPSG}", "lod": "1.2", "overture_release": OVERTURE_RELEASE,
            "licence": "ODbL-1.0", "code": "https://github.com/AhmadAmmar/GBEM", "buildings": len(d), "buildings_in_tiles": n_bldg, "tiles": n_tiles}
    keep(out / "metadata.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    keep(out / "README.md").write_text(README.format(version=a.version, n=len(d), release=OVERTURE_RELEASE), encoding="utf-8")
    (out / "LICENSE.txt").write_text("Open Database License (ODbL) v1.0: https://opendatacommons.org/licenses/odbl/1-0/\n"
                                     "See README.md for the attribution of each source.\n", encoding="utf-8")
    print(json.dumps(q, indent=1, default=str))


if __name__ == "__main__":
    main()
