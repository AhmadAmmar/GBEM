"""Stage 5 - PRISMA diagram, schematic and synthesis figures.

Figures: fig01_framework, fig02_prisma, fig03_workflow, fig09_timeline, fig10_evidence_map,
         fig11_performance, fig12_validation_time, fig13_roadmap, ga (graphical abstract, 1328x531 px)
Feeds : Figs 1-3 and 9-13 and the graphical abstract.
"""
import textwrap
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from common import load, read_csv

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.spines.top": False, "axes.spines.right": False})
VCOL = {"Held-out city": "#c0392b", "Held-out area": "#e67e22", "Spatially blocked CV": "#d35400", "Temporal hold-out": "#16a085",
        "Transfer with local fine-tuning": "#8e44ad", "Random split": "#2f5d8a", "Internal (not specified)": "#7f8c8d", "Not reported": "#bbbbbb"}


def box(ax, x, y, w, h, text, fc="#ffffff", ec="#56657a", fs=6.6, wrap=48):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.004,rounding_size=0.01", fc=fc, ec=ec, lw=0.8))
    ax.text(x + w / 2, y + h / 2, "\n".join(textwrap.fill(l, wrap) for l in text.split("\n")), ha="center", va="center", fontsize=fs, linespacing=1.3)


def arrow(ax, x1, y1, x2, y2):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=8, color="#56657a", lw=0.8))


def canvas(w, h):
    fig = plt.figure(figsize=(w, h), dpi=300); ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    return fig, ax


def run(cfg, P):
    I, S, B, Fs = (load(P["out"] / f) for f in ["stats_ingest.json", "stats_screening.json", "stats_biblio.json", "stats_focused.json"])
    F = read_csv(P["out"] / "focused_final.csv")
    supp = read_csv(P["inputs"] / cfg.HUMAN["supplementary_studies"])
    fig_ = P["fig"]

    # ---------------- PRISMA 2020
    fig, ax = canvas(7.2, 6.6)
    for y0, y1, lab in [(0.80, 0.97, "Identification"), (0.30, 0.79, "Screening"), (0.03, 0.29, "Included")]:
        ax.add_patch(FancyBboxPatch((0.01, y0), 0.045, y1 - y0, boxstyle="round,pad=0.002", fc="#dbe7f3", ec="none"))
        ax.text(0.0325, (y0 + y1) / 2, lab, rotation=90, ha="center", va="center", fontsize=7.5, weight="bold")
    ident = f"Records identified ({I['search_date']}, {I['field']})\nScopus n = {I['n_scopus']:,}"
    if I["n_wos"]:
        ident += f"\nWeb of Science n = {I['n_wos']:,}"
    box(ax, 0.08, 0.84, 0.40, 0.12, ident, fc="#f4f8fc")
    box(ax, 0.55, 0.84, 0.42, 0.12, f"Records removed before screening:\nduplicates n = {I['n_duplicates']:,}\nineligible record type or years n = {S['n_removed_record_type']:,}")
    arrow(ax, 0.48, 0.90, 0.55, 0.90)
    box(ax, 0.08, 0.66, 0.40, 0.10, f"Records screened (title, abstract, keywords)\nn = {S['n_screened']:,}\n= bibliometric corpus", fc="#f4f8fc")
    arrow(ax, 0.28, 0.84, 0.28, 0.76)
    exc = "\n".join(f"{k}: n = {v:,}" for k, v in S["excluded_reasons"].items())
    box(ax, 0.55, 0.52, 0.42, 0.26, f"Records excluded (n = {S['n_excluded_ta']:,}):\n{exc}", wrap=72, fs=5.8)
    arrow(ax, 0.48, 0.71, 0.55, 0.66)
    box(ax, 0.08, 0.50, 0.40, 0.10, f"Review articles set aside for umbrella/context use\nn = {S['n_reviews']:,}", fc="#fff8e6")
    arrow(ax, 0.28, 0.66, 0.28, 0.60)
    ver = f"verified by reviewer: {S['n_verified_by_reviewer']:,}" if S["n_verified_by_reviewer"] else "reviewer verification in progress"
    box(ax, 0.08, 0.33, 0.40, 0.12, f"Primary studies eligible at title/abstract stage\nn = {S['n_core']:,}\n({ver})", fc="#f4f8fc")
    arrow(ax, 0.28, 0.50, 0.28, 0.45)
    box(ax, 0.55, 0.33, 0.42, 0.14, f"Identification via other methods\n(citation searching, expert suggestion)\nrecords n = {len(supp):,}; eligible for the focused subset n = {Fs['n_focused_other']}", fc="#f4f8fc", fs=6.1)
    box(ax, 0.08, 0.16, 0.40, 0.11, f"Core systematic set\nn = {S['n_core']:,} studies", fc="#e6f2e6")
    arrow(ax, 0.28, 0.33, 0.28, 0.27)
    box(ax, 0.55, 0.05, 0.42, 0.14, f"Focused subset: building-level estimation of energy-efficiency ratings, labels or scores\nn = {Fs['n_focused']} ({Fs['n_focused_db']} database + {Fs['n_focused_other']} other methods)", fc="#e6f2e6", fs=6.1)
    arrow(ax, 0.48, 0.20, 0.55, 0.12); arrow(ax, 0.76, 0.33, 0.76, 0.19)
    fig.savefig(fig_ / "fig02_prisma.png"); plt.close(fig)

    # ---------------- Fig 1 framework
    fig, ax = canvas(7.2, 3.4)
    cols = [("Observation layers", ["Optical satellite / aerial", "Thermal infrared / LST", "LiDAR / 3D city models", "Street-level imagery", "SAR", "GIS, cadastre, UPRN", "Climate, LCZ, UHI"], "#e8f0fa"),
            ("Linkage", ["Address / UPRN matching", "Footprint delineation", "Point vs zonal statistics", "Multi-dwelling buildings", "EO-label time alignment"], "#fdf1e3"),
            ("Target formulation", ["Binary (e.g. A-D vs E-G)", "Ordinal bands (A-G)", "Continuous (SAP, EUI)", "Attributes (age, WWR, U-value)"], "#eaf5ea"),
            ("Validation", ["Random / k-fold", "Spatially blocked", "Held-out city or area", "Temporal hold-out", "Transfer with fine-tuning"], "#f3eafa"),
            ("Use", ["Stock screening", "Retrofit targeting", "MEES / MEPS compliance", "Fuel-poverty support", "Planning and SDGs 7, 11, 13"], "#f1f1f1")]
    for i, (title, items, fc) in enumerate(cols):
        x = 0.015 + i * 0.197
        ax.add_patch(FancyBboxPatch((x, 0.05), 0.18, 0.86, boxstyle="round,pad=0.004,rounding_size=0.015", fc=fc, ec="#8391a5", lw=0.8))
        ax.text(x + 0.09, 0.86, title, ha="center", fontsize=8, weight="bold")
        for j, it in enumerate(items):
            ax.text(x + 0.09, 0.76 - j * 0.1, it, ha="center", fontsize=6.4)
        if i < len(cols) - 1:
            arrow(ax, x + 0.181, 0.48, x + 0.196, 0.48)
    ax.text(0.5, 0.005, "Uncertainty, label noise and interpretability cut across all stages", ha="center", fontsize=6.4, style="italic", color="#444")
    fig.savefig(fig_ / "fig01_framework.png"); plt.close(fig)

    # ---------------- Fig 3 workflow
    fig, ax = canvas(7.2, 3.3)
    dbs = "Scopus" + (" + Web of Science" if I["n_wos"] else "")
    tiers = [(f"Records identified  n = {I['n_identified']:,}", f"{dbs}; {I['field']}; concept blocks A-C (Table 2)", 0.92),
             (f"Bibliometric corpus  n = {S['n_screened']:,}", "Performance analysis and science mapping (Section 3)", 0.74),
             (f"Core systematic set  n = {S['n_core']:,}", "Screening rules + reviewer verification; abstract-level coding (Section 4)", 0.56),
             (f"Focused subset  n = {Fs['n_focused']}", "Full-text extraction: data, target, validation, metrics", 0.38)]
    for i, (t, d, wdt) in enumerate(tiers):
        y = 0.78 - i * 0.2; x = (1 - wdt * 0.62) / 2 - 0.16
        ax.add_patch(FancyBboxPatch((x, y), wdt * 0.62, 0.15, boxstyle="round,pad=0.004,rounding_size=0.02", fc=plt.cm.Blues(0.25 + 0.17 * i), ec="none"))
        ax.text(x + wdt * 0.31, y + 0.075, t, ha="center", va="center", fontsize=8, weight="bold", color="white" if i > 1 else "black")
        ax.text(0.70, y + 0.075, textwrap.fill(d, 42), ha="left", va="center", fontsize=6.4)
    fig.savefig(fig_ / "fig03_workflow.png"); plt.close(fig)

    # ---------------- Fig 9 timeline
    data_ev = [(1984, "Landsat 5 TM (thermal band)"), (1999, "Landsat 7; Terra ASTER/MODIS"), (2004, "OpenStreetMap"), (2007, "Google Street View"),
               (2013, "Landsat 8 TIRS"), (2014, "Sentinel-1A (SAR)"), (2015, "Sentinel-2A; open EA LiDAR"), (2018, "ECOSTRESS"), (2021, "Landsat 9")]
    pol_ev = [(2002, "EPBD 2002/91/EC"), (2008, "EPCs in England and Wales"), (2010, "EPBD recast 2010/31/EU"), (2015, "UN SDGs; MEES regulations"),
              (2020, "Renovation Wave"), (2024, "EPBD recast 2024/1275")]
    res_ev = [(2006, "UHI effect on cooling load (London)"), (2012, "LCZ scheme; GIS mapping of EPCs"), (2014, "LiDAR-based building age (RF)"),
              (2020, "National BER prediction with GIS (Ireland); overhead imagery"), (2023, "SVI + aerial + LST for EPC bands; PointER"),
              (2025, "Transfer learning with street view; VLMs for EPC")]
    fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=300)
    for evs, y, c, lab in [(data_ev, 2, "#2f5d8a", "Sensors and open data"), (pol_ev, 1, "#b05a2a", "Policy"), (res_ev, 0, "#3d8a4b", "Research in corpus")]:
        ax.hlines(y, 1982, B["last_year"] + 0.5, color=c, lw=1.2, alpha=0.4)
        ax.text(1981.5, y, lab, ha="right", va="center", fontsize=7, color=c, weight="bold")
        for i, (yr, t) in enumerate(evs):
            off = [0.18, -0.18, 0.40, -0.40][i % 4]
            ax.plot(yr, y, "o", color=c, ms=3.5); ax.plot([yr, yr], [y, y + off * 0.8], color=c, lw=0.4, alpha=0.6)
            ax.text(yr, y + off, f"{yr}: " + textwrap.fill(t, 22), ha="center", va="center", fontsize=4.9,
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))
    by = {int(k): v for k, v in B["by_year"].items()}; xs = sorted(by)
    ax2 = ax.twinx(); ax2.fill_between(xs, [by[x] for x in xs], color="#999", alpha=0.18, step="mid")
    ax2.set_ylabel("Corpus documents per year", fontsize=6.5, color="#777"); ax2.tick_params(labelsize=6, colors="#777"); ax2.spines["top"].set_visible(False)
    ax.set_ylim(-0.6, 2.6); ax.set_yticks([]); ax.set_xlim(1980, B["last_year"] + 2); ax.spines["left"].set_visible(False)
    fig.tight_layout(); fig.savefig(fig_ / "fig09_timeline.png", bbox_inches="tight"); plt.close(fig)

    # ---------------- Fig 10 evidence map
    dec = read_csv(P["out"] / "screening_decisions.csv")
    C = dec[dec["decision"] == "Included (core)"].fillna("")
    mods = ["GIS / cadastral", "Climate / LCZ / UHI", "Thermal / LST", "LiDAR / 3D", "Aerial / UAV", "Optical satellite", "Street-level imagery", "SAR"]
    tgts = ["Heating / cooling demand", "Energy use intensity / benchmark", "Envelope / heat loss", "Retrofit potential", "Rating / label"]
    mets = ["Physics-based simulation / UBEM", "Statistical / spatial statistics", "Machine / deep learning"]
    mat = lambda a, al, b, bl: np.array([[((C[a].str.contains(x, regex=False)) & (C[b].str.contains(y, regex=False))).sum() for y in bl] for x in al])
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.4), dpi=300, gridspec_kw={"width_ratios": [1.1, 0.8]})
    for ax, (M, yl_, xl_, yl, xl) in zip(axes, [(mat("modality", mods, "target", tgts), mods, tgts, "Data modality", "Energy-efficiency target"),
                                                (mat("target", tgts, "method", mets), tgts, mets, "Energy-efficiency target", "Method family")]):
        ax.imshow(M, cmap="Blues", aspect="auto")
        ax.set_xticks(range(len(xl_))); ax.set_xticklabels([textwrap.fill(x, 14) for x in xl_], fontsize=5.6)
        ax.set_yticks(range(len(yl_))); ax.set_yticklabels(yl_, fontsize=6); ax.set_xlabel(xl, fontsize=6.5); ax.set_ylabel(yl, fontsize=6.5)
        for i in range(M.shape[0]):
            for j in range(M.shape[1]):
                ax.text(j, i, M[i, j], ha="center", va="center", fontsize=5.8, color="white" if M[i, j] > M.max() * 0.55 else "black")
    axes[0].set_title("(a) Modality x target", fontsize=7, loc="left"); axes[1].set_title("(b) Target x method", fontsize=7, loc="left")
    fig.tight_layout(); fig.savefig(fig_ / "fig10_evidence_map.png"); plt.close(fig)

    # ---------------- Fig 11 performance
    Pp = F[pd.to_numeric(F["value"], errors="coerce").notna() & F["metric"].isin(["Macro-F1", "F1", "F1 (micro)", "Accuracy", "Balanced accuracy", "Precision", "AUC", "R2"])].copy()
    Pp["value"] = pd.to_numeric(Pp["value"])
    Pp["tt"] = pd.Categorical(Pp["target_type"], ["Binary", "Multi-class", "Ordinal (A-G)", "Continuous"]); Pp = Pp.sort_values(["tt", "value"])
    fig, ax = plt.subplots(figsize=(7.2, max(2.4, 0.26 * len(Pp) + 0.8)), dpi=300)
    for i, (_, r) in enumerate(Pp.iterrows()):
        ax.barh(i, r["value"], color=VCOL.get(r["validation"], "#999"), height=0.62)
        ax.text(r["value"] + 0.01, i, f"{r['metric']} {r['value']:.2f}", va="center", fontsize=5.6)
    ax.set_yticks(range(len(Pp))); ax.set_yticklabels([f"{s} ({int(y)})  [{t}]" for s, y, t in zip(Pp["study"], Pp["year"], Pp["target_type"])], fontsize=6)
    ax.set_xlim(0, 1.12); ax.set_xlabel("Reported headline metric (as reported; not comparable across metrics or class counts)")
    for k in Pp["validation"].unique():
        ax.barh([], [], color=VCOL.get(k, "#999"), label=k)
    ax.legend(frameon=False, fontsize=6, loc="lower right", title="Validation design", title_fontsize=6)
    fig.tight_layout(); fig.savefig(fig_ / "fig11_performance.png"); plt.close(fig)

    # ---------------- Fig 12 validation over time
    V = F[~F["validation"].fillna("").isin(["Not applicable", "Not applicable (zero-shot)", ""])]
    tab = pd.crosstab(V["year"].astype(int), V["validation"])
    tab = tab[[c for c in VCOL if c in tab.columns]]
    fig, ax = plt.subplots(figsize=(5.2, 2.8), dpi=300); bottom = np.zeros(len(tab))
    for c in tab.columns:
        ax.bar(tab.index.astype(str), tab[c], bottom=bottom, color=VCOL[c], label=c); bottom += tab[c].values
    ax.set_ylabel("Studies"); ax.set_xlabel("Publication year"); ax.legend(frameon=False, fontsize=6, bbox_to_anchor=(1, 1), loc="upper left")
    fig.tight_layout(); fig.savefig(fig_ / "fig12_validation_time.png"); plt.close(fig)

    # ---------------- Fig 13 roadmap
    fig, ax = canvas(7.2, 3.0)
    lanes = [("Near term (1-2 years)", "#dbe9f6", ["G1 Open multi-city EO-EPC benchmark with fixed splits", "G2 Spatially blocked and held-out-city tests as default", "G3 Ordinal metrics: within-one-band, MAE in bands, QWK"]),
             ("Medium term (2-4 years)", "#e3f1e0", ["G4 Label-noise-aware learning; date-matched imagery", "G5 Multimodal fusion incl. SAR and open thermal; non-EU regions", "G7 Calibrated uncertainty for decision thresholds"]),
             ("Long term (4+ years)", "#f7e6da", ["G6 Efficiency under extreme heat and cold events", "G8 Temporal monitoring of retrofit from repeat EO", "Policy-grade, audited models for MEPS/MEES screening"])]
    for i, (t, c, items) in enumerate(lanes):
        x = 0.02 + i * 0.33
        ax.add_patch(FancyBboxPatch((x, 0.06), 0.30, 0.86, boxstyle="round,pad=0.004,rounding_size=0.02", fc=c, ec="none"))
        ax.text(x + 0.15, 0.86, t, ha="center", fontsize=8, weight="bold")
        for j, it in enumerate(items):
            box(ax, x + 0.015, 0.58 - j * 0.24, 0.27, 0.19, it, fs=6.2, wrap=38)
        if i < 2:
            arrow(ax, x + 0.30, 0.5, x + 0.33, 0.5)
    fig.savefig(fig_ / "fig13_roadmap.png"); plt.close(fig)

    # ---------------- Graphical abstract
    fig = plt.figure(figsize=(13.28, 5.31), dpi=100); ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    steps = [("Earth observation\n& geospatial data", "street view, aerial, LiDAR,\nthermal/LST, GIS, climate"), ("Link to buildings", "UPRN, footprints,\npoint vs zonal"),
             ("Estimate efficiency", "binary / A-G / SAP\nML, DL, VLM"), ("Validate", "random vs spatial\nvs temporal"), ("Policy use", "retrofit targeting,\nMEES / EPBD")]
    for i, (t, d) in enumerate(steps):
        x = 0.02 + i * 0.196
        ax.add_patch(FancyBboxPatch((x, 0.45), 0.17, 0.45, boxstyle="round,pad=0.005,rounding_size=0.03", fc=plt.cm.Blues(0.15 + 0.12 * i), ec="none"))
        ax.text(x + 0.085, 0.76, t, ha="center", va="center", fontsize=15, weight="bold"); ax.text(x + 0.085, 0.57, d, ha="center", va="center", fontsize=12)
        if i < 4:
            arrow(ax, x + 0.17, 0.67, x + 0.196, 0.67)
    ml = S["core_method"]["Machine / deep learning"]["pct"]
    temporal = "No study used a temporal hold-out" if Fs["n_temporal"] == 0 else f"{Fs['n_temporal']} used a temporal hold-out"
    facts = [f"{S['n_screened']:,} records mapped", f"{S['n_core']:,} core studies; ML in {ml}%",
             f"Only {Fs['n_heldout']} of {Fs['n_predictive']} predictive rating studies\ntested on an unseen city or area", temporal]
    for i, f_ in enumerate(facts):
        ax.text(0.13 + i * 0.245, 0.2, f_, ha="center", va="center", fontsize=14, color="#1f3b5c", bbox=dict(boxstyle="round,pad=0.5", fc="#f4f6f9", ec="#9fb1c7"))
    fig.savefig(fig_ / "ga.png"); plt.close(fig)
    return {"figures": sorted(p.name for p in fig_.glob("*.png"))}
