"""Step 4 - reproduction check: new point features against the earlier Earth Engine samples of the same buildings.

    python compare_old.py --area belfast --new <features parquet> --old <earlier samples csv> --id uid

For each earlier variable, the new candidates (time windows, satellites) are compared on the records present in both:
number of pairs, Spearman and Pearson correlation, median of new minus old. The candidate with the highest Spearman
correlation shows which composite the earlier variable most likely corresponds to. The earlier scripts are not
available, so their time windows and masking are not known; differences are expected where these differ.
Output: data/<area>/gee_v2/features/compare_old_<area>.csv
"""
import argparse
import numpy as np
import pandas as pd
import spec

# earlier variable -> (new candidates, conversion applied to the earlier values)
MAP = {
    "s2_NDVI": (["s2_NDVI_annual_pt", "s2_NDVI_summer_pt"], None),
    "s2_NDBI": (["s2_NDBI_annual_pt", "s2_NDBI_summer_pt"], None),
    "s2_NDWI": (["s2_NDWI_annual_pt", "s2_NDWI_summer_pt", "s2_MNDWI_annual_pt"], None),
    "s2_EVI": (["s2_EVI_annual_pt", "s2_EVI_summer_pt"], None),
    "s2_BSI": (["s2_BSI_annual_pt", "s2_BSI_summer_pt"], None),
    "s2_UI": (["s2_UI_annual_pt", "s2_UI_summer_pt"], None),
    "s2_NDRE1": (["s2_NDRE1_annual_pt", "s2_NDRE1_summer_pt"], None),
    "s2_NIRv": (["s2_NIRv_annual_pt", "s2_NIRv_summer_pt"], None),
    "s1_VV_dB": (["s1_VV_dB_annual_pt"], None),
    "s1_VH_dB": (["s1_VH_dB_annual_pt"], None),
    "s1_VV_minus_VH_dB": (["s1_VVminusVH_dB_annual_pt"], None),
    "l8_LST_C": (["landsat_LST_annual_pt", "landsat_LST_summer_pt", "landsat_LST_winter_pt"], None),
    "l8_sUHI_C": (["landsat_sUHI_annual_pt", "landsat_sUHI_summer_pt", "landsat_sUHI_winter_pt"], None),
    "modis_LST_night_C": ([f"modis_{s}_night_{w}_pt" for s in ("terra", "aqua") for w in ("annual", "summer", "winter")], None),
    "modis_sUHI_C": ([f"modis_sUHI_{s}_night_{w}_pt" for s in ("terra", "aqua") for w in ("annual", "summer", "winter")], None),
    "era5_t2m_K": (["era5_t2m_annual_pt", "era5_t2m_summer_pt", "era5_t2m_winter_pt"], lambda v: v - 273.15),
    "era5_tp_m": (["era5_precip_mm_annual_pt", "era5_precip_mm_summer_pt"], lambda v: v * 1000),
    "era5_wind_speed": (["era5_wind_speed_annual_pt", "era5_wind_speed_summer_pt", "era5_wind_speed_winter_pt"], None),
    "viirs_avg_rad": (["viirs_avg_rad_annual_pt"], None),
    "dem_elev": (["terrain_elevation_m_pt"], None),
    "dem_slope": (["terrain_slope_deg_pt"], None),
    "dem_eastness": (["terrain_eastness_pt"], None),
    "dem_northness": (["terrain_northness_pt"], None),
    # earlier London samples (reflectance 0-1, backscatter in dB, Landsat band 10)
    **{b: ([f"s2_{b}_annual_pt", f"s2_{b}_summer_pt"], None) for b in ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"]},
    "NDVI": (["s2_NDVI_annual_pt", "s2_NDVI_summer_pt"], None),
    "NDBI": (["s2_NDBI_annual_pt", "s2_NDBI_summer_pt"], None),
    "NDWI": (["s2_NDWI_annual_pt", "s2_NDWI_summer_pt"], None),
    "EVI": (["s2_EVI_annual_pt", "s2_EVI_summer_pt"], None),
    "GNDVI": (["s2_GNDVI_annual_pt", "s2_GNDVI_summer_pt"], None),
    "VV": (["s1_VV_dB_annual_pt"], None),
    "VH": (["s1_VH_dB_annual_pt"], None),
    "L8B10": (["landsat_LST_annual_pt", "landsat_LST_summer_pt", "landsat_LST_winter_pt"], None),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--new", required=True); ap.add_argument("--old", required=True)
    ap.add_argument("--id", required=True)
    a = ap.parse_args()
    new = pd.read_parquet(a.new)
    if a.old.lower().endswith(".csv"):
        old = pd.read_csv(a.old)
    else:                                   # GeoJSON, GeoPackage, shapefile: attributes only
        import pyogrio
        old = pyogrio.read_dataframe(a.old, read_geometry=False)
    old["rec_id"] = old[a.id].astype(str)
    m = old.merge(new, on="rec_id", how="inner")
    rows = []
    for o, (cands, conv) in MAP.items():
        if o not in m:
            continue
        ov = pd.to_numeric(m[o], errors="coerce")
        ov = conv(ov) if conv else ov
        # each candidate is also tried as footprint mean and neighbourhood mean (the earlier scripts sampled either
        # points or polygons)
        cands = [c[:-3] + s for c in cands for s in ("_pt", "_fp", "_nb100")] if all(c.endswith("_pt") for c in cands) else cands
        for c in cands:
            if c not in m:
                continue
            nv = m[c]
            ok = ov.notna() & nv.notna()
            if ok.sum() < 30:
                continue
            rows.append({"old": o, "new": c, "n": int(ok.sum()), "spearman": round(ov[ok].corr(nv[ok], method="spearman"), 3),
                         "pearson": round(ov[ok].corr(nv[ok]), 3), "median_new_minus_old": round(float(np.median(nv[ok] - ov[ok])), 3)})
    R = pd.DataFrame(rows)
    R["best"] = R.groupby("old")["spearman"].transform("max") == R["spearman"]
    out = spec.features_dir(a.area) / f"compare_old_{a.area}.csv"
    R.to_csv(out, index=False)
    pd.set_option("display.width", 200)
    print(f"{len(m)} records in both. Best match per earlier variable:")
    print(R[R["best"]].drop(columns="best").to_string(index=False))
    print("written", out)


if __name__ == "__main__":
    main()
