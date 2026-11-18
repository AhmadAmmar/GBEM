"""RdSAP 10 jump re-estimated with local-linear regression, a data-driven (MSE-optimal) bandwidth, a triangular kernel
and robust bias-corrected intervals (Calonico, Cattaneo and Titiunik 2014, rdrobust), errors clustered by lodgement day.
A check on method_change_rd.py, whose main estimate uses a fixed 90-day window and HC1 errors.

    python verify_rd_rdrobust.py            both areas; writes data/<area>/analysis/verify_rd_rdrobust.csv

Same certificates, fixed effects (as covariates) and 14-day donut as verify_rd.py; one year either side of each
cut-off is offered, and the bandwidth is chosen inside it.
"""
import pathlib, sys
import pandas as pd
from rdrobust import rdrobust

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import verify_rd as v  # noqa: E402


def main():
    """Cross-check of the jumps with rdrobust (Calonico, Cattaneo and Titiunik 2014) at the cutoff and placebo dates, for
    both areas; writes verify_rd_rdrobust.csv.
    """
    for area in ("london", "belfast"):
        e = v.load(area)
        rows = []
        for cut in ("2025-06-15", "2024-06-15", "2023-06-15"):
            c = pd.Timestamp(cut)
            d = e[(e.date >= c - pd.Timedelta(days=365)) & (e.date < c + pd.Timedelta(days=365))]
            d = d[(d.date < c - pd.Timedelta(days=14)) | (d.date >= c)]
            x = (d.date - c).dt.days.to_numpy(float)
            X = pd.get_dummies(d[["pt", "bf", "ag", "fg"]], drop_first=True).astype(float)
            X = X.loc[:, X.std() > 0].to_numpy()
            for y, name in (("sap", "sap"), ("cb", "c_or_better")):
                r = rdrobust(d[y].to_numpy(float), x, c=0, covs=X, cluster=x.astype(int), kernel="triangular", bwselect="mserd")
                lo, hi = r.ci.iloc[2].to_numpy()
                rows.append({"cutoff": cut, "outcome": name, "jump": float(r.coef.iloc[0, 0]), "robust_ci_low": lo, "robust_ci_high": hi,
                             "bandwidth_days": float(r.bws.iloc[0, 0]), "n_effective": int(r.N_h[0] + r.N_h[1])})
        out = pd.DataFrame(rows)
        print(area); print(out.round(3).to_string(index=False))
        out.to_csv(v.ROOT / "data" / area / "analysis/verify_rd_rdrobust.csv", index=False)


if __name__ == "__main__":
    main()
