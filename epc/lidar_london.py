"""Building height and roof form for Greater London from the Environment Agency LiDAR composite (GEE batch b6).

    python lidar_london.py

Input: gbem_v2_0_1_london_lidar_ea_2m[-<row>-<col>].tif in data/london/gee_v2/raw/ (gee/ingest.py), 2 m, British
National Grid. Each 2 m cell holds the mean over its 1 m building pixels (surface minus terrain >= 1.5 m) of:
  height_dm, height_max_dm   mean and maximum height above terrain (decimetres)
  slope_ddeg                 roof slope (tenths of a degree)
  south_pct, flat_pct        share of south-facing (slope >= 15 deg, aspect 135-225 deg) and flat (< 10 deg) pixels
The tiles are read in windows; footprints (footprints.parquet) are rasterised on each window and a footprint split by a
window or tile edge is taken from the window holding most of it.
Per footprint, the same columns as lidar_ni.py (Belfast), so assemble.py treats both areas alike:
  height_med_m, height_p90_m, roof_slope_med_deg, roof_south_share, roof_flat_share, valid_share, n_px,
  survey ("EA composite 2022"), survey_year (empty: the composite mixes surveys up to 2022), built_after_survey
  (here: under 30% of the footprint has building pixels, because only heights >= 1.5 m are exported)
Output: data/london/epc/lidar_fp.parquet (fp_id) and lidar_log.json
"""
import json, pathlib
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio import features as rfeatures
from rasterio.windows import Window
import shapely
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

PHD = pathlib.Path(__file__).resolve().parents[2]
DATA = PHD / "data"
RAW = DATA / "london/gee_v2/raw"
WIN = 4096                                    # window size in pixels (8 km at 2 m)
NODATA = -32768


def tiles():
    t = sorted(p for p in RAW.glob("gbem_v2_0_1_london_lidar_ea_2m*.tif") if "__conflict" not in p.name)
    if not t:
        raise SystemExit(f"no LiDAR export in {RAW}: run batch b6 in Earth Engine and ingest it first")
    return t


def main():
    fp = gpd.read_parquet(DATA / "london/epc/footprints.parquet", columns=["fp_id", "geometry"])
    geoms = fp.geometry.values
    tree = shapely.STRtree(geoms)
    area = shapely.area(geoms)
    rows, log = [], {"tiles": []}
    for path in tiles():
        with rasterio.open(path) as r:
            assert list(r.descriptions) == ["height_dm", "height_max_dm", "slope_ddeg", "south_pct", "flat_pct"], r.descriptions
            res = r.transform.a
            log["tiles"].append({"file": path.name, "width": r.width, "height": r.height})
            print(path.name, r.width, "x", r.height, flush=True)
            for row0 in range(0, r.height, WIN):
                for col0 in range(0, r.width, WIN):
                    w = Window(col0, row0, min(WIN, r.width - col0), min(WIN, r.height - row0))
                    t = r.window_transform(w)
                    h_, w_ = int(w.height), int(w.width)
                    bbox = shapely.box(t.c, t.f + h_ * t.e, t.c + w_ * res, t.f)
                    idx = tree.query(bbox, predicate="intersects")
                    if not len(idx):
                        continue
                    a = r.read(window=w)
                    lab = rfeatures.rasterize(zip(geoms[idx], idx + 1), out_shape=(h_, w_), transform=t, fill=0, dtype="int32")
                    sel = (lab > 0) & (a[0] != NODATA)
                    if not sel.any():
                        continue
                    df = pd.DataFrame({"i": lab[sel] - 1, "hgt": a[0][sel] / 10, "hmax": a[1][sel] / 10, "slope": a[2][sel] / 10,
                                       "south": a[3][sel] / 100, "flat": a[4][sel] / 100})
                    g = df.groupby("i")
                    s = pd.DataFrame({"n_px": g.size(), "height_med_m": g.hgt.median(), "height_p90_m": g.hmax.quantile(0.9),
                                      "roof_slope_med_deg": g.slope.median(), "roof_south_share": g.south.mean(),
                                      "roof_flat_share": g.flat.mean()})
                    rows.append(s.reset_index())
    R = pd.concat(rows, ignore_index=True).sort_values("n_px", ascending=False).drop_duplicates("i")
    R["valid_share"] = np.minimum(1, R["n_px"] * res * res / area[R["i"].to_numpy()])
    R["survey"], R["survey_year"] = "EA composite 2022", np.nan
    R["fp_id"] = fp["fp_id"].values[R["i"].to_numpy()]
    # only pixels >= 1.5 m are exported, so a building missing from the LiDAR shows as low coverage, not low height
    R["built_after_survey"] = R["valid_share"] < 0.3
    out = R.drop(columns=["i"]).rename(columns={c: f"lidar_{c}" for c in R.columns if c not in ("i", "fp_id")})
    d = DATA / "london/epc"
    out.to_parquet(keep(d / "lidar_fp.parquet"), index=False)
    log.update({"footprints": int(len(fp)), "with_lidar": int(len(out)),
                "with_good_coverage": int((out["lidar_valid_share"] >= 0.8).sum()),
                "height_med_m_median": float(out["lidar_height_med_m"].median())})
    keep(d / "lidar_log.json").write_text(json.dumps(log, indent=1, default=int), encoding="utf-8")
    print(json.dumps({k: v for k, v in log.items() if k != "tiles"}, indent=1, default=int))


if __name__ == "__main__":
    main()
