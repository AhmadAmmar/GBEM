"""Step 1 - certificate table per study area: every domestic EPC with a property location, cleaned, with flags.

    python certificates.py [--areas london belfast]

Sources (snapshots, recorded in the output log):
  London   England and Wales domestic EPC register with UPRN and coordinates (merged_certificates_with_latlon.csv,
           downloaded January 2025): certificates of the 33 London local authorities (codes E09...). Coordinates are
           the OS Open UPRN locations of the certificates' UPRNs (checked 21 Oct 2026: 99.2% within 1 m).
  Belfast  Northern Ireland domestic EPC register to January 2025 with Irish Grid coordinates from the UPRN
           (NI_Domestic_Master_to_01_2025_with_XY_v2.csv); certificates inside the Greater Belfast extent.
           Certificates before 2020 have no UPRN and therefore no location.

Rules (nothing is dropped silently; every rule is counted in the log):
  dropped   repeated certificate id (identical copies); rating not in A-G; no location; inspection date missing or before 2007; location outside the area
  kept with flags:
    year             year of the inspection date (the date the dwelling was assessed; used to match imagery years)
    new_dwelling     transaction type "new dwelling" (rated with full SAP, existing dwellings with RdSAP)
    uprn_source      how the UPRN was matched (England and Wales register: Address Matched / Energy Assessor)
    n_certs_uprn     certificates of the same UPRN; cert_order 1 = most recent; is_latest
    certs_same_day   more than one certificate of the UPRN on the same inspection date (possible duplicates)
  The choice between all certificates, the latest per property, or the one nearest an imagery year is made when
  the modelling sets are drawn, not here.
Output: data/<area>/epc/certificates.parquet and certificates_log.json
"""
import argparse, datetime, json, pathlib
import duckdb
import numpy as np
import pandas as pd
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

PHD = pathlib.Path(__file__).resolve().parents[2]
DATA = PHD / "data"
EW = DATA / "merged_certificates_with_latlon.csv"
NI = DATA / "belfast/belfast-epc/NI_Domestic_Master_to_01_2025_with_XY_v2.csv"
BELFAST_EXTENT = (315000, 357000, 351000, 390000)       # Greater Belfast, Irish Grid (as code/gee/spec.py)
RATINGS = list("ABCDEFG")


def flags(d, log):
    n0 = len(d)
    d = d.drop_duplicates("cert_id")       # the same certificate twice (NI file: 1,298 certificates, identical copies)
    log["dropped_repeated_certificate_id"] = n0 - len(d)
    n0 = len(d)
    d = d.assign(CURRENT_ENERGY_RATING=d["CURRENT_ENERGY_RATING"].str.strip().str.upper())   # NI register uses lower case
    d = d[d["CURRENT_ENERGY_RATING"].isin(RATINGS)]; log["dropped_rating_not_A_to_G"] = n0 - len(d)
    n0 = len(d)
    d = d[d["inspection_date"].notna() & (d["inspection_date"].dt.year >= 2007)]; log["dropped_date_missing_or_before_2007"] = n0 - len(d)
    d = d.copy()
    d["year"] = d["inspection_date"].dt.year.astype("int16")
    d["new_dwelling"] = d["TRANSACTION_TYPE"].str.lower().str.strip().eq("new dwelling")
    d = d.sort_values(["UPRN", "inspection_date", "cert_id"])
    g = d.groupby("UPRN")
    d["n_certs_uprn"] = g["cert_id"].transform("size").astype("int16")
    d["cert_order"] = (g.cumcount(ascending=False) + 1).astype("int16")
    d["is_latest"] = d["cert_order"].eq(1)
    d["certs_same_day"] = d.duplicated(["UPRN", "inspection_date"], keep=False)
    d["sap_score"] = pd.to_numeric(d["CURRENT_ENERGY_EFFICIENCY"], errors="coerce")
    log.update({"n_certificates": len(d), "n_uprns": int(d["UPRN"].nunique()),
                "by_year": d["year"].value_counts().sort_index().to_dict(),
                "by_rating": d["CURRENT_ENERGY_RATING"].value_counts().sort_index().to_dict(),
                "new_dwelling": int(d["new_dwelling"].sum()), "certs_same_day": int(d["certs_same_day"].sum()),
                "uprn_source": {str(k): int(v) for k, v in d["uprn_source"].value_counts(dropna=False).items()}})
    log["by_year"] = {int(k): int(v) for k, v in log["by_year"].items()}
    log["by_rating"] = {str(k): int(v) for k, v in log["by_rating"].items()}
    return d, log


def london():
    # stream the London rows of the 25 GB register to a staging file (constant memory), then read it with
    # Arrow-backed strings: loading all 94 text columns as Python objects needs more than 20 GB
    stage = DATA / "london" / "epc" / "_stage_ew_london.parquet"
    stage.parent.mkdir(parents=True, exist_ok=True)
    if not stage.exists():
        con = duckdb.connect()
        con.execute("SET preserve_insertion_order = false")
        # standard CSV quoting (doubled quotes); rows that still do not parse are stored and counted, not dropped silently
        con.execute(f"""COPY (SELECT * FROM read_csv('{EW.as_posix()}', all_varchar=true, header=true, quote='"', escape='"',
                                                     store_rejects=true)
                        WHERE LOCAL_AUTHORITY LIKE 'E09%') TO '{stage.as_posix()}' (FORMAT parquet)""")
        rej = con.execute("SELECT count(*) FROM reject_errors").fetchone()[0]
        keep((stage.parent / "_stage_rejected_rows.txt")).write_text(f"rows of the register that could not be parsed: {rej}\n", encoding="utf-8")
    d = pd.read_parquet(stage, dtype_backend="pyarrow")
    log = {"source": EW.name, "snapshot": "England and Wales register, downloaded January 2025", "rows_in_source_area": len(d)}
    n0 = len(d)
    d = d[d["UPRN"].notna() & d["LATITUDE"].notna() & d["LONGITUDE"].notna()]; log["dropped_no_location"] = n0 - len(d)
    d["UPRN"] = d["UPRN"].str.replace(r"\.0$", "", regex=True)
    d["cert_id"] = d["LMK_KEY"]
    d["inspection_date"] = pd.to_datetime(d["INSPECTION_DATE"], errors="coerce")
    d["uprn_source"] = d["UPRN_SOURCE"]
    pts = pd.DataFrame({"lon": d["LONGITUDE"].astype(float), "lat": d["LATITUDE"].astype(float)})
    import geopandas as gpd
    g = gpd.GeoSeries(gpd.points_from_xy(pts.lon, pts.lat), crs=4326).to_crs(27700)
    d["x"], d["y"] = g.x.values, g.y.values
    return flags(d, log)


def belfast():
    d = pd.read_csv(NI, dtype=str, encoding="latin1", low_memory=False)
    log = {"source": NI.name, "snapshot": "Northern Ireland register to January 2025, coordinates from UPRN", "rows_in_source": len(d)}
    n0 = len(d)
    d = d[d["UPRN_key"].notna() & d["X_COR"].notna() & d["Y_COR"].notna()]; log["dropped_no_location"] = n0 - len(d)
    d["x"], d["y"] = d["X_COR"].astype(float), d["Y_COR"].astype(float)
    x0, y0, x1, y1 = BELFAST_EXTENT
    n0 = len(d)
    d = d[(d.x >= x0) & (d.x < x1) & (d.y >= y0) & (d.y < y1)]; log["dropped_outside_area"] = n0 - len(d)
    d["UPRN"] = d["UPRN_key"]
    d["cert_id"] = d["ASSESSMENT_ID"]
    d["inspection_date"] = pd.to_datetime(d["INSPECTION_DATE"], errors="coerce", dayfirst=True)
    d["uprn_source"] = d["xy_source"]
    return flags(d, log)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--areas", nargs="+", default=["london", "belfast"])
    for area in ap.parse_args().areas:
        d, log = london() if area == "london" else belfast()
        out = DATA / area / "epc"; out.mkdir(parents=True, exist_ok=True)
        log["run"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        d.to_parquet(keep(out / "certificates.parquet"), index=False)
        keep((out / "certificates_log.json")).write_text(json.dumps(log, indent=1, default=int), encoding="utf-8")
        print(json.dumps({k: v for k, v in log.items() if k not in ("by_year",)}, indent=1, default=int))
        print(f"{area}: {len(d):,} certificates written to {out / 'certificates.parquet'}")


if __name__ == "__main__":
    main()
