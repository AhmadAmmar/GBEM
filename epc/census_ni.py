"""Census 2021 context for Greater Belfast certificates: ward shares of heating, renewables, accommodation and tenure.

    python census_ni.py

Sources (NISRA Census 2021 main statistics, ward sheets; OSNI ward boundaries 2012, as used by the census):
  MS-E06 accommodation type (households)   share detached, semi-detached, terraced, purpose-built flat
  MS-E11 central heating (household based) share oil only, mains gas only, electric only, solid fuel only, renewable only,
                                           two or more types, no central heating
  MS-E13 renewable energy systems          share solar PV, solar water heating, air source, any renewable
  MS-E15 tenure (households)               share owner occupied, social rented, private rented
Shares are of all households in the ward. Each certificate takes the values of the ward its UPRN point lies in
(area context, not properties of the dwelling).
Output: data/belfast/epc/census_ward.parquet (one row per ward) and census_cert.parquet (cert_id, ward code, shares)
"""
import pathlib
import numpy as np
import pandas as pd
import geopandas as gpd
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

PHD = pathlib.Path(__file__).resolve().parents[2]
DATA = PHD / "data"
CEN = DATA / "belfast/census2021_nisra"
WARDS = DATA / "belfast/boundaries_osni/osni_open_data_largescale_boundaries_wards_2012.zip"
TABLES = {   # table: {output name: start of the census column header}
    "e06": {"detached": "Whole house or bungalow:\n Detached", "semi": "Whole house or bungalow: \nSemi-detached",
            "terraced": "Whole house or bungalow: \nTerraced", "flat_purpose_built": "Flat, maisonette or apartment: \nPurpose-built"},
    "e11": {"heat_oil": "Oil only", "heat_gas": "Mains gas only", "heat_electric": "Electric", "heat_solid": "Solid fuel",
            "heat_renewable": "Renewable heating system only", "heat_two_or_more": "Two or more types", "heat_none": "No central heating"},
    "e13": {"ren_solar_pv": "Solar panels for electricity", "ren_solar_water": "Solar panels for heating water",
            "ren_air_source": "Air source", "ren_any": "Any renewable energy system"},
    "e15": {"owner": "Owner occupied", "social_rented": "Social rented", "private_rented": "Private rented"},
}


def ward_sheet(t):
    x = pd.read_excel(CEN / f"census-2021-ms-{t}.xlsx", sheet_name="Ward", header=None)
    hdr = next(i for i in range(15) if x.iloc[i].astype(str).str.contains("Code", case=False).any())
    x.columns = [str(c) for c in x.iloc[hdr]]
    x = x.iloc[hdr + 1:].dropna(subset=["Geography code"])
    x = x.set_index("Geography code")
    # each ward appears twice: counts first, then percentages; the counts are used
    x = x[x.index.astype(str).str.match(r"^N\d{8}$")]          # ward and NI codes only (drops repeated header rows)
    return x[~x.index.duplicated(keep="first")]


def main():
    out = None
    for t, cols in TABLES.items():
        x = ward_sheet(t)
        total = pd.to_numeric(x["All households"], errors="coerce")
        part = {}
        for name, start in cols.items():
            match = [c for c in x.columns if c.startswith(start)]
            assert match, f"{t}: no column starting with {start!r}"
            v = sum(pd.to_numeric(x[c], errors="coerce") for c in match)     # several columns (e.g. tenure groups) are summed
            part[f"census_{name}_share"] = (v / total).round(4)
        df = pd.DataFrame(part)
        out = df if out is None else out.join(df, how="outer")
    out.index.name = "ward_code"
    out = out.reset_index()
    d = DATA / "belfast" / "epc"
    out.to_parquet(keep(d / "census_ward.parquet"), index=False)

    w = gpd.read_file(f"zip://{WARDS.as_posix()}").to_crs(29902)[["WardCode", "geometry"]]
    c = pd.read_parquet(d / "certificates_linked.parquet", columns=["cert_id", "x", "y"])
    P = gpd.GeoDataFrame(c, geometry=gpd.points_from_xy(c.x, c.y), crs=29902)
    j = gpd.sjoin(P, w, how="left", predicate="within").drop_duplicates("cert_id")
    res = j[["cert_id", "WardCode"]].rename(columns={"WardCode": "census_ward_code"}).merge(
        out.rename(columns={"ward_code": "census_ward_code"}), on="census_ward_code", how="left")
    res.to_parquet(keep(d / "census_cert.parquet"), index=False)
    print(f"wards {len(out)}, certificates {len(res):,}, without ward {int(res.census_ward_code.isna().sum())}")
    print(out.describe().T[["mean", "min", "max"]].round(3).to_string())


if __name__ == "__main__":
    main()
