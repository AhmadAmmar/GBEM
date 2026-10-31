"""Could the rush itself explain the London jump? Three robustness checks, using the independent fit in verify_rd.py.

    python verify_rd_robust.py

The rush may have used up certificates that would have come after the cut-off, so that the homes on either side differ. Checks: add tenure
to the fixed effects; also leave out the 14 and 28 days after the cut-off; estimate within each tenure. Also tests whether tenure jumps at the cut-off.
"""
import numpy as np
import pandas as pd
import verify_rd as V

CUT = pd.Timestamp("2025-06-15")


def show(name, r):
    print(f"{name:40s} n={r['n']:6d} jump={r['jump']:+.3f} by day [{r['day_lo']:+.3f}, {r['day_hi']:+.3f}]")


e = V.load("london")
t = pd.read_parquet(V.ROOT / "data/london/epc/certificates_linked.parquet", columns=["TENURE"]).TENURE.astype(str).str.lower()
e["ten"] = np.select([t.loc[e.index].str.contains("owner"), t.loc[e.index].str.contains("social"), t.loc[e.index].str.contains("private")], ["owner", "social", "private"], "unknown")
for y, lab in [("sap", "SAP"), ("cb", "C or better")]:
    show(f"{lab}: paper specification", V.estimate(e, "2025-06-15", outcome=y))
    show(f"{lab}: with tenure", V.estimate(e.assign(fg=e.fg + e.ten), "2025-06-15", outcome=y))
    for after in (14, 28):
        k = e[(e.date < CUT) | (e.date >= CUT + pd.Timedelta(days=after))]
        show(f"{lab}: also drop {after} days after", V.estimate(k, "2025-06-15", outcome=y))
    for x in ["owner", "private", "social"]:
        show(f"{lab}: {x} only", V.estimate(e[e.ten == x], "2025-06-15", outcome=y))
    show(f"{lab}: tenure, 2024 placebo", V.estimate(e.assign(fg=e.fg + e.ten), "2024-06-15", outcome=y))
w = e[(e.date >= CUT - pd.Timedelta(days=90)) & (e.date < CUT + pd.Timedelta(days=90))]
w = w[(w.date < CUT - pd.Timedelta(days=14)) | (w.date >= CUT)]
print("Tenure share, 76 days before and 90 days after:")
print(w.groupby(w.date >= CUT).ten.value_counts(normalize=True).unstack().round(3).to_string())
print("Weekly certificates after the cut-off:", w[w.date >= CUT].groupby((w.date - CUT).dt.days // 7).size().head(8).to_dict())
