"""Inputs for a HEM engine trial: does the fabric proxy (analysis/physics_check.py) rank dwellings as HEM does?

    python make_archetypes.py --demo <HEM repo>/examples/input/core/short/demo.json --out <folder>

Starts from an official HEM example dwelling (any number of zones; the roof is varied only if the base has one;
the simulation period of the base is kept unless --full-year) and varies only the fabric over the ranges found in the certificates: wall U (solid, cavity unfilled,
cavity filled or insulated), roof U (uninsulated, 100 mm, 270 mm loft insulation), window U (single, older double,
modern double) and air permeability (leaky, typical, tight): 3 x 3 x 3 x 3 = 81 variants. Simulation time is set to a
full year (8,760 hours). For each variant the steady-state proxy of physics_check.py is computed on the same geometry:
HLC = sum(U x A) + y x envelope + 0.33 x n x V, Q = HLC x HDD x 24 / 1000 per m2 (only the exposed envelope:
elements adjacent to other dwellings are left out, as the proxy does), with the y value and air changes
of the proxy's rules (n from air permeability by the n50/20 rule of thumb). Running HEM on the variants (run_hem.sh)
gives the annual space heating demand to compare with Q (rank correlation; per-variant ratio).
Outputs in --out: variant_<id>.json (HEM inputs) and variants.csv (parameters and proxy Q).
"""
import argparse, copy, itertools, json, pathlib
import pandas as pd

WALL = {"solid": 2.1, "cavity_unfilled": 1.5, "insulated": 0.45}
ROOF = {"none": 2.3, "100mm": 0.4, "270mm": 0.16}
WINDOW = {"single": 4.8, "double_old": 2.8, "double_new": 1.4}
AIR = {"leaky": 15.0, "typical": 10.0, "tight": 5.0}          # air permeability m3/(h m2) at 50 Pa
RSI_RSE = {90: 0.17, 0: 0.14}                                  # surface resistances (walls and windows, roof)
HDD_LONDON = 2000.0                                            # base 15.5 C, order of magnitude for the proxy only
Y = 0.15                                                       # thermal bridging of the proxy before 2003


def r_construction(u, pitch):
    return max(1.0 / u - RSI_RSE.get(pitch, 0.17), 0.01)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--full-year", action="store_true", help="set 8,760 hourly steps (only if the base has full-year schedules)")
    a = ap.parse_args()
    base = json.load(open(a.demo, encoding="utf8"))
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    if a.full_year:
        base["SimulationTime"] = {"start": 0, "end": 8760, "step": 1}
    zones = list(base["Zone"].values())
    floor, volume = sum(z["area"] for z in zones), sum(z["volume"] for z in zones)
    has_roof = any(el["type"] == "BuildingElementOpaque" and el["pitch"] == 0 for z in zones for el in z["BuildingElement"].values())
    roofs = ROOF if has_roof else {"n/a": None}
    rows = []
    for i, ((wk, uw), (rk, ur), (gk, ug), (ak, ap50)) in enumerate(itertools.product(WALL.items(), roofs.items(), WINDOW.items(), AIR.items())):
        d = copy.deepcopy(base)
        ua, env = 0.0, 0.0
        for name, el in ((n, e) for z in d["Zone"].values() for n, e in z["BuildingElement"].items()):
            t = el["type"]
            if t == "BuildingElementOpaque":
                u = ur if el["pitch"] == 0 else uw
                el["thermal_resistance_construction"] = round(r_construction(u, el["pitch"]), 4)
                area = el.get("area") or el["height"] * el["width"]
                ua += u * area; env += area
            elif t == "BuildingElementTransparent":
                el["thermal_resistance_construction"] = round(r_construction(ug, 90), 4)
                area = el.get("area") or el["height"] * el["width"]
                ua += ug * area; env += area
            elif t == "BuildingElementGround":
                ua += el["u_value"] * el["area"]; env += el["area"]
        leaks = d["InfiltrationVentilation"].get("Leaks", {})
        if "test_result" in leaks:
            leaks["test_result"] = ap50
        n = ap50 * env / volume / 20.0                         # n50/20 rule of thumb, air changes per hour
        hlc = ua + Y * env + 0.33 * n * volume
        q = hlc * HDD_LONDON * 24 / 1000 / floor
        vid = f"{i:02d}"
        json.dump(d, open(out / f"variant_{vid}.json", "w", encoding="utf8"), indent=1)
        rows.append({"variant": vid, "wall": wk, "roof": rk, "window": gk, "air": ak, "u_wall": uw, "u_roof": ur,
                     "u_window": ug, "air_permeability": ap50, "hlc_proxy": round(hlc, 1), "q_proxy_kwh_m2": round(q, 1)})
    pd.DataFrame(rows).to_csv(out / "variants.csv", index=False)
    print(f"{len(rows)} variants written to {out}; leaks keys in demo: {list(base['InfiltrationVentilation'].get('Leaks', {}).keys())}")


if __name__ == "__main__":
    main()
