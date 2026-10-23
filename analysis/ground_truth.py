"""How good is the label, and does it agree with measured energy? Two checks with the data in hand.

    python ground_truth.py --area london|belfast

1. Label noise floor (test-retest): the same property certified twice within --days (default 365) days, where the
   later certificate does not record a change of main fuel, property type or built form (most such pairs are a
   re-assessment of an unchanged home: a new sale or letting, or a corrected certificate). The disagreement between
   two assessors of the same home is the noise in the label: no model can be expected to agree with certificates
   better than certificates agree with themselves.
   Reported: pairs, mean and median absolute SAP difference, same band, within one band, quadratic weighted kappa.
2. Measured consumption (London; DESNZ by LSOA): Spearman correlation of the area mean SAP of the current stock with
   measured domestic gas and electricity per meter in 2024, with and without the mean floor area of the area
   (partial correlation on ranks), and of the whole-stock predicted SAP where available.
Outputs in data/<area>/analysis/: ground_truth_retest.csv, ground_truth_retest_pairs.parquet, ground_truth_energy.csv
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import cohen_kappa_score
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"
BANDS = list("ABCDEFG")


def retest(area, days):
    e = pd.read_parquet(DATA / area / "analysis/cert_enriched.parquet",
                        columns=["cert_id", "uprn", "date", "sap", "band", "fuel", "property_type", "built_form", "floor_area"])
    e = e[e["uprn"].notna() & ~e["uprn"].isin(["nan", "None"]) & e["sap"].notna() & e["date"].notna()].sort_values(["uprn", "date"])
    prev = e.groupby("uprn").shift()
    p = pd.DataFrame({"uprn": e["uprn"], "date": e["date"], "gap_days": (e["date"] - prev["date"]).dt.days,
                      "sap1": prev["sap"], "sap2": e["sap"], "band1": prev["band"], "band2": e["band"],
                      "same_fuel": e["fuel"].eq(prev["fuel"]), "same_type": e["property_type"].eq(prev["property_type"]) & e["built_form"].eq(prev["built_form"]),
                      "area_change": (e["floor_area"] / prev["floor_area"] - 1).abs()})
    p = p[(p["gap_days"] > 0) & (p["gap_days"] <= days) & p["same_fuel"] & p["same_type"] & (p["area_change"].fillna(0) <= 0.1)
          & p["band1"].isin(BANDS) & p["band2"].isin(BANDS)]
    d = (p["sap2"] - p["sap1"]).abs()
    b1, b2 = np.searchsorted(BANDS, p["band1"]), np.searchsorted(BANDS, p["band2"])
    r = {"area": area, "max_days": days, "pairs": len(p), "sap_abs_diff_mean": d.mean(), "sap_abs_diff_median": d.median(),
         "sap_abs_diff_p90": d.quantile(0.9), "sap_diff_mean": (p["sap2"] - p["sap1"]).mean(), "same_band": float(np.mean(b1 == b2)),
         "within_one_band": float(np.mean(np.abs(b1 - b2) <= 1)), "qwk": cohen_kappa_score(b1, b2, weights="quadratic")}
    return r, p


def energy(area):
    if area != "london":
        return None
    en = pd.read_parquet(DATA / "london/energy_desnz/lsoa_energy_london.parquet")
    e24 = en[en["year"] == 2024].pivot_table(index="lsoa", columns="fuel", values="mean_kwh")
    u = pd.read_parquet(DATA / "london/analysis/units_nbhd.parquet").set_index("nbhd")
    u = u.join(e24, how="inner")
    rows = []
    for fuel in ("gas", "electricity"):
        g = u[["sap_mean", "floor_area", fuel]].dropna()
        rho, p = stats.spearmanr(g["sap_mean"], g[fuel])
        # partial rank correlation controlling for mean floor area (bigger homes use more energy at any efficiency)
        r = g.rank()
        res = lambda y: y - np.polyval(np.polyfit(r["floor_area"], y, 1), r["floor_area"])
        prho, pp = stats.pearsonr(res(r["sap_mean"]), res(r[fuel]))
        rows.append({"fuel": fuel, "lsoas": len(g), "spearman_sap": rho, "p": p, "partial_spearman_sap_given_floor_area": prho, "p_partial": pp,
                     "spearman_floor_area": stats.spearmanr(g["floor_area"], g[fuel])[0]})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--days", type=int, default=365)
    a = ap.parse_args()
    out = DATA / a.area / "analysis"
    r, pairs = retest(a.area, a.days)
    pd.DataFrame([r]).round(4).to_csv(keep(out / "ground_truth_retest.csv"), index=False)
    pairs.to_parquet(keep(out / "ground_truth_retest_pairs.parquet"), index=False)
    print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})
    e = energy(a.area)
    if e is not None:
        e.round(4).to_csv(keep(out / "ground_truth_energy.csv"), index=False)
        print(e.round(3).to_string(index=False))
    print("written", out)


if __name__ == "__main__":
    main()
