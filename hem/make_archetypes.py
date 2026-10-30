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
FLOOR = {"uninsulated": (0.7, 0.2), "insulated": (0.25, 2.5)}  # ground floor: overall U, construction R
# built forms derived from a single-storey flat base: which party surfaces become exposed; exposed floor perimeter
# (m) for a plan of about 5.5 x 5.5 m
FORMS = {"flat_mid": set(), "flat_top": {"roof"}, "flat_ground": {"ground"}, "bungalow_terrace": {"roof", "ground"},
         "bungalow_semi": {"roof", "ground", "wall_bau"}, "bungalow_detached": {"roof", "ground", "wall_bau", "wall_other"}}
PERIM = {"flat_ground": 11.0, "bungalow_terrace": 11.0, "bungalow_semi": 16.5, "bungalow_detached": 22.0}
ROOF_EL = {"type": "BuildingElementOpaque", "solar_absorption_coeff": 0.7, "thermal_resistance_construction": 1.0,
           "areal_heat_capacity": 19000, "mass_distribution_class": "I", "pitch": 0, "orientation360": 0,
           "base_height": 3, "width": 1, "is_unheated_pitched_roof": False}
WALL_EL = {"type": "BuildingElementOpaque", "solar_absorption_coeff": 0.7, "thermal_resistance_construction": 1.0,
           "areal_heat_capacity": 51000, "mass_distribution_class": "I", "pitch": 90, "orientation360": 270,
           "base_height": 0, "width": 1}


def make_form(base, form):
    """Expose the party surfaces of the form: ceilings become a flat roof, floors a ground floor (slab), party walls
    external walls facing west. U values are set per variant afterwards."""
    expose = FORMS[form]
    total = sum(z["area"] for z in base["Zone"].values())
    for z in base["Zone"].values():
        for n, el in z["BuildingElement"].items():
            if el["type"] != "BuildingElementAdjacentConditionedSpace":
                continue
            ar = el["area"]
            if el["pitch"] == 0 and "roof" in expose:
                el.clear(); el.update(ROOF_EL, area=ar, height=ar)
            elif el["pitch"] == 180 and "ground" in expose:
                el.clear(); el.update({"type": "BuildingElementGround", "total_area": total, "area": ar, "pitch": 180,
                                       "u_value": 0.7, "thermal_resistance_floor_construction": 0.2,
                                       "areal_heat_capacity": 112000, "mass_distribution_class": "I",
                                       "floor_type": "Slab_no_edge_insulation", "thickness_walls": 0.3,
                                       "perimeter": PERIM[form], "psi_wall_floor_junc": 0.0})
            elif el["pitch"] == 90 and "party wall" in n.lower() and                     (("wall_bau" in expose and "BAU" in n) or ("wall_other" in expose and "BAU" not in n)):
                el.clear(); el.update(WALL_EL, area=ar, height=ar)
    return base


def r_construction(u, pitch):
    return max(1.0 / u - RSI_RSE.get(pitch, 0.17), 0.01)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--full-year", action="store_true", help="simulate 8,760 hours, keeping the base's time step (only if the base has full-year schedules)")
    ap.add_argument("--top-floor", action="store_true", help="same as --form flat_top")
    ap.add_argument("--form", choices=list(FORMS), default="flat_mid", help="built form derived from the flat base")
    a = ap.parse_args()
    base = json.load(open(a.demo, encoding="utf8"))
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    if a.full_year:
        base["SimulationTime"]["start"], base["SimulationTime"]["end"] = 0, 8760
    form = "flat_top" if a.top_floor else a.form
    base = make_form(base, form)
    zones = list(base["Zone"].values())
    floor, volume = sum(z["area"] for z in zones), sum(z["volume"] for z in zones)
    has_roof = any(el["type"] == "BuildingElementOpaque" and el["pitch"] == 0 for z in zones for el in z["BuildingElement"].values())
    roofs = ROOF if has_roof else {"n/a": None}
    has_ground = any(el["type"] == "BuildingElementGround" for z in zones for el in z["BuildingElement"].values())
    floors = FLOOR if has_ground else {"n/a": (None, None)}
    rows = []
    for i, ((wk, uw), (rk, ur), (gk, ug), (ak, ap50), (fk, (uf, rf))) in enumerate(
            itertools.product(WALL.items(), roofs.items(), WINDOW.items(), AIR.items(), floors.items())):
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
                if uf is not None:
                    el["u_value"], el["thermal_resistance_floor_construction"] = uf, rf
                ua += el["u_value"] * el["area"]; env += el["area"]
        leaks = d["InfiltrationVentilation"].get("Leaks", {})
        if "test_result" in leaks:
            leaks["test_result"] = ap50
        # n50/20 rule of thumb, air changes per hour; air permeability is per m2 of the whole envelope (HEM env_area,
        # party walls and floors included), not only the exposed part used for heat loss
        n = ap50 * leaks.get("env_area", env) / volume / 20.0
        hlc = ua + Y * env + 0.33 * n * volume
        q = hlc * HDD_LONDON * 24 / 1000 / floor
        vid = f"{i:03d}"
        json.dump(d, open(out / f"variant_{vid}.json", "w", encoding="utf8"), indent=1)
        rows.append({"variant": vid, "form": form, "wall": wk, "roof": rk, "window": gk, "air": ak, "floor": fk, "u_floor": uf, "u_wall": uw, "u_roof": ur,
                     "u_window": ug, "air_permeability": ap50, "hlc_proxy": round(hlc, 1), "q_proxy_kwh_m2": round(q, 1)})
    pd.DataFrame(rows).to_csv(out / "variants.csv", index=False)
    print(f"{len(rows)} variants written to {out}; leaks keys in demo: {list(base['InfiltrationVentilation'].get('Leaks', {}).keys())}")


if __name__ == "__main__":
    main()
