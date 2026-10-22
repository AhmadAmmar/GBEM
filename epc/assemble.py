"""Step 5 - modelling table per area and imagery year: certificate, morphology and satellite features in one row.

    python assemble.py [--areas london belfast] [--years 2020 2021 2024]

One row per certificate inspected in the year (code/gee/extract.py --certificates). Columns:
  label_rating, label_sap        A-G band and SAP score
  id_cert, id_uprn, id_fp        identifiers; group cross-validation folds by id_uprn and id_fp
  flag_*                         new_dwelling, is_latest, n_certs_uprn, certs_same_day, uprn_source, link_method
  epc_*                          attributes recorded on the certificate itself (property type, built form, floor area,
                                 age band, ...). They are kept so that models with and without them can be compared;
                                 they are not remote-sensing predictors.
  morph_*                        footprint morphology and streets (code/epc/morphology.py)
  s2_, s1_, landsat_, modis_, era5_, viirs_, ghsl_, lc_, terrain_, worldcover_   satellite and climate features
Also written: data_dictionary.csv (column, group, source) for feature-group ablations.
Output: data/<area>/model/dataset_<year>.parquet
"""
import argparse, json, pathlib
import pandas as pd
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

PHD = pathlib.Path(__file__).resolve().parents[2]
DATA = PHD / "data"
EPC_ATTR = ["PROPERTY_TYPE", "BUILT_FORM", "TOTAL_FLOOR_AREA", "CONSTRUCTION_AGE_BAND", "TENURE", "MAIN_FUEL",
            "MAINS_GAS_FLAG", "FLOOR_LEVEL", "FLAT_TOP_STOREY", "FLAT_STOREY_COUNT", "NUMBER_HABITABLE_ROOMS",
            "EXTENSION_COUNT", "TRANSACTION_TYPE"]
GROUPS = {"s2_": "sentinel2", "s1_": "sentinel1", "landsat_": "thermal_landsat", "modis_": "thermal_modis",
          "landsatmulti_": "thermal_multiyear", "modismulti_": "thermal_multiyear",
          "era5_": "climate", "viirs_": "night_lights", "ghsl_": "built_volume_ghsl", "lc_": "landcover",
          "terrain_": "terrain", "worldcover_": "landcover", "morph_": "morphology", "epc_": "certificate_attributes",
          "label_": "label", "id_": "identifier", "flag_": "flag", "census_": "census_context", "lidar_": "lidar"}
STREET = {"road_dist_m", "major_road_dist_m", "road_density_250"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--areas", nargs="+", default=["london", "belfast"]); ap.add_argument("--years", nargs="+", type=int)
    a = ap.parse_args()
    for area in a.areas:
        e = DATA / area / "epc"
        cert = pd.read_parquet(e / "certificates_linked.parquet")
        morph = pd.read_parquet(e / "morphology.parquet").merge(pd.read_parquet(e / "dwellings_fp.parquet"), on="fp_id", how="left")
        morph = morph.rename(columns={c: f"morph_{c}" for c in morph.columns if c != "fp_id"})
        pos = pd.read_parquet(e / "dwellings_cert.parquet").rename(columns={"cert_id": "id_cert", "pos_in_block": "morph_pos_in_block"})
        pos["id_cert"] = pos["id_cert"].astype(str)
        fdir = DATA / area / "gee_v2" / "features"
        years = a.years or sorted(int(p.stem.split("_")[1]) for p in fdir.glob("certs_[0-9][0-9][0-9][0-9].parquet"))
        out_dir = DATA / area / "model"; out_dir.mkdir(parents=True, exist_ok=True)
        for y in years:
            f = pd.read_parquet(fdir / f"certs_{y}.parquet").drop(columns=["year", "UPRN", "fp_id", "link_method"], errors="ignore")
            c = cert[cert["year"] == y]
            base = pd.DataFrame({
                "id_cert": c["cert_id"].astype(str).values, "id_uprn": c["UPRN"].values, "id_fp": c["fp_id"].values,
                "label_rating": c["CURRENT_ENERGY_RATING"].values, "label_sap": c["sap_score"].values,
                "year": y, "inspection_date": c["inspection_date"].values,
                **{f"flag_{k}": c[k].values for k in ("new_dwelling", "is_latest", "n_certs_uprn", "certs_same_day",
                                                       "uprn_source", "link_method", "link_dist_m")},
                **{f"epc_{k.lower()}": c[k].values for k in EPC_ATTR if k in c}})
            df = base.merge(f.rename(columns={"rec_id": "id_cert"}), on="id_cert", how="left")
            df = df.merge(morph, left_on="id_fp", right_on="fp_id", how="left").drop(columns=["fp_id"])
            df = df.merge(pos.drop_duplicates("id_cert"), on="id_cert", how="left")
            lid = e / "lidar_fp.parquet"                             # LiDAR building height and roof form (Belfast; lidar_ni.py)
            if lid.exists():
                df = df.merge(pd.read_parquet(lid), left_on="id_fp", right_on="fp_id", how="left").drop(columns=["fp_id"])
            cen = e / "census_cert.parquet"                          # Census 2021 ward context (Belfast; census_ni.py)
            if cen.exists():
                cc = pd.read_parquet(cen).rename(columns={"cert_id": "id_cert"})
                cc["id_cert"] = cc["id_cert"].astype(str)
                df = df.merge(cc.drop_duplicates("id_cert"), on="id_cert", how="left")
            df.to_parquet(keep(out_dir / f"dataset_{y}.parquet"), index=False)
            print(f"{area} {y}: {len(df):,} certificates x {df.shape[1]} columns -> {out_dir / f'dataset_{y}.parquet'}")
        cols = df.columns
        dd = pd.DataFrame({"column": cols})
        dd["group"] = [("streets" if c.replace("morph_", "") in STREET else next((g for p, g in GROUPS.items() if c.startswith(p)), "meta"))
                       for c in cols]
        dd.to_csv(keep(out_dir / "data_dictionary.csv"), index=False)
        print(dd["group"].value_counts().to_dict())


if __name__ == "__main__":
    main()
