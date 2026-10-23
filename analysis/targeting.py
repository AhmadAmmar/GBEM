"""Which targeting rule reaches the areas in need? (London LSOAs)

    python targeting.py [--top 0.2]

Each rule ranks the LSOAs and selects the top share (--top, default 20%):
  F-G share            share of the current stock rated F or G (certificates)
  low mean SAP         lowest mean SAP of the current stock
  income deprivation   IoD 2025 income domain (most deprived first)
  physics demand       highest median space-heating demand per m2 (analysis/physics_check.py)
  fabric first         highest share of homes with heat-loss parameter >= 3 W/m2K (analysis/heatpump_readiness.py)
  combined             vulnerability index (analysis/vulnerability.py: low SAP and income deprivation)
Outcomes (top --top of LSOAs by):
  fuel poverty (official)   DESNZ sub-regional estimates, 2024 data, LILEE metric (its efficiency criterion makes
                            efficiency rules partly circular: read with care)
  high gas use              metered domestic gas per meter, DESNZ 2024
  high use and low income   product of the percentile ranks of gas per meter and income deprivation
Reported per rule and outcome: precision (share of selected LSOAs that are in the outcome's top share), recall (share
of the outcome's LSOAs that are selected; equal to precision when both shares are the same) and Spearman correlation
between rule score and outcome.
Output: data/london/analysis/targeting_rules.csv
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
from scipy import stats
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=float, default=0.2)
    a = ap.parse_args()
    A = DATA / "london/analysis"
    u = pd.read_parquet(A / "units_nbhd.parquet").set_index("nbhd")[["n", "sap_mean", "share_FG"]]
    dep = pd.read_parquet(DATA / "london/deprivation/imd2025_lsoa_london.parquet").set_index("lsoa")[["income_rank"]]
    vul = pd.read_parquet(A / "units_dep.parquet").set_index("unit")[["vuln_index"]]
    hp = pd.read_parquet(A / "hp_readiness_units_nbhd.parquet").set_index("nbhd")[["share_fabric_first"]]
    ph = pd.read_parquet(A / "physics_cert.parquet", columns=["cert_id", "q_as_described_kwh_m2"])
    cur = pd.read_parquet(A / "stock_current.parquet", columns=["cert_id", "nbhd"])
    q = cur.merge(ph, on="cert_id").groupby("nbhd")["q_as_described_kwh_m2"].median().rename("q_median")
    fp = pd.read_parquet(DATA / "london/fuel_poverty/fuel_poverty_lsoa_london.parquet").set_index("lsoa")[["share_fuel_poor"]]
    en = pd.read_parquet(DATA / "london/energy_desnz/lsoa_energy_london.parquet")
    gas = en[(en["fuel"] == "gas") & (en["year"] == 2024)].set_index("lsoa")["mean_kwh"].rename("gas_per_meter")
    t = u.join([dep, vul, hp, q, fp, gas], how="inner").dropna()
    t = t[t["n"] >= 10]
    t["income_deprivation"] = -t["income_rank"]                          # higher = more deprived
    t["use_and_income"] = t["gas_per_meter"].rank(pct=True) * t["income_deprivation"].rank(pct=True)
    rules = {"F-G share": t["share_FG"], "low mean SAP": -t["sap_mean"], "income deprivation": t["income_deprivation"],
             "physics demand": t["q_median"], "fabric first": t["share_fabric_first"], "combined": t["vuln_index"]}
    outcomes = {"fuel poverty (official)": t["share_fuel_poor"], "high gas use": t["gas_per_meter"], "high use and low income": t["use_and_income"]}
    k = int(round(a.top * len(t)))
    rows = []
    for on, o in outcomes.items():
        target = set(o.nlargest(k).index)
        for rn, r in rules.items():
            sel = set(r.nlargest(k).index)
            hit = len(sel & target)
            rows.append({"outcome": on, "rule": rn, "lsoas": len(t), "selected": k, "precision": hit / k, "recall": hit / len(target),
                         "spearman": stats.spearmanr(r, o)[0]})
    res = pd.DataFrame(rows)
    res.round(4).to_csv(keep(A / "targeting_rules.csv"), index=False)
    print(res.pivot(index="rule", columns="outcome", values="precision").round(2).to_string())
    print("\nSpearman:\n", res.pivot(index="rule", columns="outcome", values="spearman").round(2).to_string())


if __name__ == "__main__":
    main()
