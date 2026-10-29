"""Compare HEM space heating demand with the fabric proxy on the trial variants (make_archetypes.py, run_hem.sh).

    python compare_trial.py --inputs <folder with variants.csv and variant_<id>__results>

Reads "Space heat demand" (kWh/m2 over the simulated period) from each variant's results summary and compares it with
the proxy Q of variants.csv: Spearman and Pearson correlation, a linear fit of HEM on proxy, and the ratio by variant.
The proxy uses annual heating degree days while the trial base may simulate part of a year, so the level differs by a
factor; the test is whether the proxy ranks fabric as HEM does. Also reports how much each element moves HEM demand
(mean HEM demand by level of each factor).
Outputs in --inputs: trial_comparison.csv, trial_summary.txt, trial_scatter.png
"""
import argparse, pathlib
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def hem_demand(folder, vid):
    f = folder / f"variant_{vid}__results" / f"variant_{vid}__core__results_summary.csv"
    for line in f.read_text(encoding="utf8").splitlines():
        if line.startswith("Space heat demand"):
            return float(line.split(",")[-1])
    return np.nan


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--inputs", required=True)
    a = ap.parse_args()
    d = pathlib.Path(a.inputs)
    v = pd.read_csv(d / "variants.csv", dtype={"variant": str})
    v["hem_kwh_m2"] = [hem_demand(d, i) for i in v.variant]
    rho = stats.spearmanr(v.q_proxy_kwh_m2, v.hem_kwh_m2)[0]
    r = stats.pearsonr(v.q_proxy_kwh_m2, v.hem_kwh_m2)[0]
    slope, icpt = np.polyfit(v.q_proxy_kwh_m2, v.hem_kwh_m2, 1)
    v["ratio_hem_to_proxy"] = v.hem_kwh_m2 / v.q_proxy_kwh_m2
    v.to_csv(d / "trial_comparison.csv", index=False)
    lines = [f"variants: {len(v)}", f"Spearman rho: {rho:.3f}", f"Pearson r: {r:.3f} (R2 {r * r:.3f})",
             f"fit: HEM = {slope:.3f} x proxy + {icpt:.1f}",
             f"ratio HEM/proxy: median {v.ratio_hem_to_proxy.median():.3f}, range {v.ratio_hem_to_proxy.min():.3f}-{v.ratio_hem_to_proxy.max():.3f}"]
    for f in ("wall", "roof", "window", "air"):
        if v[f].nunique() > 1:
            m = v.groupby(f).hem_kwh_m2.mean().round(1).to_dict()
            p = v.groupby(f).q_proxy_kwh_m2.mean().round(1).to_dict()
            lines.append(f"{f}: HEM {m} | proxy {p}")
    (d / "trial_summary.txt").write_text("\n".join(lines), encoding="utf8")
    print("\n".join(lines))
    fig, ax = plt.subplots(figsize=(4.2, 3.6))
    for (w, g), mk in zip(v.groupby("wall"), "osD"):
        ax.scatter(g.q_proxy_kwh_m2, g.hem_kwh_m2, marker=mk, s=22, label=f"wall: {w}")
    x = np.linspace(v.q_proxy_kwh_m2.min(), v.q_proxy_kwh_m2.max(), 10)
    ax.plot(x, slope * x + icpt, color="k", lw=0.8)
    ax.set(xlabel="Fabric proxy Q (kWh/m2/yr)", ylabel="HEM space heat demand (kWh/m2, simulated period)",
           title=f"Spearman {rho:.2f}, R2 {r * r:.2f}")
    ax.legend(frameon=False, fontsize=7)
    fig.savefig(d / "trial_scatter.png", dpi=300, bbox_inches="tight")


if __name__ == "__main__":
    main()
