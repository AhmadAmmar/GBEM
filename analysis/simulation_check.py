"""Steady-state heat loss against dynamic simulation: does the physics of this thesis rank homes as EnergyPlus does?

    python simulation_check.py

Data: the synthetic Irish residential stock of Ali et al. (2024, Data in Brief 110241; Mendeley m6vv9k9gcd v5, CC BY 4.0):
about one million EnergyPlus/jEPlus simulations of four house types (bungalow, detached, semi-detached, terraced) with
varied U-values, air change rate, window-to-wall ratio, set-points, internal gains, HVAC efficiency and weather
(historical and 2030). Each type has a fixed geometry (floor area per type).

The steady-state calculation of analysis/physics_check.py is applied to the same inputs. The geometry of each type is
reconstructed with the rules used for the certificates (epc/physics.py): storeys (bungalow 1, others 2), a square
footprint of floor area / storeys, storey height 2.8 m, party walls (detached 0, semi-detached 1, terraced 2 sides),
windows = window-to-wall ratio x exposed wall area, one door of 2 m2:
    HLC = sum(U x A) + y x envelope (y = 0.08) + 0.33 x n x V
    Q   = HLC x (T_set - 15.5 + 15.5 - T_base) ... reduced here to HLC x HDD x 24/1000 with a degree-day base that moves
          with the set-point (base = set-point - 4.5 K for internal and solar gains)
The heating degree-days of each weather file are not published with the data, so the comparison uses ranks: Spearman
correlation of Q with the simulated space-heating demand (Total_Heating_Energy) per m2, overall, by house type and by
weather file, and the share of simulated variance explained by a linear fit (R2). A second variant without the
set-point term shows how much of the agreement comes from the fabric alone.
Output: data/national/ucd_synthetic_stock/simulation_check.csv
"""
import pathlib, sys
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

PHD = pathlib.Path(__file__).resolve().parents[2]
D = PHD / "data/national/ucd_synthetic_stock"
STOREYS = {"Bungalow": 1, "Detached": 2, "Semi Detached": 2, "Terraced": 2}
PARTY_SIDES = {"Bungalow": 0, "Detached": 0, "Semi Detached": 1, "Terraced": 2}
H_STOREY = 2.8
HDD_REF = 2400.0                             # nominal degree-days (base 15.5 C); only the ranks are compared


def steady_state(d, with_setpoint=True):
    n = d["Building_Type"].map(STOREYS)
    floor = d["Total_Building_Area"]
    a = floor / n                                                # footprint area
    side = np.sqrt(a)
    h = n * H_STOREY
    wall_gross = (4 - d["Building_Type"].map(PARTY_SIDES)) * side * h
    win = wall_gross * d["Window_to_Wall_Ratio"] / 100
    door = 2.0
    wall = (wall_gross - win - door).clip(lower=0)
    env = wall + win + door + 2 * a
    hlc = (d["Wall_Insulation_U-Value"] * wall + d["Window_Insulation_U-Value"] * win + d["Door_Insulation_U-Value"] * door
           + d["Roof_Insulation_U-Value"] * a + d["Floor_Insulation_U-Value"] * a + 0.08 * env
           + 0.33 * d["Air_Change_Rate"] * a * h)
    scale = 1.0
    if with_setpoint:                                            # degree-days grow roughly linearly with the base
        base = d["Heating_Setpoint_Temperature"] - 4.5
        scale = (HDD_REF + 200 * (base - 15.5)).clip(lower=200) / HDD_REF
    return hlc * HDD_REF * scale * 24 / 1000 / floor, hlc / floor


def main():
    cols = ["Weather_File", "Building_Type", "Floor_Insulation_U-Value", "Door_Insulation_U-Value", "Roof_Insulation_U-Value",
            "Window_Insulation_U-Value", "Wall_Insulation_U-Value", "Air_Change_Rate", "Window_to_Wall_Ratio",
            "Heating_Setpoint_Temperature", "Total_Building_Area", "Total_Heating_Energy"]
    src = next((D / "raw").glob("urban_building_stock_datasets_*.csv"))
    d = pd.read_csv(src, usecols=cols)
    d = d[d["Total_Heating_Energy"] > 0]
    sim = d["Total_Heating_Energy"] / d["Total_Building_Area"]
    rows = []
    for variant, sp in (("fabric, ventilation and set-point", True), ("fabric and ventilation only", False)):
        q, hlp = steady_state(d, sp)
        for name, m in [("all", np.ones(len(d), bool))] + [(f"type: {t}", (d["Building_Type"] == t).to_numpy()) for t in STOREYS] \
                + [(f"weather: {w}", (d["Weather_File"] == w).to_numpy()) for w in sorted(d["Weather_File"].unique())]:
            x, y = q[m].to_numpy(), sim[m].to_numpy()
            r2 = np.corrcoef(x, y)[0, 1] ** 2
            rows.append({"variant": variant, "group": name, "n": int(m.sum()), "spearman": round(spearmanr(x, y)[0], 3),
                         "r2_linear": round(r2, 3), "median_q_steady_kwh_m2": round(float(np.median(x)), 1),
                         "median_sim_kwh_m2": round(float(np.median(y)), 1)})
    out = pd.DataFrame(rows)
    out.to_csv(keep(D / "simulation_check.csv"), index=False)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
