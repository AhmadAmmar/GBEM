"""Building envelope geometry for heat loss, for every footprint (no certificate needed).

    python physics.py --area belfast|london

A steady-state heat balance makes the fabric heat loss of a building proportional to the area of each exposed element
times its U-value (W/m2K). Geometry is what Earth observation and building data can provide everywhere; U-values
need construction or age (physics_check.py). Inputs: footprints (area A, perimeter P), shared (party) wall length S
(morphology.py), height H (LiDAR median height where it covers at least half of the footprint, else footprint data,
else floors x 3 m), addresses per footprint (dwellings.py).

Per building (prefix phys_):
  storeys         round(H / 2.8 m storey height), at least 1
  floor_m2        gross floor area A x storeys (the heated floor area is about 85-90% of this)
  wall_ext_m2     exposed wall area (P - S) x H (party walls lose little heat: neighbour heated to similar temperature)
  wall_party_m2   party wall area S x H
  roof_m2         A (heat loss through the top ceiling or roof plane; pitch does not change the heat-loss area of
                  an insulated ceiling much, so the plan area is used)
  ground_m2       A
  envelope_m2     wall_ext + roof + ground (heat-loss area)
  volume_m3       A x H
  hlff            heat-loss form factor = envelope / floor (m2 of heat-loss area per m2 of floor; detached bungalow
                  about 3, mid-terrace house 1.5-2, flats in large blocks below 1)
  sv              surface-to-volume ratio = envelope / volume (1/m)
  exposed_share   wall_ext / (wall_ext + wall_party): share of the perimeter that is exposed
  floor_per_dw_m2, envelope_per_dw_m2   per address (dwellings in the footprint)
Output: data/<area>/epc/physics_fp.parquet (fp_id, phys_*). assemble.py adds them as the feature group "physics".
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"
STOREY_M = 2.8


def geometry(area_m2, perim_m, shared_m, height_m, n_dw):
    A, P = np.asarray(area_m2, float), np.asarray(perim_m, float)
    S = np.clip(np.nan_to_num(np.asarray(shared_m, float)), 0, P)
    H = np.asarray(height_m, float)
    n = np.clip(np.nan_to_num(np.asarray(n_dw, float), nan=1), 1, None)
    storeys = np.clip(np.round(H / STOREY_M), 1, None)
    out = {"storeys": storeys, "floor_m2": A * storeys, "wall_ext_m2": (P - S) * H, "wall_party_m2": S * H,
           "roof_m2": A, "ground_m2": A, "volume_m3": A * H}
    out["envelope_m2"] = out["wall_ext_m2"] + out["roof_m2"] + out["ground_m2"]
    with np.errstate(all="ignore"):
        out["hlff"] = out["envelope_m2"] / out["floor_m2"]
        out["sv"] = out["envelope_m2"] / out["volume_m3"]
        out["exposed_share"] = out["wall_ext_m2"] / (out["wall_ext_m2"] + out["wall_party_m2"])
        out["floor_per_dw_m2"] = out["floor_m2"] / n
        out["envelope_per_dw_m2"] = out["envelope_m2"] / n
    return out


def building_height(area):
    e = DATA / area / "epc"
    m = pd.read_parquet(e / "morphology.parquet", columns=["fp_id", "area_m2", "perimeter_m", "shared_wall_m", "height_m", "num_floors"])
    m = m.merge(pd.read_parquet(e / "dwellings_fp.parquet", columns=["fp_id", "n_uprn"]), on="fp_id", how="left")
    lid = e / "lidar_fp.parquet"
    if lid.exists():
        m = m.merge(pd.read_parquet(lid, columns=["fp_id", "lidar_height_med_m", "lidar_valid_share"]), on="fp_id", how="left")
        h = m["lidar_height_med_m"].where(m["lidar_valid_share"] >= 0.5)
    else:
        h = pd.Series(np.nan, index=m.index)
    src = np.select([h.notna(), m["height_m"].notna(), m["num_floors"].notna()], ["lidar", "footprint data", "floors"], "none")
    m["H"] = h.fillna(m["height_m"]).fillna(m["num_floors"] * STOREY_M).clip(2.5, 300)
    m["H_source"] = src
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True)
    a = ap.parse_args()
    m = building_height(a.area)
    g = geometry(m["area_m2"], m["perimeter_m"], m["shared_wall_m"], m["H"], m["n_uprn"])
    out = pd.DataFrame({"fp_id": m["fp_id"], **{f"phys_{k}": np.asarray(v, "float32") for k, v in g.items()},
                        "phys_height_source": m["H_source"]})
    out = out[np.isfinite(out["phys_envelope_m2"])]
    dest = DATA / a.area / "epc/physics_fp.parquet"
    out.to_parquet(keep(dest), index=False)
    print(f"{a.area}: {len(out):,} footprints; heights from {out['phys_height_source'].value_counts(normalize=True).round(3).to_dict()}; "
          f"median heat-loss form factor {out['phys_hlff'].median():.2f}, exposed share {out['phys_exposed_share'].median():.2f} -> {dest}")


if __name__ == "__main__":
    main()
