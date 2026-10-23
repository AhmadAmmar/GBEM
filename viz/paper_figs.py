"""Publication figures and numbers for the label-noise / spatial-benchmark paper (JURSE 2027 draft).

    python paper_figs.py [--paper Manuscripts/03_JURSE2027]

Figures (IEEE single column, 3.5 in wide; PDF vector + PNG 300 dpi; one folder each in Outputs/publication/ with the
data it shows and SOURCE.txt):
  fig_ceiling   weighted kappa of the models (spatial CV) by feature set, both cities, against the certificate
                test-retest agreement (label-noise ceiling)
  fig_scale     R2 of mean predicted vs mean actual SAP by spatial scale (dwelling, building, street, 250 m cell,
                neighbourhood), satellite only vs satellite + form + LiDAR, both cities
  fig_random    accuracy with random vs spatial folds by feature set (the optimism of random splits)
Numbers for the text are written to <paper>/generated/numbers.tex.
Colours: London #2a78d6, Belfast #eb6834 (fixed categorical order); text in ink colours; no dual axes.
"""
import argparse, datetime, pathlib, subprocess
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

CODE = pathlib.Path(__file__).resolve().parents[1]
PHD = CODE.parent
DATA = PHD / "data"
PUB = PHD / "Outputs/publication"
TAG = {"london": "2024_s50k", "belfast": "2024"}
COL = {"london": "#2a78d6", "belfast": "#eb6834"}
NAME = {"london": "London", "belfast": "Belfast"}
FS = [("eo", "Satellite"), ("eo_morph_nolidar", "+ form"), ("eo_morph", "+ LiDAR"), ("eo_morph_floor", "+ floor"), ("all", "+ cert.\nattributes")]
plt.rcParams.update({"font.family": "sans-serif", "font.size": 7.5, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#898781", "axes.labelcolor": "#0b0b0b", "xtick.color": "#52514e", "ytick.color": "#52514e",
                     "axes.grid": True, "grid.color": "#e1e0d9", "grid.linewidth": 0.5, "axes.axisbelow": True})


def metrics(area):
    res = DATA / area / "model/results"
    files = [res / f"baseline_{TAG[area]}.csv"] + sorted(res.glob(f"baseline_{TAG[area]}_*.csv"))
    b = pd.concat([pd.read_csv(f) for f in files if f.exists()])
    return b.drop_duplicates(["featureset", "validation", "model", "target"], keep="last")


def save(fig, fid, data, note):
    d = PUB / fid; d.mkdir(parents=True, exist_ok=True)
    fig.savefig(d / f"{fid}.pdf", bbox_inches="tight"); fig.savefig(d / f"{fid}.png", dpi=300, bbox_inches="tight")
    data.to_csv(d / f"{fid}_data.csv", index=False)
    v = subprocess.run(["git", "-C", str(CODE), "describe", "--tags", "--always"], capture_output=True, text=True).stdout.strip()
    (d / "SOURCE.txt").write_text(f"{note}\nScript: code/viz/paper_figs.py (code {v}), {datetime.date.today()}\n", encoding="utf-8")
    plt.close(fig)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", default=str(PHD / "Manuscripts/03_JURSE2027"))
    a = ap.parse_args()
    nums = {}
    M = {k: metrics(k) for k in TAG}
    rt = {k: pd.read_csv(DATA / k / "analysis/ground_truth_retest.csv").iloc[0] for k in TAG}
    # fig_ceiling
    fig, ax = plt.subplots(figsize=(3.5, 2.2))
    x = np.arange(len(FS)); w = 0.38; rows = []
    for i, area in enumerate(TAG):
        m = M[area]
        v = [m[(m.featureset == f) & (m.validation == "spatial") & (m.model == "lgbm") & (m.target == "band")]["qwk"].squeeze() for f, _ in FS]
        v = [float(t) if np.isscalar(t) or getattr(t, "size", 0) == 1 else np.nan for t in v]
        ax.bar(x + (i - 0.5) * w, v, w * 0.92, color=COL[area], label=f"{NAME[area]} models")
        ax.axhline(rt[area]["qwk"], color=COL[area], lw=1.2, ls="--")
        ax.text(-0.45, rt[area]["qwk"] + 0.012, f"{NAME[area]} certificate test-retest {rt[area]['qwk']:.2f}", ha="left", va="bottom", fontsize=6.3, color="#52514e")
        rows += [{"area": area, "featureset": f, "qwk": q, "retest_qwk": rt[area]["qwk"]} for (f, _), q in zip(FS, v)]
    ax.set_xticks(x, [l for _, l in FS]); ax.set_ylabel("Weighted kappa (spatial CV)"); ax.set_ylim(0, 1.0)
    ax.legend(frameon=False, loc="upper left", fontsize=6.5, bbox_to_anchor=(0, 1.0), ncol=2)
    save(fig, "fig_ceiling", pd.DataFrame(rows), "Weighted kappa of LightGBM band models (spatial 5-fold CV, 2 km blocks, 2024) and certificate test-retest agreement (pairs within 365 days, same fuel, type and floor area).")
    # fig_scale
    fig, axs = plt.subplots(1, 2, figsize=(3.5, 1.9), sharey=True); rows = []
    order = ["certificate", "building", "street", "250 m cell", "neighbourhood"]
    for ax, area in zip(axs, TAG):
        s = pd.read_csv(DATA / area / "model/results" / f"scale_{TAG[area]}.csv")
        for fs, ls, lab in (("eo", ":", "Satellite"), ("eo_morph", "-", "+ form, LiDAR"), ("eo_morph_floor", "--", "+ floor")):
            t = s[s.featureset == fs].set_index("scale").reindex(order)
            ax.plot(range(len(order)), t["r2"].clip(lower=-0.25), ls, marker="o", ms=3, lw=1.4, color=COL[area])
            for i, r in enumerate(t["r2"]):
                if r < -0.25:                                    # off the axis: value written at the bottom
                    ax.annotate(f"{r:.2f}", (i, -0.25), xytext=(5, 0), textcoords="offset points", ha="left", va="center", fontsize=5.5, color="#52514e")
            rows += [{"area": area, "featureset": fs, "scale": k, "r2": r} for k, r in t["r2"].items()]
        ax.set_xticks(range(len(order)), ["home", "bldg", "street", "cell", "nbhd"], fontsize=6.5)
        ax.set_title(NAME[area], fontsize=7.5, color="#0b0b0b"); ax.set_ylim(-0.27, 0.8)
    axs[0].set_ylabel("R$^2$ of unit means (SAP)")
    from matplotlib.lines import Line2D
    fig.legend([Line2D([], [], ls=ls, color="#52514e", lw=1.2) for ls in (":", "-", "--")], ["Satellite", "+ form, LiDAR", "+ floor"],
               frameon=False, fontsize=6.3, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.14))
    save(fig, "fig_scale", pd.DataFrame(rows), "R2 of mean predicted vs mean actual SAP of out-of-fold predictions (spatial CV) by spatial unit; units with >= 5 certificates (buildings >= 2).")
    # fig_random
    fig, ax = plt.subplots(figsize=(3.5, 2.0)); rows = []
    for area in TAG:
        m = M[area]
        for val, mk in (("spatial", "o"), ("random", "s")):
            v = [float(m[(m.featureset == f) & (m.validation == val) & (m.model == "lgbm") & (m.target == "band")]["accuracy"].squeeze()) for f, _ in FS]
            ax.plot(range(len(FS)), v, marker=mk, ms=3.5, lw=1.2, ls="-" if val == "spatial" else "--", color=COL[area], label=f"{NAME[area]}, {val} folds")
            rows += [{"area": area, "validation": val, "featureset": f, "accuracy": t} for (f, _), t in zip(FS, v)]
    ax.set_xticks(range(len(FS)), [l for _, l in FS]); ax.set_ylabel("Band accuracy"); ax.legend(frameon=False, fontsize=6, ncol=2)
    save(fig, "fig_random", pd.DataFrame(rows), "Band accuracy with random vs spatial (2 km blocks) 5-fold CV by feature set, LightGBM, 2024.")
    # numbers for the text
    for area, k in (("london", "Lon"), ("belfast", "Bel")):
        r = rt[area]
        nums[f"{k}RetestPairs"] = f"{int(r['pairs']):,}".replace(",", "{,}"); nums[f"{k}RetestSame"] = f"{100 * r['same_band']:.0f}"
        nums[f"{k}RetestQwk"] = f"{r['qwk']:.2f}"; nums[f"{k}RetestWithin"] = f"{100 * r['within_one_band']:.0f}"
        m = M[area]
        for f, nm in (("eo", "Eo"), ("eo_morph", "Morph"), ("eo_morph_floor", "Floor"), ("all", "All"), ("eo_morph_nolidar", "Form")):
            for val, vn in (("spatial", ""), ("random", "Rand")):
                r2 = m[(m.featureset == f) & (m.validation == val) & (m.model == "lgbm") & (m.target == "band")]
                if len(r2):
                    nums[f"{k}Acc{nm}{vn}"] = f"{100 * r2['accuracy'].iat[0]:.1f}"; nums[f"{k}Qwk{nm}{vn}"] = f"{r2['qwk'].iat[0]:.2f}"
        s = pd.read_csv(DATA / area / "model/results" / f"scale_{TAG[area]}.csv").set_index(["featureset", "scale"])
        for sc, sn in (("certificate", "Home"), ("street", "Street"), ("neighbourhood", "Nbhd")):
            if ("eo_morph", sc) in s.index:
                nums[f"{k}RsqMorph{sn}"] = f"{s.loc[('eo_morph', sc), 'r2']:.2f}"
    t = pd.read_csv(DATA / "model_transfer/transfer_2024.csv")
    for exp, nm in (("London -> Belfast 2024", "LonToBel"), ("Belfast -> London 2024", "BelToLon")):
        r = t[(t.experiment == exp) & (t.featureset == "core")]
        if len(r):
            nums[f"Acc{nm}"] = f"{100 * r['accuracy'].iat[0]:.1f}"; nums[f"Bias{nm}"] = f"{r['mean_sap_pred'].iat[0] - r['mean_sap_actual'].iat[0]:+.1f}"
    g = pathlib.Path(a.paper) / "generated"; g.mkdir(parents=True, exist_ok=True)
    (g / "numbers.tex").write_text("".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in sorted(nums.items())), encoding="utf-8")
    fd = pathlib.Path(a.paper) / "figures"; fd.mkdir(parents=True, exist_ok=True)
    for fid in ("fig_ceiling", "fig_scale", "fig_random"):
        (fd / f"{fid}.pdf").write_bytes((PUB / fid / f"{fid}.pdf").read_bytes())
    print(f"{len(nums)} numbers, 3 figures -> {PUB} and {a.paper}")


if __name__ == "__main__":
    main()
