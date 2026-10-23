"""Building Energy Ratings (BER, Republic of Ireland) for the Dublin region: the Irish counterpart of the EPC.

    python ber_dublin.py

Input: data/dublin/ber/raw/BERPublicSearch.zip (SEAI BER Research Tool, full download, kept unchanged; anonymised:
no address, MPRN or Eircode). Location is the county or Dublin postal district ("Dublin 6", "Co. Dublin") and, where
SEAI has assigned it, the CSO Small Area (SA_Code) with SEAI's probability that this assignment is wrong.

The BER scale differs from the EPC: the rating is primary energy per m² and year (kWh/m²/yr, BerRating; lower is
better), banded A1 ... G; the EPC is the SAP cost score (higher is better), banded A ... G. Compare within each
system (ranks, bands), not their values.

Outputs:
  data/dublin/ber/ber_ireland.parquet     all certificates, selected columns, typed (one row per certificate)
  data/dublin/ber/ber_dublin.parquet      the four Dublin councils (postal districts and Co. Dublin)
  data/dublin/ber/ber_dublin_sa.parquet   Dublin certificates per Small Area: n, median BerRating, share of D-G,
                                          share of heat pumps (only certificates with a Small Area)
  data/dublin/ber/ber_summary.csv         counts, coverage of SA_Code, dates
"""
import io, pathlib, sys, zipfile
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

PHD = pathlib.Path(__file__).resolve().parents[2]
D = PHD / "data" / "dublin" / "ber"
KEEP = ["CountyName", "DwellingTypeDescr", "Year_of_Construction", "TypeofRating", "EnergyRating", "BerRating",
        "GroundFloorArea(sq m)", "UValueWall", "UValueRoof", "UValueFloor", "UValueWindow", "WallArea", "RoofArea",
        "FloorArea", "WindowArea", "NoStoreys", "CO2Rating", "MainSpaceHeatingFuel", "MainWaterHeatingFuel",
        "HSMainSystemEfficiency", "StructureType", "PercentageDraughtStripped", "PermeabilityTestResult",
        "ThermalBridgingFactor", "PredominantRoofType", "PurposeOfRating", "DateOfAssessment", "FirstWallType_Description",
        "SA_Code", "prob_smarea_error_0corr", "prob_smarea_error_100corr", "HeatLossIndicator", "SolarPVEnergyOutput"]
NUM = ["Year_of_Construction", "BerRating", "GroundFloorArea(sq m)", "UValueWall", "UValueRoof", "UValueFloor",
       "UValueWindow", "WallArea", "RoofArea", "FloorArea", "WindowArea", "NoStoreys", "CO2Rating",
       "HSMainSystemEfficiency", "PercentageDraughtStripped", "PermeabilityTestResult", "ThermalBridgingFactor",
       "prob_smarea_error_0corr", "prob_smarea_error_100corr", "HeatLossIndicator", "SolarPVEnergyOutput"]


def load():
    with zipfile.ZipFile(D / "raw" / "BERPublicSearch.zip") as z:
        with z.open("BERPublicsearch.txt") as f:
            df = pd.read_csv(io.TextIOWrapper(f, encoding="latin-1"), sep="\t", usecols=lambda c: c in KEEP,
                             dtype=str, quoting=3, on_bad_lines="warn")
    df.columns = [c.replace("(sq m)", "_m2") for c in df.columns]
    for c in df.columns:
        df[c] = df[c].str.strip().replace("", np.nan)
    for c in NUM:
        c = c.replace("(sq m)", "_m2")
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["DateOfAssessment"] = pd.to_datetime(df["DateOfAssessment"], format="%b %d %Y %I:%M%p", errors="coerce")
    df["year"] = df["DateOfAssessment"].dt.year
    df["heat_pump"] = df["MainSpaceHeatingFuel"].str.contains("Electricity", na=False) & (df["HSMainSystemEfficiency"] > 150)
    return df


def main():
    df = load()
    df.to_parquet(keep(D / "ber_ireland.parquet"), index=False)
    dub = df[df["CountyName"].str.match(r"^(Dublin \d|Dublin 6W|Co\. Dublin)", na=False)].copy()
    dub.to_parquet(keep(D / "ber_dublin.parquet"), index=False)
    sa = dub[dub["SA_Code"].notna()]
    g = sa.groupby("SA_Code").agg(n=("BerRating", "size"), ber_median=("BerRating", "median"),
                                  share_dg=("EnergyRating", lambda s: s.str[0].isin(list("DEFG")).mean()),
                                  heat_pump_share=("heat_pump", "mean")).reset_index()
    g.to_parquet(keep(D / "ber_dublin_sa.parquet"), index=False)
    s = pd.Series({"certificates_ireland": len(df), "certificates_dublin": len(dub),
                   "dublin_with_sa_code": int(dub["SA_Code"].notna().sum()),
                   "dublin_sa_code_share": round(dub["SA_Code"].notna().mean(), 4),
                   "dublin_small_areas": len(g), "median_certs_per_sa": float(g["n"].median()) if len(g) else None,
                   "first_assessment": str(dub["DateOfAssessment"].min()), "last_assessment": str(dub["DateOfAssessment"].max()),
                   "dublin_heat_pump_share": round(dub["heat_pump"].mean(), 4)})
    s.to_csv(keep(D / "ber_summary.csv"), header=["value"])
    print(s.to_string())
    print(dub["CountyName"].value_counts().head(30).to_string())
    print(dub.groupby("year").size().tail(8).to_string())


if __name__ == "__main__":
    main()
