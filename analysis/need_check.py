"""Dwelling-level ground truth: how much does the EPC band say about metered energy use? (NEED 2024, DESNZ)

    python need_check.py [--year 2022]

Data: the 4 million property anonymised NEED sample (geo/get_need.py), England and Wales, no location below region.
Gas: annual consumption of --year with a valid reading (GasValFlag = 'V'), homes heated by gas (consumption > 2,000
kWh). Electricity: valid readings.
1. Explanation of log gas use by the EPC band alone, by floor area band alone, and by band + floor area + type + age
   (eta squared / R2 of group means, i.e. ordinary least squares on dummies), for England and Wales and for London
   (region E12000007). Median gas by band and floor area band.
2. Measured effect of insulation: homes with cavity wall insulation (CWI) or loft insulation (LI) installed in a given
   year Y (2010-2017): change of gas use from Y-1 to Y+2 against homes of the same band, type and floor area without
   any recorded measure (difference in medians of the percentage change).
Outputs in data/national/need_2024/: need_band_summary.csv, need_explained.csv, need_measures.csv
"""
import argparse, pathlib, sys, zipfile
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

ROOT = pathlib.Path(__file__).resolve().parents[2] / "data/national/need_2024"
LONDON = "E12000007"


def r2_groups(y, keys):
    """share of the variance of y explained by the means of the groups defined by keys (OLS on all interactions)"""
    g = y.groupby([k for k in keys]).transform("mean")
    return 1 - ((y - g) ** 2).sum() / ((y - y.mean()) ** 2).sum()


def r2_additive(y, frame):
    X = pd.get_dummies(frame.astype(str), drop_first=True).astype(float)
    X.insert(0, "c", 1.0)
    beta, *_ = np.linalg.lstsq(X.to_numpy(), y.to_numpy(), rcond=None)
    pred = X.to_numpy() @ beta
    return 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2022)
    a = ap.parse_args()
    z = zipfile.ZipFile(ROOT / "raw/anonymised-NEED-data-2024-4million.zip")
    member = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
    years = list(range(2009, 2023))
    cols = ["PROP_TYPE", "PROP_AGE_BAND", "FLOOR_AREA_BAND", "REGION", "EPC", "IMD_BAND_ENG", "CWI_FLAG", "CWI_DATE", "LI_FLAG", "LI_DATE",
            "PV_FLAG", "MAIN_HEAT_FUEL"] + [f"Gcons{y}" for y in years] + [f"GasValFlag{y}" for y in years] + [f"Econs{a.year}", f"ElecValFlag{a.year}"]
    with z.open(member) as f:
        d = pd.read_csv(f, usecols=cols, low_memory=False)
    print(f"NEED: {len(d):,} properties", flush=True)
    d["band"] = d["EPC"].astype(str)
    y = a.year
    gas = d[(d[f"GasValFlag{y}"] == "V") & (d[f"Gcons{y}"] > 2000)].copy()
    gas["lg"] = np.log(gas[f"Gcons{y}"])
    rows, summ = [], []
    for name, s in (("England and Wales", gas), ("London", gas[gas["REGION"] == LONDON])):
        e = s[s["band"].ne("No EPC")]
        rows.append({"area": name, "homes_with_epc": len(e), "homes_all": len(s),
                     "r2_epc_band": r2_groups(e["lg"], [e["band"]]),
                     "r2_floor_area_band": r2_groups(e["lg"], [e["FLOOR_AREA_BAND"]]),
                     "r2_type_age_floor": r2_additive(e["lg"], e[["PROP_TYPE", "PROP_AGE_BAND", "FLOOR_AREA_BAND"]]),
                     "r2_band_type_age_floor": r2_additive(e["lg"], e[["band", "PROP_TYPE", "PROP_AGE_BAND", "FLOOR_AREA_BAND"]])})
        t = e.groupby("band")[f"Gcons{y}"].agg(["size", "median"]).rename(columns={"size": "homes", "median": "gas_kwh_median"})
        t["area"] = name
        summ.append(t.reset_index())
        t2 = e.groupby(["band", "FLOOR_AREA_BAND"])[f"Gcons{y}"].median().unstack()
        t2.columns = [f"gas_median_floor_band_{c}" for c in t2.columns]
        summ[-1] = summ[-1].merge(t2, left_on="band", right_index=True, how="left")
    ex = pd.DataFrame(rows)
    ex.round(4).to_csv(keep(ROOT / "need_explained.csv"), index=False)
    bs = pd.concat(summ, ignore_index=True)
    bs.round(1).to_csv(keep(ROOT / "need_band_summary.csv"), index=False)
    print(ex.round(3).to_string(index=False))
    print(bs[["area", "band", "homes", "gas_kwh_median"]].to_string(index=False))
    # insulation measures: change of gas use from Y-1 to Y+2
    meas = []
    base = d[(d["CWI_FLAG"] == 0) & (d["LI_FLAG"] == 0) & (d["PV_FLAG"] == 0)]
    for m in ("CWI", "LI"):
        for yi in range(2010, 2018):
            treated = d[(d[f"{m}_FLAG"] == 1) & (pd.to_numeric(d[f"{m}_DATE"], errors="coerce") == yi)]
            def change(s):
                ok = (s[f"GasValFlag{yi - 1}"] == "V") & (s[f"GasValFlag{yi + 2}"] == "V") & (s[f"Gcons{yi - 1}"] > 2000)
                s = s[ok]
                return s, 100 * (s[f"Gcons{yi + 2}"] / s[f"Gcons{yi - 1}"] - 1)
            t, ct = change(treated)
            c, cc = change(base)
            if len(t) < 200:
                continue
            meas.append({"measure": m, "install_year": yi, "treated_homes": len(t), "control_homes": len(c),
                         "treated_median_change_pct": ct.median(), "control_median_change_pct": cc.median(),
                         "effect_pct_points": ct.median() - cc.median()})
    me = pd.DataFrame(meas)
    me.round(2).to_csv(keep(ROOT / "need_measures.csv"), index=False)
    print(me.round(1).to_string(index=False))
    print("written", ROOT)


if __name__ == "__main__":
    main()
