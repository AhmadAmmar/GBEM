"""Pooled comparison of HEM space heat demand with the fabric proxy over a campaign of built forms and climates.

    python compare_campaign.py --campaign <folder with <form>_<city>/ subfolders from make_archetypes.py --form>

Each subfolder holds variants.csv and variant_<id>__results (run_hem.sh locally or run_hem_array.sh on Kelvin-2).
Reports Spearman and Pearson correlation and a linear calibration HEM = a x proxy + b: pooled, by city and by form, plus
the mean HEM demand by level of each factor within each city. The calibration by city is what maps the proxy of the
whole-stock models onto HEM-scale demand.
Outputs in --campaign: campaign_results.csv (all variants), campaign_summary.csv, campaign_scatter.png
"""
import argparse, pathlib
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from compare_trial import hem_demand


def fit(g):
    r = stats.pearsonr(g.q_proxy_kwh_m2, g.hem_kwh_m2)[0]
    a, b = np.polyfit(g.q_proxy_kwh_m2, g.hem_kwh_m2, 1)
    return pd.Series({"n": len(g), "spearman": stats.spearmanr(g.q_proxy_kwh_m2, g.hem_kwh_m2)[0], "pearson": r,
                      "r2": r * r, "slope": a, "intercept": b,
                      "rmse_after_fit": np.sqrt(np.mean((g.hem_kwh_m2 - (a * g.q_proxy_kwh_m2 + b)) ** 2))})


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--campaign", required=True)
    c = pathlib.Path(ap.parse_args().campaign)
    parts = []
    for d in sorted(p for p in c.iterdir() if (p / "variants.csv").exists()):
        v = pd.read_csv(d / "variants.csv", dtype={"variant": str})
        v["city"] = d.name.rsplit("_", 1)[1]
        v["hem_kwh_m2"] = [hem_demand(d, i) if (d / f"variant_{i}__results").exists() else np.nan for i in v.variant]
        parts.append(v)
    v = pd.concat(parts, ignore_index=True)
    v.to_csv(c / "campaign_results.csv", index=False)
    print(f"{v.hem_kwh_m2.notna().sum()} of {len(v)} variants have HEM results")
    v = v.dropna(subset=["hem_kwh_m2"])
    rows = [fit(v).rename("all")]
    rows += [fit(g).rename(f"city={k}") for k, g in v.groupby("city")]
    rows += [fit(g).rename(f"city={k[0]}, form={k[1]}") for k, g in v.groupby(["city", "form"])]
    s = pd.DataFrame(rows)
    s.round(3).to_csv(c / "campaign_summary.csv")
    print(s.round(3).to_string())
    for f in ("form", "wall", "roof", "window", "air", "floor"):
        print(f, v.groupby(["city", f]).hem_kwh_m2.mean().round(1).unstack(0).to_string(), sep="\n")
    fig, axs = plt.subplots(1, v.city.nunique(), figsize=(8, 3.8), sharey=True, squeeze=False)
    for ax, (k, g) in zip(axs[0], v.groupby("city")):
        for (f, h), mk in zip(g.groupby("form"), "os^vDP"):
            ax.scatter(h.q_proxy_kwh_m2, h.hem_kwh_m2, s=8, marker=mk, label=f.replace("_", " "))
        r = fit(g)
        ax.set(title=f"{k.title()}: Spearman {r.spearman:.3f}, R2 {r.r2:.3f}", xlabel="Fabric proxy Q (kWh/m2/yr)")
    axs[0][0].set_ylabel("HEM space heat demand (kWh/m2)"); axs[0][0].legend(frameon=False, fontsize=6)
    fig.savefig(c / "campaign_scatter.png", dpi=300, bbox_inches="tight")


if __name__ == "__main__":
    main()
