"""Year-to-year stability of the features, on the same certificates.

    python stability.py --area london --tag epc2024 [--years 2020 2021 2024]

For every feature present in all years, the Spearman correlation between the values of each pair of years is
computed on the same records. A feature that ranks buildings the same way every year (high correlation) describes
the buildings or their setting; a low correlation means the feature mostly reflects the conditions of the year
(weather, clear-sky days, scene sampling). This bears on transfer between years: features that are not stable need
to be normalised (for example surface temperature relative to the rural reference) or used with care.
Output: data/<area>/gee_v2/features/stability_<tag>.csv
"""
import argparse, itertools
import pandas as pd
import spec
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--tag", required=True); ap.add_argument("--years", nargs="+", type=int)
    a = ap.parse_args()
    d = spec.features_dir(a.area)
    years = a.years or sorted(int(p.stem.rsplit("_", 1)[1]) for p in d.glob(f"{a.tag}_[0-9][0-9][0-9][0-9].parquet"))
    F = {y: pd.read_parquet(d / f"{a.tag}_{y}.parquet").set_index("rec_id") for y in years}
    common = set.intersection(*[set(f.columns) for f in F.values()]) - {"year", "pt_source", "fp_px_10m", "fp_px_30m"}
    rows = []
    for c in sorted(common):
        r = {"feature": c}
        for y1, y2 in itertools.combinations(years, 2):
            x, z = F[y1][c], F[y2][c]
            ok = x.notna() & z.notna()
            r[f"rho_{y1}_{y2}"] = round(x[ok].corr(z[ok], method="spearman"), 3) if ok.sum() > 30 and x[ok].nunique() > 1 else None
        rows.append(r)
    R = pd.DataFrame(rows)
    rho = [c for c in R if c.startswith("rho_")]
    R["rho_min"] = R[rho].min(axis=1)
    R.sort_values("rho_min").to_csv(keep(d / f"stability_{a.tag}.csv"), index=False)
    pd.set_option("display.width", 200)
    key = ["s2_NDVI_annual_pt", "s2_NDBI_annual_pt", "s2_B11_annual_pt", "s1_VV_dB_annual_pt", "s1_VVminusVH_dB_annual_pt",
           "landsat_LST_annual_pt", "landsat_LST_summer_pt", "landsat_sUHI_summer_pt", "modis_terra_night_winter_pt",
           "modis_sUHI_terra_night_winter_pt", "era5_HDD_annual_pt", "viirs_avg_rad_annual_pt"]
    print(f"{a.area}: {len(R)} features, years {years}")
    print(R[R.feature.isin(key)].set_index("feature").loc[[k for k in key if k in set(R.feature)]].to_string())
    print("Share of features with rho_min >= 0.8:", round((R.rho_min >= 0.8).mean(), 3), "| < 0.5:", round((R.rho_min < 0.5).mean(), 3))


if __name__ == "__main__":
    main()
