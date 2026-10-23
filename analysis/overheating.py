"""Summer overheating exposure of the housing stock, and its relation to winter heat loss (exploratory index).

    python overheating.py --area belfast|london [--years 2020 ... 2025]

No observed overheating label exists for these homes, so this is an exposure index built from factors that the
literature on dwelling overheating associates with risk, each as a percentile rank (0-1, higher = more exposed),
averaged with equal weights:
  surface heat     multi-year (2020-2025) summer land surface temperature at the footprint (Landsat)
  roof exposure    top-floor flat 1.0, house or bungalow 0.7 (own roof), middle floor 0.3, ground floor 0.2
  small dwelling   small floor area per dwelling (footprint floor area / addresses), inverted
  little greenery  low summer NDVI within 100 m (Sentinel-2), inverted
  flat roof        share of flat roof (LiDAR)
Weights and factors are assumptions to be tested if a label becomes available (e.g. indoor temperature studies).
Winter-summer trade-off: Spearman correlation between the index and the heat-loss parameter of the home
(analysis/heatpump_readiness.py), overall and by type; homes high on both (top quarter of each) are counted.
Outputs in data/<area>/analysis/: overheating_cert.parquet, overheating_summary.csv, overheating_units_cell.parquet
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy import stats
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "models"))
from safeio import keep                      # existing outputs are archived, never overwritten
import baseline as B

DATA = B.DATA
NEED = ["id_cert", "x", "y", "epc_property_type", "epc_floor_level", "epc_flat_top_storey", "morph_num_floors", "lidar_height_p90_m",
        "landsatmulti_LST_summer_fp", "morph_area_per_uprn_m2", "lidar_roof_flat_share"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--years", nargs="+", type=int, default=list(range(2020, 2026)))
    a = ap.parse_args()
    out = DATA / a.area / "analysis"
    frames = []
    for y in a.years:
        p = DATA / a.area / "model" / f"dataset_{y}.parquet"
        names = pq.ParquetFile(p).schema.names
        ndvi = next((c for c in names if c.startswith("s2_NDVI_summer_nb100") and not c.endswith("sd")), None)
        cols = [c for c in NEED if c in names] + ([ndvi] if ndvi else [])
        f = pd.read_parquet(p, columns=cols).rename(columns={ndvi: "ndvi_100"} if ndvi else {})
        frames.append(f)
    d = pd.concat(frames, ignore_index=True).drop_duplicates("id_cert")
    if "x" not in d:
        xy = pd.read_parquet(DATA / a.area / "epc/certificates_linked.parquet", columns=["cert_id", "x", "y"]).rename(columns={"cert_id": "id_cert"})
        xy["id_cert"] = xy["id_cert"].astype(str); d = d.merge(xy, on="id_cert", how="left")
    d = B.floor_features(d)
    roof = d["fl_pos"].map({"top": 1.0, "house": 0.7, "middle": 0.3, "ground": 0.2})
    f = pd.DataFrame({"surface_heat": d["landsatmulti_LST_summer_fp"].rank(pct=True),
                      "roof_exposure": roof,
                      "small_dwelling": 1 - pd.to_numeric(d["morph_area_per_uprn_m2"], errors="coerce").rank(pct=True),
                      "little_greenery": 1 - d["ndvi_100"].rank(pct=True) if "ndvi_100" in d else np.nan,
                      "flat_roof": pd.to_numeric(d["lidar_roof_flat_share"], errors="coerce").rank(pct=True)})
    d["overheating_index"] = f.mean(axis=1, skipna=True)
    d = pd.concat([d[["id_cert", "x", "y", "epc_property_type", "fl_pos", "overheating_index"]], f], axis=1)
    hp = pd.read_parquet(out / "hp_readiness_cert.parquet", columns=["cert_id", "hlp"]).rename(columns={"cert_id": "id_cert"})
    d = d.merge(hp, on="id_cert", how="left")
    d.to_parquet(keep(out / "overheating_cert.parquet"), index=False)
    rows = []
    for g, s in [("all", d)] + list(d.groupby("fl_pos")):
        s2 = s.dropna(subset=["overheating_index", "hlp"])
        if len(s2) < 100:
            continue
        both = (s2["overheating_index"] >= s2["overheating_index"].quantile(0.75)) & (s2["hlp"] >= s2["hlp"].quantile(0.75))
        rows.append({"group": g, "homes": len(s2), "index_median": s2["overheating_index"].median(),
                     "spearman_index_vs_heat_loss": stats.spearmanr(s2["overheating_index"], s2["hlp"])[0],
                     "share_high_both": both.mean()})
    summ = pd.DataFrame(rows)
    summ.round(4).to_csv(keep(out / "overheating_summary.csv"), index=False)
    print(summ.round(3).to_string(index=False))
    d["cell"] = (np.floor(d["x"] / 250).astype("Int64")).astype(str) + "_" + (np.floor(d["y"] / 250).astype("Int64")).astype(str)
    u = d.groupby("cell").agg(homes=("id_cert", "size"), overheating_index=("overheating_index", "mean"), hlp_median=("hlp", "median"))
    u[u["homes"] >= 5].round(4).reset_index().to_parquet(keep(out / "overheating_units_cell.parquet"), index=False)
    print(f"{a.area}: {len(d):,} certificates 2020-2025 with an index")


if __name__ == "__main__":
    main()
