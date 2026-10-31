"""Recalculates the UKES abstract's subgroup and geography claims from the certificates, using the independent fit in verify_rd.py.

    python verify_ukes.py

Subgroups use the paper's specification (180 days, 14-day donut, linear trends). Prints aggregates only.
"""
import pathlib
import numpy as np
import pandas as pd
import verify_rd as V

ROOT = V.ROOT


def show(name, r):
    print(f"{name:42s} n={r['n']:7d} jump={r['jump']:+.3f} HC1 [{r['hc_lo']:+.3f}, {r['hc_hi']:+.3f}] by day [{r['day_lo']:+.3f}, {r['day_hi']:+.3f}]")


e = V.load("london")
e["start"] = e.CONSTRUCTION_AGE_BAND.map(V.age_start)
print("London age bands by group:\n", e.groupby("ag").CONSTRUCTION_AGE_BAND.agg(lambda s: sorted(set(s.astype(str).str.replace("England and Wales: ", "")))[:7]).to_string())
c = "2025-06-15"
house = e.pt.isin(["House", "Bungalow"])
for name, sel in [("houses, all ages", e.pt == "House"), ("houses built before 1976", (e.pt == "House") & e.start.between(0, 1975)), ("all homes built before 1976", e.start.between(0, 1975)),
                  ("all homes from 2003", e.start >= 2003), ("houses from 2003", (e.pt == "House") & (e.start >= 2003))]:
    d = e[sel]
    for col in ["ag", "pt"]:
        if d[col].nunique() == 1:
            d = d.assign(**{col: "one"})
    show(name, V.estimate(d, c, bw=180))
    show(name + ", C or better", V.estimate(d, c, bw=180, outcome="cb"))

g = pd.read_parquet(ROOT / "data/london/epc/certificates_linked.parquet", columns=["LOCAL_AUTHORITY_LABEL", "is_latest", "REPORT_TYPE", "sap_score", "CONSTRUCTION_AGE_BAND", "PROPERTY_TYPE"])
g = g[(g.REPORT_TYPE.astype(str) == "2") & g.is_latest.astype(bool)].copy()
g["sap"] = pd.to_numeric(g.sap_score, errors="coerce")
near = g.CONSTRUCTION_AGE_BAND.map(V.age_start).between(0, 1975) & g.PROPERTY_TYPE.astype(str).isin(["House", "Bungalow", "Maisonette"]) & g.sap.between(67, 68)
s = near.groupby(g.LOCAL_AUTHORITY_LABEL.astype(str)).agg(["mean", "size"]).sort_values("mean", ascending=False)
s = s[s["size"] > 5000]
print("Homes most likely to cross into C, % of certified dwellings, by council")
print((s["mean"] * 100).round(1).head(10).to_string())
print("lowest:\n", (s["mean"] * 100).round(1).tail(6).to_string())

b = V.load("belfast")
print("Belfast age bands:", sorted(set(b.CONSTRUCTION_AGE_BAND.astype(str)))[:14])
for y in ["sap", "cb"]:
    show("Belfast " + y, V.estimate(b, c, bw=90, outcome=y))
w = b[(b.date >= "2025-04-13") & (b.date < "2025-06-15")]
print("Belfast weekly lodgements before the cut-off:", w.groupby((w.date - pd.Timestamp(c)).dt.days // 7).size().to_dict())
print("Belfast last lodgement:", b.date.max().date(), "certificates kept:", len(V.load("belfast")))
