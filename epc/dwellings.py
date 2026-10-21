"""Step 4b - dwellings per footprint, and the position of each property in its building.

    python dwellings.py [--areas london belfast]

Mapped footprints often cover a whole terrace row or a pair of semi-detached houses as one polygon (in London 31% of
houses lie in a footprint with more than two UPRNs; Microsoft machine-learned footprints never separate houses). The
footprint's shape then describes the block, not the dwelling. This step adds measures that hold for blocks:

per footprint   n_uprn            all UPRNs (address points) inside the footprint: OS Open UPRN 2025-07 (London),
                                  OSNI UPRN list with coordinates (Belfast)
                area_per_uprn_m2  footprint area / n_uprn
per certificate pos_in_block      distance of the property's UPRN point from the footprint centroid along the long
                                  axis, divided by half the length of the long axis: about 0 in the middle of a block,
                                  about 1 at its ends (end-terrace, semi-detached, corner flats)
Output: data/<area>/epc/dwellings_fp.parquet (fp_id) and dwellings_cert.parquet (cert_id)
"""
import argparse, pathlib
import duckdb
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

PHD = pathlib.Path(__file__).resolve().parents[2]
DATA = PHD / "data"
UPRN = {"london": (DATA / "uprn/osopenuprn_202507.csv", "UPRN", "X_COORDINATE", "Y_COORDINATE"),
        "belfast": (DATA / "belfast/uprn/BELFS_20250829_F/uprn_union_with_xy_v2.csv", "UPRN_key", "X_COR", "Y_COR")}
EXTENT = {"london": (501000, 153000, 564000, 204000), "belfast": (315000, 357000, 351000, 390000)}
EPSG = {"london": 27700, "belfast": 29902}


def uprn_points(area):
    path, idc, xc, yc = UPRN[area]
    x0, y0, x1, y1 = EXTENT[area]
    q = f"""SELECT DISTINCT CAST("{idc}" AS VARCHAR) AS uprn, CAST("{xc}" AS DOUBLE) AS x, CAST("{yc}" AS DOUBLE) AS y
            FROM read_csv('{path.as_posix()}', header=true, all_varchar=true)
            WHERE TRY_CAST("{xc}" AS DOUBLE) BETWEEN {x0} AND {x1} AND TRY_CAST("{yc}" AS DOUBLE) BETWEEN {y0} AND {y1}"""
    return duckdb.connect().execute(q).df()


def long_axis(geoms):
    """Unit vector and half-length of the long side of each footprint's minimum rotated rectangle."""
    mrr = shapely.minimum_rotated_rectangle(geoms)
    ok = shapely.get_type_id(mrr) == 3
    vec = np.full((len(geoms), 2), np.nan); half = np.full(len(geoms), np.nan)
    coords, idx = shapely.get_coordinates(shapely.get_exterior_ring(mrr[ok]), return_index=True)
    first = np.searchsorted(idx, np.arange(ok.sum()))
    p0, p1, p2 = coords[first], coords[first + 1], coords[first + 2]
    a, b = p1 - p0, p2 - p1
    la, lb = np.hypot(*a.T), np.hypot(*b.T)
    v = np.where((la >= lb)[:, None], a, b)
    L = np.maximum(la, lb)
    vec[ok] = v / np.maximum(L, 1e-9)[:, None]; half[ok] = L / 2
    return vec, half


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--areas", nargs="+", default=["london", "belfast"])
    for area in ap.parse_args().areas:
        d = DATA / area / "epc"
        fp = gpd.read_parquet(d / "footprints.parquet", columns=["fp_id", "geometry"])
        u = uprn_points(area)
        P = gpd.GeoDataFrame(u, geometry=gpd.points_from_xy(u.x, u.y), crs=EPSG[area])
        j = gpd.sjoin(P, fp, how="inner", predicate="within")
        n = j.groupby("fp_id")["uprn"].nunique()
        out = pd.DataFrame({"fp_id": fp["fp_id"]})
        out["n_uprn"] = out["fp_id"].map(n).fillna(0).astype("int32")
        area_m2 = fp.area.to_numpy()
        out["area_per_uprn_m2"] = np.where(out["n_uprn"] > 0, area_m2 / np.maximum(out["n_uprn"], 1), np.nan)
        out.to_parquet(keep(d / "dwellings_fp.parquet"), index=False)

        c = pd.read_parquet(d / "certificates_linked.parquet", columns=["cert_id", "UPRN", "x", "y", "fp_id"])
        c = c.dropna(subset=["fp_id"]).drop_duplicates("UPRN")
        g = fp.set_index("fp_id").loc[c["fp_id"], "geometry"].values
        cen = shapely.get_coordinates(shapely.centroid(g))
        vec, half = long_axis(g)
        along = np.abs((c["x"].to_numpy() - cen[:, 0]) * vec[:, 0] + (c["y"].to_numpy() - cen[:, 1]) * vec[:, 1])
        pos = pd.DataFrame({"UPRN": c["UPRN"].values, "pos_in_block": np.clip(along / np.maximum(half, 1e-9), 0, 1.5)})
        certs = pd.read_parquet(d / "certificates_linked.parquet", columns=["cert_id", "UPRN"]).merge(pos, on="UPRN", how="left")
        certs[["cert_id", "pos_in_block"]].to_parquet(keep(d / "dwellings_cert.parquet"), index=False)
        print(area, f"UPRN points {len(u):,}; footprints with >=1 UPRN {int((out.n_uprn > 0).sum()):,};",
              "n_uprn quantiles", out.loc[out.n_uprn > 0, "n_uprn"].quantile([.5, .9, .99]).to_dict())


if __name__ == "__main__":
    main()
