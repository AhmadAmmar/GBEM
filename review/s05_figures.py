"""Stage 5 - PRISMA diagram, schematic and synthesis figures.

Figures: fig01_framework, fig02_prisma, fig03_workflow, fig09_timeline, fig10_evidence_map,
         fig11_performance, fig12_validation_time, fig13_roadmap, ga (graphical abstract, 1328x531 px)
Feeds : Figs 1-3 and 9-13 and the graphical abstract.
"""
import textwrap
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Patch
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


def screening_flow(cfg, P, I, S, Fs):
    """Decision sequence from the database search to the core set and focused subset (database records), with counts.

    The order of the steps is the order of the rules in s01_screen.rule_decision; each excluded record is counted at
    the first criterion it does not meet. The description of the search components has to follow the query file.
    """
    dec = read_csv(P["out"] / "screening_decisions.csv")
    tp = P["out"] / "stats_triage.json"     # triage of the candidates (stage 8), if it has been run
    tri = ""
    if tp.exists() and Fs["n_pending"]:
        T = load(tp)
        tri = (f"; ordered for full-text screening by triage rules: {T['triage']['Likely']:,} likely, {T['triage']['Unclear']:,} unclear, "
               f"{T['triage']['Unlikely']:,} unlikely; full text read for {T['n_with_fulltext']:,}")
    D = dec[dec["arm"].fillna("database") == "database"]
    rr, rd = D["rule_reason"].fillna(""), D["rule_decision"]
    n = lambda *keys: int(sum(rr.str.startswith(k).sum() for k in keys))
    n_type, n_rev = int((rd == "Excluded (record type)").sum()), int((rd == "Review (umbrella)").sum())
    n_rating = int(((rd == "Included (core)") & (D["route"] == "rating estimation")).sum())
    n_geo = int(((rd == "Included (core)") & (D["route"] != "rating estimation")).sum())
    yrs, types = cfg.SEARCH["years"], ", ".join(t.lower() for t in cfg.SEARCH["doc_types"])
    steps = [   # question, text of the side box, records leaving here, kind of side box
        ("Unique record?", "Duplicates removed\n(record identifier, DOI, title and year)", I["n_duplicates"], "out"),
        ("Eligible record type and year?", "Excluded: retracted, erratum, other type or year", n_type, "out"),
        ("Primary study?\n(not a review by document type or title)", "Reviews set aside as context (umbrella evidence)", n_rev, "aside"),
        ("Building or building stock\nin title or abstract?", "Excluded: no building or building stock", n("No building"), "out"),
        ("Energy-efficiency outcome\nin title or abstract?", f"Excluded: outcome not related to building energy efficiency {n('Outcome not related'):,}; "
         f"thermal comfort only {n('Outcome is thermal comfort'):,}; renewable or solar potential only {n('Renewable'):,}",
         n("Outcome not related", "Outcome is thermal comfort", "Renewable"), "out"),
        ("Energy rating, label or class estimated?", "Included: rating-estimation route\n(no geospatial term required)", n_rating, "in"),
        ("Geospatial or remote-sensing data or method named\nin title, abstract or author keywords?",
         f"Excluded: urban climate or urban form named only as setting {n('Urban climate'):,}; no geospatial term {n('No geospatial'):,}; "
         f"indoor sensing or laboratory {n('Indoor'):,}; term in index keywords only {n('Geospatial term in'):,}",
         n("Urban climate", "No geospatial", "Indoor", "Geospatial term in"), "out"),
        ("Wide-area data source,\nor close-range sensing of many buildings?", "Excluded: single building or component", n("Single building"), "out"),
        ("Buildings the subject of the study?", "Excluded: buildings mentioned only in passing", n("Buildings mentioned"), "out"),
    ]
    fig, ax = canvas(7.2, 9.4)
    LX, LW, RX, RW, H, DY = 0.035, 0.43, 0.555, 0.41, 0.046, 0.070
    box(ax, LX, 0.898, RX + RW - LX, 0.094,
        f"Scopus search of {I['search_date']}, four components joined by OR:\n"
        "(1) built object AND energy outcome AND remote-sensing or geospatial term, in titles, abstracts and keywords; "
        "(2) the same three blocks with broader terms, in titles only; (3) urban building energy modelling named; "
        "(4) built object AND rating or certificate term AND data-analysis method term.\n"
        f"Limits: {yrs[0]}-{yrs[1]}; {types}; English.   Records identified: n = {I['n_identified']:,}", fc="#f4f8fc", fs=6.0, wrap=118)
    left, y, top = I["n_identified"], 0.898, 0.898
    for i, (q, side, k, kind) in enumerate(steps):
        y = 0.835 - i * DY
        box(ax, LX, y, LW, H, q, fc="#ffffff", fs=6.0, wrap=58)
        arrow(ax, LX + LW / 2, top, LX + LW / 2, y + H)
        fc = {"out": "#fbeeee", "aside": "#fff8e6", "in": "#e6f2e6"}[kind]
        box(ax, RX, y - 0.003, RW, H + 0.006, f"{side}\nn = {k:,}", fc=fc, fs=5.2, wrap=66)
        arrow(ax, LX + LW, y + H / 2, RX, y + H / 2)
        ax.text((LX + LW + RX) / 2, y + H / 2 + 0.006, "yes" if kind == "in" else "no", ha="center", fontsize=5.4, color="#444")
        left -= k
        ax.text(LX + LW / 2 + 0.008, y - (DY - H) / 2, ("no" if kind == "in" else "yes") + f"   {left:,} remain", ha="left", va="center", fontsize=5.4, color="#444")
        top = y
    y = top - DY
    box(ax, LX, y, LW, H, f"Included: geospatial data or method route\nn = {n_geo:,}", fc="#e6f2e6", fs=6.0, wrap=58)
    arrow(ax, LX + LW / 2, top, LX + LW / 2, y + H)
    ver = (f"{S['n_verified_by_reviewer']:,} decisions verified by the first reviewer" if S["n_verified_by_reviewer"]
           else "every rule decision is to be verified by the reviewer")
    box(ax, LX, y - 0.10, RX + RW - LX, 0.078,
        f"Core systematic set: {n_geo:,} + {n_rating:,} = {S.get('n_core_db', n_geo + n_rating):,} database records, plus {S.get('n_core_other', 0):,} records "
        f"identified by other methods and screened with the same rules: n = {S['n_core']:,}\n"
        f"{ver[0].upper() + ver[1:]}, starting with decisions that rest on weak evidence (n = {S.get('n_to_verify', 0):,}); "
        + (f"a second reviewer screens a random sample (n = {S.get('n_dual_sample', 0):,}) and Cohen's kappa is reported"
           if S.get("dual_screening", True) else "screening is by a single reviewer, without independent second screening"),
        fc="#e6f2e6", fs=5.8, wrap=124)
    arrow(ax, LX + LW / 2, y, LX + LW / 2, y - 0.022)
    box(ax, LX, y - 0.195, RX + RW - LX, 0.066,
        f"Focused subset: core studies coded with a rating or label target are candidates; inclusion is decided on the full text "
        f"(building-level estimation of an energy rating, label or score, or data designed for it): n = {Fs['n_focused']} "
        f"({Fs['n_pending']:,} candidates awaiting a decision{tri})", fc="#dcebdc", fs=5.8, wrap=124)
    arrow(ax, LX + LW / 2, y - 0.10, LX + LW / 2, y - 0.129)
    for ext in ("png", "pdf"):
        fig.savefig(P["fig"] / f"figS_screening_rules.{ext}")
    plt.close(fig)
    return left


def run(cfg, P):
    I, S, B, Fs = (load(P["out"] / f) for f in ["stats_ingest.json", "stats_screening.json", "stats_biblio.json", "stats_focused.json"])
    screening_flow(cfg, P, I, S, Fs)
    F = read_csv(P["out"] / "focused_final.csv")
    supp = read_csv(P["inputs"] / cfg.HUMAN["supplementary_studies"])
    fig_ = P["fig"]

    # ---------------- PRISMA 2020 (databases: left and centre; other methods: right)
    fig, ax = canvas(7.2, 7.0)
    for y0, y1, lab in [(0.81, 0.97, "Identification"), (0.31, 0.80, "Screening"), (0.02, 0.30, "Included")]:
        ax.add_patch(FancyBboxPatch((0.005, y0), 0.035, y1 - y0, boxstyle="round,pad=0.002", fc="#dbe7f3", ec="none"))
        ax.text(0.0225, (y0 + y1) / 2, lab, rotation=90, ha="center", va="center", fontsize=7, weight="bold")
    L, M, R, W = 0.05, 0.345, 0.645, 0.27
    ax.text(L + (M + W - L) / 2, 0.985, "Identification of studies via databases", ha="center", fontsize=7, weight="bold")
    ax.text(R + W / 2 + 0.02, 0.985, "Identification via other methods", ha="center", fontsize=7, weight="bold")
    ident = f"Records identified from Scopus\nsearch of {I['search_date']}\n({I['field']})\nn = {I['n_scopus']:,}"
    for e in I.get("earlier_searches", []):
        ident += f"\nsearch of {e['date']}, {e['field']}:\nn = {e['n']:,}"
    if I["n_wos"]:
        ident += f"\nWeb of Science: n = {I['n_wos']:,}"
    box(ax, L, 0.83, W, 0.13, ident, fc="#f4f8fc", fs=6.0, wrap=46)
    dup_label = "duplicates within and between searches" if I.get("earlier_searches") or I["n_wos"] else "duplicate records"
    box(ax, M, 0.83, W, 0.13, f"Removed before screening:\n{dup_label}:\nn = {I['n_duplicates']:,}\n"
        f"ineligible record type or years, errata and retracted articles: n = {S['n_removed_record_type']:,}", fs=6.0, wrap=44)
    arrow(ax, L + W, 0.895, M, 0.895)
    oth = S.get("n_other_identified", 0)
    box(ax, R, 0.83, W + 0.04, 0.13, "Records identified from earlier scoping searches, the authors' previous reports, presentations, reference "
        f"library and PDF library, citation searching and expert suggestion, and not retrieved by the search: n = {oth:,}", fc="#f4f8fc", fs=6.0, wrap=54)
    box(ax, L, 0.66, W, 0.10, f"Records screened (title, abstract, keywords)\nn = {S['n_screened']:,} = bibliometric corpus", fc="#f4f8fc", fs=6.0, wrap=48)
    arrow(ax, L + W / 2, 0.83, L + W / 2, 0.76)
    exc = "\n".join(f"{k}: {v:,}" for k, v in S["excluded_reasons"].items())
    box(ax, M, 0.50, W, 0.28, f"Records excluded (n = {S['n_excluded_ta']:,}):\n{exc}", wrap=56, fs=4.9 if len(S["excluded_reasons"]) > 7 else 5.4)
    arrow(ax, L + W, 0.71, M, 0.66)
    box(ax, L, 0.51, W, 0.09, f"Review articles set aside for umbrella/context use\nn = {S['n_reviews']:,}", fc="#fff8e6", fs=6.0, wrap=48)
    arrow(ax, L + W / 2, 0.66, L + W / 2, 0.60)
    ver = f"verified by reviewer: {S['n_verified_by_reviewer']:,}" if S["n_verified_by_reviewer"] else "reviewer verification pending"
    box(ax, L, 0.34, W, 0.11, f"Primary studies eligible at title/abstract stage\nn = {S.get('n_core_db', S['n_core']):,}\n({ver})", fc="#f4f8fc", fs=6.0, wrap=48)
    arrow(ax, L + W / 2, 0.51, L + W / 2, 0.45)
    box(ax, R, 0.66, W + 0.04, 0.10, f"Records screened with the same criteria\nn = {S.get('n_other_screened', 0):,}", fc="#f4f8fc", fs=6.0, wrap=50)
    arrow(ax, R + W / 2 + 0.02, 0.83, R + W / 2 + 0.02, 0.76)
    box(ax, R, 0.49, W + 0.04, 0.13, f"Excluded: record type (book, report, dataset, thesis, web) n = {S.get('n_other_record_type', 0):,}; "
        f"title/abstract n = {S.get('n_other_excluded', 0):,}; review articles set aside n = {S.get('n_other_reviews', 0):,}", fs=5.8, wrap=54)
    arrow(ax, R + W / 2 + 0.02, 0.66, R + W / 2 + 0.02, 0.62)
    box(ax, R, 0.34, W + 0.04, 0.11, f"Primary studies eligible\nn = {S.get('n_core_other', 0):,}", fc="#f4f8fc", fs=6.0, wrap=50)
    arrow(ax, R + W / 2 + 0.02, 0.49, R + W / 2 + 0.02, 0.45)
    box(ax, L, 0.15, W, 0.12, f"Core systematic set\nn = {S['n_core']:,} studies\n({S.get('n_core_db', S['n_core']):,} database + {S.get('n_core_other', 0):,} other methods)",
        fc="#e6f2e6", fs=6.2, wrap=48)
    arrow(ax, L + W / 2, 0.34, L + W / 2, 0.27); arrow(ax, R + 0.02, 0.34, L + W, 0.24)
    box(ax, R, 0.03, W + 0.04, 0.14, f"Focused subset: building-level estimation of energy-efficiency ratings, labels or scores\n"
        f"n = {Fs['n_focused']} ({Fs['n_focused_db']} database + {Fs['n_focused_other']} other methods)", fc="#e6f2e6", fs=6.0, wrap=52)
    arrow(ax, L + W, 0.18, R, 0.10)
    fig.savefig(fig_ / "fig02_prisma.png"); fig.savefig(fig_ / "fig02_prisma.pdf"); plt.close(fig)

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
        ax.set_xticks(range(len(xl_))); ax.set_xticklabels([textwrap.fill(x, 10, break_long_words=False) for x in xl_], fontsize=5.6)
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
    handles = [Patch(color=VCOL.get(k, "#999"), label=k) for k in Pp["validation"].unique()]
    ax.legend(handles=handles, frameon=False, fontsize=6, loc="lower right", title="Validation design", title_fontsize=6)
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
