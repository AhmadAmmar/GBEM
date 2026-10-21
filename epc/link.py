"""Step 3 - link each certificate to a building footprint through its UPRN location.

    python link.py [--areas london belfast] [--max-dist 5]

Each distinct UPRN point is linked to the footprint that contains it (link_method "within"; if several footprints
contain it, the smallest). A point outside every footprint is linked to the nearest footprint within --max-dist
metres ("nearest", with the distance); beyond that it stays unlinked ("none"). UPRN points often lie on or just
outside the outline of the building (address points at the door or the street side), hence the small tolerance.
Output: data/<area>/epc/certificates_linked.parquet (the certificate table with fp_id, link_method, link_dist_m)
and link_log.json
"""
import argparse, datetime, json, pathlib
import geopandas as gpd
import numpy as np
import pandas as pd

PHD = pathlib.Path(__file__).resolve().parents[2]
DATA = PHD / "data"
EPSG = {"london": 27700, "belfast": 29902}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--areas", nargs="+", default=["london", "belfast"])
    ap.add_argument("--max-dist", type=float, default=5.0)
    a = ap.parse_args()
    for area in a.areas:
        d = DATA / area / "epc"
        cert = pd.read_parquet(d / "certificates.parquet")
        fp = gpd.read_parquet(d / "footprints.parquet")[["fp_id", "geometry"]]
        fp["fp_area"] = fp.area
        pts = cert.drop_duplicates("UPRN")[["UPRN", "x", "y"]]
        P = gpd.GeoDataFrame(pts, geometry=gpd.points_from_xy(pts.x, pts.y), crs=EPSG[area])
        w = gpd.sjoin(P, fp, how="left", predicate="within").sort_values("fp_area").drop_duplicates("UPRN")
        w["link_method"] = np.where(w["fp_id"].notna(), "within", None)
        w["link_dist_m"] = np.where(w["fp_id"].notna(), 0.0, np.nan)
        miss = w[w["fp_id"].isna()][["UPRN", "geometry"]]
        near = gpd.sjoin_nearest(gpd.GeoDataFrame(miss, crs=EPSG[area]), fp[["fp_id", "geometry"]], how="left",
                                 max_distance=a.max_dist, distance_col="dist").drop_duplicates("UPRN")
        near = near[near["fp_id"].notna()].set_index("UPRN")
        w = w.set_index("UPRN")
        w.loc[near.index, "fp_id"] = near["fp_id"]
        w.loc[near.index, "link_method"] = "nearest"
        w.loc[near.index, "link_dist_m"] = near["dist"].round(2)
        w["link_method"] = w["link_method"].fillna("none")
        out = cert.merge(w[["fp_id", "link_method", "link_dist_m"]], left_on="UPRN", right_index=True, how="left")
        out.to_parquet(d / "certificates_linked.parquet", index=False)
        per_fp = out.dropna(subset=["fp_id"]).groupby("fp_id")["UPRN"].nunique()
        log = {"run": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "max_dist_m": a.max_dist,
               "uprns": int(len(w)), "uprns_by_link": w["link_method"].value_counts().to_dict(),
               "certificates_by_link": out["link_method"].value_counts().to_dict(),
               "footprints_with_certificates": int(len(per_fp)),
               "uprns_per_footprint": {"median": float(per_fp.median()), "p95": float(per_fp.quantile(0.95)), "max": int(per_fp.max())}}
        (d / "link_log.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
        print(area, json.dumps(log))


if __name__ == "__main__":
    main()
