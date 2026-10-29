"""The proposed Home Energy Model (HEM) EPC metrics, approximated for the current certified stock from EPC fields and
open geodata, and mapped.

    python hem_metrics.py --area london|belfast [--cell 500]

Why: from the second half of 2027 the EPC is to report four metrics instead of one band (DESNZ 2026, The Home Energy
Model: Energy Performance Certificates): fabric performance (Fabric Energy Efficiency, FEE: modelled heating and
cooling demand with a standard heating system), heating system (efficiency and emissions; no home whose primary space
or water heating uses fossil fuel can reach C), smart readiness and energy cost. No HEM certificates exist yet, and the
HEM simplified inputs for existing homes are not published, so these are proxies, defined to be replaced or calibrated
when the HEM engine is run on sample dwellings (plan section 9, step 2):
  fabric proxy     q_as_described_kwh_m2 from physics_check.py: steady-state space-heating demand per m2 from envelope
                   geometry (footprints, LiDAR) and the certificate's element descriptions, independent of the heating
                   system, as FEE is. Banded at the C/D boundary only: the consultation proposes close equivalence of
                   the C/D boundary with the current EER, so the proxy boundary q* is the median demand of homes rated
                   at the EER C/D boundary (SAP 68-70). Homes with q <= q* are "fabric C or better".
  heating rule     main fuel of the certificate: fossil (mains gas, LPG, oil, coal, solid fuel; not community) -> at
                   most D on the heating metric; electric (incl. heat pumps) -> eligible for C; community heat networks
                   and unknown fuel kept separate (the rule's treatment of networks is not yet set).
  smart readiness  indicators only (PV on the certificate, heat pump in the main heating description); the banding is
                   not yet defined.
Scope: the latest certificate of each property (the certified current stock), RdSAP and SAP alike.
Outputs in data/<area>/analysis/: hem_metrics_cert.parquet (per certificate), hem_metrics_summary.csv (stock shares),
hem_metrics_cells.parquet (per grid cell with at least 10 certificates).
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"
FOSSIL = r"mains gas|gas: mains|lpg|bottled gas|oil|coal|anthracite|smokeless|wood|dual fuel|solid fuel|peat"
# wood and dual fuel are biomass or mixed; kept out of the fossil class below, see fuel_class()


def fuel_class(fuel):
    f = fuel.astype(str).str.lower()
    network = f.str.contains("community") & ~f.str.contains("not community")
    cls = np.select(
        [network, f.str.contains("electric"), f.str.contains(r"wood|biomass|dual fuel"),
         f.str.contains(r"mains gas|gas: mains|lpg|bottled gas|oil|coal|anthracite|smokeless|solid fuel|peat")],
        ["heat network", "electric", "biomass or mixed", "fossil"], "unknown")
    return pd.Series(cls, index=fuel.index)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--cell", type=int, default=500)
    a = ap.parse_args()
    cols = ["cert_id", "x", "y", "is_latest", "MAIN_FUEL", "MAINHEAT_DESCRIPTION", "PHOTO_SUPPLY",
            "CURRENT_ENERGY_RATING", "sap_score", "PROPERTY_TYPE"]
    e = pd.read_parquet(DATA / a.area / "epc/certificates_linked.parquet", columns=cols)
    e["cert_id"] = e.cert_id.astype(str)
    e = e[e.is_latest.astype(bool) & e.x.notna()].copy()
    e["sap"] = pd.to_numeric(e.sap_score, errors="coerce")
    e["eer_c_or_better"] = e.CURRENT_ENERGY_RATING.astype(str).isin(list("ABC"))
    e["fuel_class"] = fuel_class(e.MAIN_FUEL)
    e["heat_pump"] = e.MAINHEAT_DESCRIPTION.astype(str).str.lower().str.contains("heat pump")
    e["pv"] = pd.to_numeric(e.PHOTO_SUPPLY, errors="coerce").fillna(0) > 0

    p = pd.read_parquet(DATA / a.area / "analysis/physics_cert.parquet", columns=["cert_id", "q_as_described_kwh_m2"]).astype({"cert_id": str}).drop_duplicates("cert_id")
    e = e.merge(p, on="cert_id", how="left")
    q = e.q_as_described_kwh_m2.where(e.q_as_described_kwh_m2.between(10, 1000))   # implausible geometry dropped
    qstar = q[e.sap.between(68, 70)].median()
    e["fabric_q"] = q
    e["fabric_c_or_better"] = np.where(q.notna(), q <= qstar, np.nan)
    e["heating_capped_below_c"] = e.fuel_class.eq("fossil")
    e["c_on_eer_but_heating_capped"] = e.eer_c_or_better & e.heating_capped_below_c

    n = len(e)
    share = lambda s: float(np.nanmean(s.astype(float)))
    summ = pd.DataFrame([
        ("certificates (latest per property)", n),
        ("fabric proxy C/D boundary q* (kWh/m2/yr)", round(qstar, 1)),
        ("share with fabric proxy available", share(e.fabric_q.notna())),
        ("EER C or better (current band)", share(e.eer_c_or_better)),
        ("fabric proxy C or better", share(e.fabric_c_or_better.dropna())),
        ("fossil primary heating (heating metric at most D)", share(e.heating_capped_below_c)),
        ("EER C or better but fossil heating", share(e.c_on_eer_but_heating_capped)),
        ("share of EER C-or-better homes capped by the heating rule", share(e.loc[e.eer_c_or_better, "heating_capped_below_c"])),
        ("heat network", share(e.fuel_class.eq("heat network"))), ("electric", share(e.fuel_class.eq("electric"))),
        ("unknown fuel", share(e.fuel_class.eq("unknown"))), ("heat pump", share(e.heat_pump)), ("PV recorded", share(e.pv)),
    ], columns=["measure", "value"])
    d = DATA / a.area / "analysis"
    summ.to_csv(keep(d / "hem_metrics_summary.csv"), index=False)

    out = ["cert_id", "x", "y", "PROPERTY_TYPE", "sap", "eer_c_or_better", "fuel_class", "heat_pump", "pv", "fabric_q",
           "fabric_c_or_better", "heating_capped_below_c", "c_on_eer_but_heating_capped"]
    e[out].assign(PROPERTY_TYPE=e.PROPERTY_TYPE.astype(str)).to_parquet(keep(d / "hem_metrics_cert.parquet"), index=False)
    e["cx"] = (e.x // a.cell) * a.cell + a.cell / 2
    e["cy"] = (e.y // a.cell) * a.cell + a.cell / 2
    g = e.groupby(["cx", "cy"]).agg(n=("cert_id", "size"), eer_c=("eer_c_or_better", "mean"),
                                    fabric_c=("fabric_c_or_better", "mean"), fossil=("heating_capped_below_c", "mean"),
                                    capped=("c_on_eer_but_heating_capped", "mean"), heat_pump=("heat_pump", "mean"),
                                    pv=("pv", "mean")).reset_index()
    g = g[g.n >= 10]
    g.to_parquet(keep(d / "hem_metrics_cells.parquet"), index=False)
    print(summ.to_string(index=False))


if __name__ == "__main__":
    main()
