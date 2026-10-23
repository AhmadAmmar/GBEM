"""Heat-pump readiness of the housing stock, by home, street and neighbourhood.

    python heatpump_readiness.py --area belfast|london [--ready 2.0] [--minor 3.0]

Heat-loss parameter HLP = heat-loss coefficient / floor area (W/m2K), from analysis/physics_check.py (envelope
geometry from footprints and LiDAR, U-values from the certificate's element descriptions, thermal bridging and
ventilation; floor area from the certificate). A low HLP means the home can be kept warm at the low flow temperatures
at which heat pumps are efficient. Screening bands (thresholds are arguments; the defaults are working values to be
confirmed against heat-pump suitability guidance before they are reported as such):
  ready         HLP < --ready
  minor fabric  --ready <= HLP < --minor
  fabric first  HLP >= --minor
Checked against what is observed: share of homes heated by a heat pump in each band (current stock), and the HLP of
homes whose later certificate shows a switch to a heat pump. Aggregated by street, neighbourhood (London LSOA,
Belfast ward) and 250 m cell for maps (units with >= 5 homes).
Outputs in data/<area>/analysis/: hp_readiness_summary.csv, hp_readiness_units_<unit>.parquet, hp_readiness_cert.parquet
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--ready", type=float, default=2.0); ap.add_argument("--minor", type=float, default=3.0)
    a = ap.parse_args()
    out = DATA / a.area / "analysis"
    ph = pd.read_parquet(out / "physics_cert.parquet", columns=["cert_id", "hlc_as_described", "floor_area", "q_as_described_kwh_m2"])
    cur = pd.read_parquet(out / "stock_current.parquet", columns=["cert_id", "uprn", "fuel", "property_type", "floor_pos", "street", "nbhd", "cell", "sap", "band"])
    d = cur.merge(ph, on="cert_id", how="inner")
    d["hlp"] = d["hlc_as_described"] / d["floor_area"].where(d["floor_area"] > 10)
    d = d[d["hlp"].between(0.2, 15)]
    d["readiness"] = pd.cut(d["hlp"], [0, a.ready, a.minor, np.inf], labels=["ready", "minor fabric", "fabric first"], right=False)
    d["heat_pump"] = d["fuel"].eq("heat pump")
    print(f"{a.area}: {len(d):,} homes with a heat-loss estimate; median HLP {d['hlp'].median():.2f} W/m2K", flush=True)
    rows = []
    for grp, g in [("all", d)] + [(f"type: {k}", v) for k, v in d.groupby("property_type") if len(v) >= 200]:
        s = {"group": grp, "homes": len(g), "hlp_median": g["hlp"].median()}
        for r in ("ready", "minor fabric", "fabric first"):
            m = g["readiness"] == r
            s[f"share_{r.replace(' ', '_')}"] = m.mean()
            s[f"heat_pump_share_in_{r.replace(' ', '_')}"] = g.loc[m, "heat_pump"].mean() if m.any() else np.nan
        rows.append(s)
    summ = pd.DataFrame(rows)
    # homes that switched to a heat pump between certificates: their heat-loss parameter at the later certificate
    e = pd.read_parquet(out / "cert_enriched.parquet", columns=["cert_id", "uprn", "date", "fuel"]).sort_values(["uprn", "date"])
    prev = e.groupby("uprn")["fuel"].shift()
    switched = set(e.loc[e["fuel"].eq("heat pump") & prev.notna() & prev.ne("heat pump"), "cert_id"])
    sw = d[d["cert_id"].isin(switched)]
    summ["switchers_with_hlp"] = len(sw)
    summ["switchers_hlp_median"] = sw["hlp"].median() if len(sw) else np.nan
    summ.round(4).to_csv(keep(out / "hp_readiness_summary.csv"), index=False)
    print(summ.round(3).to_string(index=False))
    for unit in ("street", "nbhd", "cell"):
        u = d[d[unit].notna()].groupby(unit).agg(homes=("hlp", "size"), hlp_median=("hlp", "median"),
                                                  share_ready=("readiness", lambda s: (s == "ready").mean()),
                                                  share_fabric_first=("readiness", lambda s: (s == "fabric first").mean()),
                                                  heat_pump_share=("heat_pump", "mean"))
        u[u["homes"] >= 5].round(4).reset_index().to_parquet(keep(out / f"hp_readiness_units_{unit}.parquet"), index=False)
    d[["cert_id", "uprn", "property_type", "floor_pos", "hlp", "readiness", "heat_pump", "street", "nbhd", "cell"]].to_parquet(keep(out / "hp_readiness_cert.parquet"), index=False)
    print("written", out)


if __name__ == "__main__":
    main()
