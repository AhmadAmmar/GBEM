"""Building height and roof form from the OpenDataNI LiDAR (Greater Belfast).

    python lidar_ni.py

Inputs: the Belfast City 2006 survey and the River Basin surveys 2007-2014 (get_ni_lidar.py), read directly from their
zips (never extracted or changed). Each survey has 1 km tiles of a surface model (DSM) and a terrain model (DTM),
0.5 m or 1 m, Irish Grid; a DSM tile is paired with the DTM tile of the same name.

Per footprint and survey, over the pixels inside the footprint (footprints rasterised on each tile; a footprint split
by a tile edge is taken from the tile holding most of it):
  height_med_m, height_p90_m   median and 90th percentile of DSM - DTM
  roof_slope_med_deg           median slope of the DSM
  roof_south_share             share of pixels with slope >= 15 deg facing 135-225 deg (south-facing roof planes)
  roof_flat_share              share of pixels with slope < 10 deg
  valid_share                  share of the footprint area with LiDAR values
  ground_med_m                 median DTM (ground height above Malin Head datum)
For each footprint the most recent survey with valid_share >= 0.8 is kept (survey name and year recorded). A median
height below 2 m usually means the building did not exist at the survey date: flag built_after_survey.
Output: data/belfast/epc/lidar_fp.parquet (fp_id) and lidar_log.json. From Python, main(footprints, out_dir) runs the
same for any footprints in EPSG:29902 (for example the open 3D building model, geo/open3d_belfast.py).
"""
import json, pathlib, re, zipfile
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio import features as rfeatures
import shapely
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

PHD = pathlib.Path(__file__).resolve().parents[2]
DATA = PHD / "data"
LIDAR = DATA / "belfast/lidar"
EXT = (".asc", ".grd")
SKIPPED = []                                  # tiles that could not be read (empty or damaged files)
MM_TILES = set()                              # surveys with tiles stored in millimetres (converted to metres)


def surveys():
    """(zip path, survey name, year) for every downloaded survey."""
    out = [(z, z.stem, 2006) for z in sorted((LIDAR / "opendatani_belfast_city_2006").glob("BelfastCityLidar_*.zip"))]
    for z in sorted((LIDAR / "opendatani_river_basin").glob("*/*.zip")):
        m = re.search(r"_(\d{4})$", z.stem)
        out.append((z, z.stem, int(m.group(1)) if m else None))
    return out


def kind_of(member):
    """'DSM' or 'DTM' from the folder (or file) name; file names differ between surveys (J2768DSM.grd, D0900853.asc,
    J3474_DEM.asc), so tiles are paired by location, not by name."""
    folder = member.rsplit("/", 1)[0].lower() if "/" in member else ""
    low = folder or member.lower()
    return "DSM" if "dsm" in low else ("DTM" if "dtm" in low else None)


def tile_pairs(z):
    """[(DSM source, DTM member)] for one survey zip, paired by tile location. A DSM source is ('grid', member) or, where
    the surface is published only as a point cloud, ('xyz', member)."""
    names = zipfile.ZipFile(z).namelist()
    dtm, dsm_grid, dsm_xyz = {}, {}, []
    for n in names:
        low, k = n.lower(), kind_of(n)
        if low.endswith(EXT) and k:
            try:                                  # all tiles are ESRI ASCII grids (also the .grd files)
                with rasterio.open(f"/vsizip/{z.as_posix()}/{n}", driver="AAIGrid") as r:
                    b = tuple(round(v) for v in r.bounds)
            except Exception:                     # empty or damaged tile in the published zip
                SKIPPED.append(f"{z.name}/{n}"); continue
            (dtm if k == "DTM" else dsm_grid)[b] = n
        elif low.endswith(".xyz") and k == "DSM":
            dsm_xyz.append(n)
    pairs = [(("grid", dsm_grid[b]), m) for b, m in dtm.items() if b in dsm_grid]
    if dsm_xyz:                                   # point clouds: matched to a DTM tile by the point extent
        zf = zipfile.ZipFile(z)
        for n in dsm_xyz:
            with zf.open(n) as f:
                head = pd.read_csv(f, sep=r"\s+", header=None, nrows=2000, usecols=[0, 1])
            cx, cy = head[0].median(), head[1].median()
            hit = [m for b, m in dtm.items() if b[0] <= cx < b[2] and b[1] <= cy < b[3]]
            if hit:
                pairs.append((("xyz", n), hit[0]))
    return pairs


def read(z, member):
    with rasterio.open(f"/vsizip/{z.as_posix()}/{member}", driver="AAIGrid") as r:
        a = r.read(1).astype("float32")
        if r.nodata is not None:
            a[a == r.nodata] = np.nan
        a[a < -100] = np.nan
        return a, r.transform


def read_dsm(z, src, dtm_shape, dtm_t):
    """DSM on the grid of the DTM tile: a grid is resampled if its pixel size differs; a point cloud is gridded by the
    highest return per cell (first-surface heights)."""
    kind, member = src
    if kind == "grid":
        a, t = read(z, member)
        if a.shape == dtm_shape and tuple(t)[:6] == tuple(dtm_t)[:6]:
            return a
        from rasterio.warp import reproject, Resampling
        out = np.full(dtm_shape, np.nan, dtype="float32")
        reproject(a, out, src_transform=t, dst_transform=dtm_t, src_crs="EPSG:29902", dst_crs="EPSG:29902",
                  resampling=Resampling.bilinear, src_nodata=np.nan, dst_nodata=np.nan)
        return out
    with zipfile.ZipFile(z).open(member) as f:
        p = pd.read_csv(f, sep=r"\s+", header=None, usecols=[0, 1, 2]).to_numpy()
    h, w = dtm_shape
    col = np.floor((p[:, 0] - dtm_t.c) / dtm_t.a).astype(int)
    row = np.floor((p[:, 1] - dtm_t.f) / dtm_t.e).astype(int)
    ok = (row >= 0) & (row < h) & (col >= 0) & (col < w)
    out = np.full(h * w, -np.inf, dtype="float64")
    np.maximum.at(out, row[ok] * w + col[ok], p[ok, 2])
    out[np.isinf(out)] = np.nan
    return out.reshape(h, w).astype("float32")


def main(footprints=None, out_dir=None):
    """footprints: a GeoParquet with fp_id and geometry in EPSG:29902 (default: the project's footprints); out_dir: where
    lidar_fp.parquet and lidar_log.json are written (default: data/belfast/epc)"""
    fp = gpd.read_parquet(footprints or DATA / "belfast/epc/footprints.parquet", columns=["fp_id", "geometry"])
    geoms = fp.geometry.values
    tree = shapely.STRtree(geoms)
    area = shapely.area(geoms)
    rows, log = [], {"surveys": []}
    for z, name, year in surveys():
        pairs = tile_pairs(z)
        log["surveys"].append({"survey": name, "year": year, "tiles": len(pairs)})
        print(f"{name} ({year}): {len(pairs)} tiles", flush=True)
        for dsm_src, dtm_member in pairs:
            try:
                dtm, t = read(z, dtm_member)
                dsm = read_dsm(z, dsm_src, dtm.shape, t)
            except Exception as err:              # truncated or damaged tile in the published zip: skipped and logged
                SKIPPED.append(f"{z.name}/{dsm_src[1]} ({str(err)[:60]})"); continue
            # some 2012 surveys (Saintfield, Mossley, Glenavy, Bangor extension) store heights in millimetres: ground in
            # the study area is below 600 m, so a tile median above 2000 means millimetres
            for a in (dtm, dsm):
                if np.isfinite(a).any() and np.nanmedian(a) > 2000:
                    a /= 1000
                    MM_TILES.add(name)
            res = t.a
            h, w = dsm.shape
            bbox = shapely.box(t.c, t.f + h * t.e, t.c + w * res, t.f)
            idx = tree.query(bbox, predicate="intersects")
            if not len(idx):
                continue
            lab = rfeatures.rasterize(zip(geoms[idx], idx + 1), out_shape=(h, w), transform=t, fill=0, dtype="int32")
            gy, gx = np.gradient(dsm, res)
            slope = np.degrees(np.arctan(np.hypot(gx, gy)))
            aspect = (np.degrees(np.arctan2(gx, gy)) + 180) % 360           # direction the plane faces, clockwise from north
            sel = lab > 0
            df = pd.DataFrame({"i": lab[sel] - 1, "hgt": (dsm - dtm)[sel], "ground": dtm[sel], "slope": slope[sel], "aspect": aspect[sel]})
            df = df[df["hgt"].notna()]
            if df.empty:
                continue
            df["south"] = (df.slope >= 15) & (df.aspect >= 135) & (df.aspect <= 225)
            df["flat"] = df.slope < 10
            g = df.groupby("i")
            s = pd.DataFrame({"n_px": g.size(), "height_med_m": g.hgt.median(), "height_p90_m": g.hgt.quantile(0.9),
                              "roof_slope_med_deg": g.slope.median(), "roof_south_share": g.south.mean(), "roof_flat_share": g.flat.mean(),
                              "ground_med_m": g.ground.median()})
            s["valid_share"] = np.minimum(1, s["n_px"] * res * res / area[s.index])
            s["survey"], s["survey_year"] = name, year
            rows.append(s.reset_index())
    R = pd.concat(rows, ignore_index=True)
    # per footprint and survey keep the tile holding most of it; then the most recent survey with good coverage
    R = R.sort_values("n_px", ascending=False).drop_duplicates(["i", "survey"])
    R["good"] = R["valid_share"] >= 0.8
    R = R.sort_values(["good", "survey_year", "valid_share"], ascending=[False, False, False]).drop_duplicates("i")
    R["fp_id"] = fp["fp_id"].values[R["i"].to_numpy()]
    R["built_after_survey"] = R["height_med_m"] < 2
    out = R.drop(columns=["i", "good"]).rename(columns={c: f"lidar_{c}" for c in R.columns if c not in ("i", "good", "fp_id")})
    d = pathlib.Path(out_dir) if out_dir else DATA / "belfast/epc"
    d.mkdir(parents=True, exist_ok=True)
    out.to_parquet(keep(d / "lidar_fp.parquet"), index=False)
    log.update({"skipped_tiles": SKIPPED, "surveys_in_mm": sorted(MM_TILES), "footprints": int(len(fp)), "with_lidar": int(len(out)),
                "with_good_coverage": int((out["lidar_valid_share"] >= 0.8).sum()),
                "by_survey": out["lidar_survey"].value_counts().to_dict(),
                "height_med_m_median": float(out["lidar_height_med_m"].median()),
                "built_after_survey": int(out["lidar_built_after_survey"].sum())})
    keep(d / "lidar_log.json").write_text(json.dumps(log, indent=1, default=int), encoding="utf-8")
    print(json.dumps({k: v for k, v in log.items() if k != "surveys"}, indent=1, default=int))


if __name__ == "__main__":
    main()
