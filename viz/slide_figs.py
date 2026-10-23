"""Slide versions of the paper figures and a map, for the JURSE 2027 talk.

    python slide_figs.py

Same data as viz/paper_figs.py, drawn for projection: 16:9 panels, large type (14-16 pt at slide size), thick lines,
markers and direct labels so that no message depends on colour alone. Colours: London #2a78d6, Belfast #eb6834;
sequential maps in one blue hue (light = low, dark = high), readable in greyscale.
Outputs (PNG 300 dpi + PDF) in Outputs/publication/<id>/<id>_slide.*:
  fig_ceiling, fig_random, fig_scale          as in the paper
  map_belfast_scale    Belfast wards: certified mean SAP vs out-of-fold predicted mean SAP (satellite + form + LiDAR),
                       wards with at least 10 certificates; Irish Grid (EPSG:29902), scale bar, north arrow, credits
"""
import pathlib, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paper_figs as P

INK, INK2, GRID = "#0b0b0b", "#52514e", "#e1e0d9"
plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Arial", "DejaVu Sans"], "font.size": 15,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#898781",
                     "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True,
                     "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True, "axes.titleweight": "bold"})
SEQ = LinearSegmentedColormap.from_list("blue", ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"])


def save(fig, fid, data, note):
    d = P.PUB / fid; d.mkdir(parents=True, exist_ok=True)
    fig.savefig(d / f"{fid}_slide.png", dpi=300, bbox_inches="tight"); fig.savefig(d / f"{fid}_slide.pdf", bbox_inches="tight")
    data.to_csv(d / f"{fid}_slide_data.csv", index=False)
    (d / "SOURCE_slide.txt").write_text(note + "\nScript: code/viz/slide_figs.py\n", encoding="utf-8")
    plt.close(fig)


def ceiling(M, rt):
    fig, ax = plt.subplots(figsize=(11, 5.6)); x = np.arange(len(P.FS)); w = 0.38; rows = []
    for i, area in enumerate(P.TAG):
        m = M[area]
        v = [float(m[(m.featureset == f) & (m.validation == "spatial") & (m.model == "lgbm") & (m.target == "band")]["qwk"].squeeze()) for f, _ in P.FS]
        bars = ax.bar(x + (i - 0.5) * w, v, w * 0.92, color=P.COL[area], label=f"{P.NAME[area]} models", hatch=None if i == 0 else "//", edgecolor="white", linewidth=0)
        for b, t in zip(bars, v):
            ax.text(b.get_x() + b.get_width() / 2, t + 0.012, f"{t:.2f}", ha="center", va="bottom", fontsize=12, color=INK)
        ax.axhline(rt[area]["qwk"], color=P.COL[area], lw=2.5, ls="--")
        ax.text(-0.5, rt[area]["qwk"] + 0.015, f"{P.NAME[area]}: two certificates of the same home agree at {rt[area]['qwk']:.2f}",
                ha="left", va="bottom", fontsize=13, color=INK2)
        rows += [{"area": area, "featureset": f, "qwk": q} for (f, _), q in zip(P.FS, v)]
    ax.set_xticks(x, [l.replace("\n", " ") for _, l in P.FS]); ax.set_ylabel("Agreement with the certificate\n(weighted kappa)")
    ax.set_ylim(0, 1.0); ax.legend(frameon=False, loc="upper left", ncol=2, fontsize=13)
    save(fig, "fig_ceiling", pd.DataFrame(rows), "Weighted kappa, spatial 5-fold CV; dashed: certificate test-retest agreement.")


def random_vs_spatial(M):
    fig, ax = plt.subplots(figsize=(11, 5.6)); rows = []; labels = []
    for area in P.TAG:
        m = M[area]
        for val, mk, ls in (("spatial", "o", "-"), ("random", "s", "--")):
            v = [float(m[(m.featureset == f) & (m.validation == val) & (m.model == "lgbm") & (m.target == "band")]["accuracy"].squeeze()) for f, _ in P.FS]
            ax.plot(range(len(P.FS)), [100 * t for t in v], marker=mk, ms=9, lw=2.6, ls=ls, color=P.COL[area])
            labels.append([100 * v[-1], f"{P.NAME[area]}, {val} folds", P.COL[area], ls])
            rows += [{"area": area, "validation": val, "featureset": f, "accuracy": t} for (f, _), t in zip(P.FS, v)]
    labels.sort(key=lambda t: t[0])                    # direct labels, pushed apart to at least 1.6 points
    for i in range(1, len(labels)):
        labels[i][0] = max(labels[i][0], labels[i - 1][0] + 1.6)
    for yv, text, col, ls in labels:
        ax.text(len(P.FS) - 1 + 0.12, yv, f"{'— —' if ls == '--' else '——'}  {text}", va="center", fontsize=12.5, color=col)
    ax.set_xticks(range(len(P.FS)), [l.replace("\n", " ") for _, l in P.FS]); ax.set_ylabel("Exact band correct (%)")
    ax.set_xlim(-0.3, len(P.FS) + 0.9)
    save(fig, "fig_random", pd.DataFrame(rows), "Band accuracy, random vs spatial (2 km blocks) 5-fold CV.")


def scale():
    fig, axs = plt.subplots(1, 2, figsize=(11, 5.4), sharey=True); rows = []
    order = ["certificate", "building", "street", "250 m cell", "neighbourhood"]
    for ax, area in zip(axs, P.TAG):
        s = pd.read_csv(P.DATA / area / "model/results" / f"scale_{P.TAG[area]}.csv")
        for fs, ls, mk in (("eo", ":", "^"), ("eo_morph", "-", "o")):
            t = s[s.featureset == fs].set_index("scale").reindex(order)
            ax.plot(range(len(order)), t["r2"].clip(lower=-0.25), ls=ls, marker=mk, ms=9, lw=2.6, color=P.COL[area])
            for i, r in enumerate(t["r2"]):
                if r < -0.25:
                    ax.annotate(f"{r:.2f}", (i, -0.25), xytext=(8, 0), textcoords="offset points", va="center", fontsize=11, color=INK2)
            rows += [{"area": area, "featureset": fs, "scale": k, "r2": r} for k, r in t["r2"].items()]
        ax.set_xticks(range(len(order)), ["home", "building", "street", "250 m", "area"], fontsize=13)
        ax.set_title(P.NAME[area], color=INK); ax.set_ylim(-0.28, 0.8)
    axs[0].set_ylabel("Variance explained, R²")
    fig.legend([Line2D([], [], ls=":", marker="^", ms=8, color=INK2, lw=2.2), Line2D([], [], ls="-", marker="o", ms=8, color=INK2, lw=2.2)],
               ["Satellite only", "Satellite + building form + LiDAR"], frameon=False, loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.07), fontsize=13)
    save(fig, "fig_scale", pd.DataFrame(rows), "R2 of mean predicted vs mean certified SAP by spatial unit (out-of-fold).")


def scalebar(ax, x0, y0, km, label_y_off, h=450):
    """alternating two-segment scale bar of km kilometres (map units in metres)"""
    half = km * 500
    ax.add_patch(plt.Rectangle((x0, y0), half, h, facecolor=INK, edgecolor=INK, lw=1))
    ax.add_patch(plt.Rectangle((x0 + half, y0), half, h, facecolor="white", edgecolor=INK, lw=1))
    for d, t in ((0, "0"), (half, f"{km / 2:g}"), (2 * half, f"{km:g} km")):
        ax.text(x0 + d, y0 - label_y_off, t, ha="center", va="top", fontsize=12, color=INK)


def north(ax, x, y, size):
    ax.annotate("N", xy=(x, y + size), xytext=(x, y), ha="center", va="center", fontsize=14, fontweight="bold", color=INK,
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=2))


def belfast_map():
    oof = pd.read_parquet(P.DATA / "belfast/model/results/oof_2024.parquet")
    oof["id_cert"] = oof["id_cert"].astype(str)
    e = pd.read_parquet(P.DATA / "belfast/analysis/cert_enriched.parquet", columns=["cert_id", "nbhd"]).rename(columns={"cert_id": "id_cert"})
    d = oof.merge(e, on="id_cert", how="left")
    w = d.groupby("nbhd").agg(n=("actual_sap", "size"), actual=("actual_sap", "mean"), pred=("sap_lgbm_eo_morph", "mean"))
    w = w[w["n"] >= 10]
    g = gpd.read_parquet(P.DATA / "belfast/analysis/geometry_nbhd.parquet").to_crs(29902).drop_duplicates("nbhd").set_index("nbhd").join(w, how="inner")
    r2 = 1 - ((g["actual"] - g["pred"]) ** 2).sum() / ((g["actual"] - g["actual"].mean()) ** 2).sum()
    bounds = [50, 56, 60, 64, 68, 72, 80]
    norm = BoundaryNorm(bounds, SEQ.N, extend="both")
    fig, axs = plt.subplots(1, 2, figsize=(11, 5.6))
    x0, y0, x1, y1 = g.total_bounds
    for ax, col, title in zip(axs, ("actual", "pred"), ("Certificates (mean SAP)", "Model prediction (mean SAP)")):
        g.plot(column=col, cmap=SEQ, norm=norm, ax=ax, edgecolor="white", linewidth=0.4)
        ax.set_title(title, color=INK, fontsize=15); ax.set_axis_off(); ax.set_aspect("equal")
        ax.set_xlim(x0 - 500, x1 + 500); ax.set_ylim(y0 - 2500, y1 + 300)
    scalebar(axs[0], x0, y0 - 1600, 10, 500); north(axs[1], x0 + 1500, y1 - 4500, 3000)
    sm = plt.cm.ScalarMappable(cmap=SEQ, norm=norm)
    cb = fig.colorbar(sm, ax=axs, orientation="horizontal", fraction=0.045, pad=0.04, aspect=45)
    cb.set_label("Mean SAP score of the ward (higher = more efficient)", fontsize=13, color=INK); cb.ax.tick_params(labelsize=12)
    fig.text(0.01, -0.02, f"Wards (2012) with at least 10 certificates in 2024 (n = {len(g)}); predictions out-of-fold, spatial cross-validation; "
             f"R² = {r2:.2f}. Irish Grid (EPSG:29902).\nBoundaries: OSNI, Open Government Licence. Certificates: Department of Finance NI.",
             fontsize=10.5, color=INK2, ha="left", va="top")
    save(fig, "map_belfast_scale", g.reset_index()[["nbhd", "n", "actual", "pred"]], f"Belfast wards: certified vs predicted mean SAP, R2 {r2:.2f}.")
    return r2


def main():
    M = {k: P.metrics(k) for k in P.TAG}
    rt = {k: pd.read_csv(P.DATA / k / "analysis/ground_truth_retest.csv").iloc[0] for k in P.TAG}
    ceiling(M, rt); random_vs_spatial(M); scale()
    r2 = belfast_map()
    print(f"slide figures written to {P.PUB} (Belfast ward map R2 {r2:.2f})")


if __name__ == "__main__":
    main()
