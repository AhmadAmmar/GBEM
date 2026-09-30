"""Stage 2 - bibliometric (science-mapping) analysis of the screened corpus.

Output: outputs/stats_biblio.json, top_sources.csv, countries_affiliation.csv, keyword_frequencies.csv,
        thematic_map.csv, top_cited.csv, top_cited_references.csv
Figures: fig04_annual, fig05_map, fig06_cooccurrence, fig07_keywords_blocks, fig08_thematic
Feeds : Section 3 (all subsections), Table 6, Figs 4-8, Appendix F.
"""
import collections, itertools, re
import numpy as np, pandas as pd, networkx as nx
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from common import BLOCKS, CNORM, norm_kw, dump, read_csv

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.spines.top": False, "axes.spines.right": False})
COLS = plt.cm.tab10.colors


def aff_countries(a):
    if not isinstance(a, str):
        return []
    out = []
    for part in a.split(";"):
        c = CNORM.get(part.split(",")[-1].strip(), part.split(",")[-1].strip())
        if c and len(c) < 40:
            out.append(c)
    return out


def block_of(k):
    for b in ["C. Remote sensing and geospatial", "D. Methods and validation", "B. Energy performance", "A. Built form and urban context"]:
        if re.search(BLOCKS[b], k.lower()):
            return b
    return None


def run(cfg, P):
    rec = read_csv(P["out"] / "records.csv")
    dec = read_csv(P["out"] / "screening_decisions.csv")[["rid", "decision", "study_country"]]
    df = rec.merge(dec, on="rid")
    df = df[df["decision"] != "Excluded (record type)"].copy()
    df["year"] = df["year"].astype(int)
    core = df["decision"].eq("Included (core)")
    last_year = int(df["year"].max())
    S = {"n_corpus": int(len(df)), "n_core": int(core.sum()), "last_year": last_year, "search_date": cfg.SEARCH["search_date"]}

    # ---------- annual production
    yr, yc = df["year"].value_counts().sort_index(), df.loc[core, "year"].value_counts().sort_index()
    S["by_year"] = {int(k): int(v) for k, v in yr.items()}
    base = 2010 if yr.get(2010, 0) > 0 else int(yr.index.min())
    end = last_year - 1   # last year is usually incomplete
    S["cagr_years"] = [base, end]
    S["cagr_pct"] = round(100 * ((yr.get(end, 0) / yr.get(base, 1)) ** (1 / max(end - base, 1)) - 1), 1)
    S["share_since_2020"] = round(100 * df["year"].ge(2020).mean(), 1)
    S["core_share_since_2020"] = round(100 * df.loc[core, "year"].ge(2020).mean(), 1)
    S["peak_year"], S["peak_n"] = int(yr.idxmax()), int(yr.max())
    fig, ax = plt.subplots(figsize=(6.6, 3.0), dpi=300)
    years = np.arange(int(df["year"].min()), last_year + 1)
    ax.bar(years, [yr.get(y, 0) for y in years], color="#9fb8d8", label=f"Bibliometric corpus (n = {len(df):,})")
    ax.bar(years, [yc.get(y, 0) for y in years], color="#2f5d8a", label=f"Core systematic set (n = {int(core.sum()):,})")
    # milestone labels sit above the tallest bar on two alternating levels, so they never cover bars or each other
    miles = [(2002, "EPBD\n2002/91/EC"), (2008, "EPCs E&W\n2007-08"), (2010, "EPBD recast\n2010/31/EU"),
             (2015, "Sentinel-2A;\nEA open LiDAR"), (2018, "ECOSTRESS;\nMEES in force"), (2024, "EPBD recast\n2024/1275")]
    for i, (y, lab) in enumerate(m for m in miles if m[0] in years):
        ax.annotate(lab, (y, yr.get(y, 0)), xytext=(y, yr.max() * (1.10 if i % 2 == 0 else 1.30)), ha="center", va="bottom",
                    fontsize=5.8, arrowprops=dict(arrowstyle="-", color="#888", lw=0.5), color="#444")
    ax.set_ylim(0, yr.max() * 1.55)
    ax.text(last_year, yr.get(last_year, 0) + yr.max() * 0.02, "partial\nyear", ha="center", fontsize=5.5, color="#666")
    ax.set_xlabel("Publication year"); ax.set_ylabel("Documents"); ax.legend(frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2)
    fig.tight_layout(); fig.savefig(P["fig"] / "fig04_annual.png"); plt.close(fig)

    # ---------- sources and document types
    src = df.groupby("source_title").agg(docs=("rid", "size"), cites=("cited_by", "sum"),
                                         core=("decision", lambda s: int((s == "Included (core)").sum())))
    src = src.sort_values(["docs", "cites"], ascending=False)
    src.head(10).to_csv(P["out"] / "top_sources.csv", encoding="utf-8-sig")
    S["top_sources"] = src.head(10).reset_index().to_dict("records")
    S["n_sources"] = int(df["source_title"].nunique())
    cum = df["source_title"].value_counts().cumsum()
    S["sources_for_third"] = int((cum < len(df) / 3).sum() + 1)
    S["doc_types"] = df["doc_type"].value_counts().to_dict()

    # ---------- countries
    df["aff_c"] = df["affiliations"].map(aff_countries)
    cnt = collections.Counter(c for l in df["aff_c"] for c in set(l))
    pd.Series(cnt).sort_values(ascending=False).to_csv(P["out"] / "countries_affiliation.csv", header=["docs"], encoding="utf-8-sig")
    S["countries_top"] = {k: {"n": v, "pct": round(100 * v / len(df), 1)} for k, v in cnt.most_common(10)}
    S["n_countries_aff"] = len(cnt)
    S["intl_collab_pct"] = round(100 * df["aff_c"].map(lambda l: len(set(l)) > 1).mean(), 1)

    # ---------- citations
    top = df.sort_values("cited_by", ascending=False).head(10)[["authors", "title", "year", "source_title", "cited_by", "doi", "decision"]]
    top.to_csv(P["out"] / "top_cited.csv", index=False, encoding="utf-8-sig"); S["top_cited"] = top.to_dict("records")
    topc = df[core].sort_values("cited_by", ascending=False).head(10)[["authors", "title", "year", "cited_by", "doi"]]
    S["top_cited_core"] = topc.to_dict("records")
    S["median_citations"] = float(df["cited_by"].median())
    cs = sorted(df["cited_by"].fillna(0), reverse=True)
    S["h_index"] = int(sum(c >= i + 1 for i, c in enumerate(cs)))
    # local citations: references cited most often by corpus documents (co-citation seed list)
    refs = collections.Counter()
    for r in df["references"].dropna():
        for x in str(r).split(";"):
            key = re.sub(r"\s+", " ", x.strip().lower())[:90]
            if len(key) > 25:
                refs[key] += 1
    pd.DataFrame(refs.most_common(25), columns=["reference (truncated)", "citing_docs"]).to_csv(
        P["out"] / "top_cited_references.csv", index=False, encoding="utf-8-sig")
    S["has_references"] = bool(len(refs))

    # ---------- keywords
    df["kw"] = df["author_keywords"].fillna("").map(lambda s: sorted({norm_kw(k) for k in str(s).split(";") if k.strip()}))
    kwc = collections.Counter(k for l in df["kw"] for k in l)
    pd.Series(kwc).sort_values(ascending=False).to_csv(P["out"] / "keyword_frequencies.csv", header=["docs"], encoding="utf-8-sig")
    S["n_keywords_unique"], S["docs_with_kw"] = len(kwc), int(df["kw"].map(bool).sum())
    S["top_keywords"] = dict(kwc.most_common(30))

    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.6), dpi=300)
    S["block_top"] = {}
    for i, (ax, b) in enumerate(zip(axes.flat, BLOCKS)):
        items = [(k, v) for k, v in kwc.most_common() if block_of(k) == b][:12]
        S["block_top"][b] = items[:8]
        ax.barh([k for k, _ in items][::-1], [v for _, v in items][::-1], color=["#3b6ea5", "#c0504d", "#4f9a55", "#8064a2"][i])
        ax.set_title(b, fontsize=7, loc="left"); ax.tick_params(labelsize=6); ax.set_xlabel("Documents", fontsize=6)
    fig.tight_layout(); fig.savefig(P["fig"] / "fig07_keywords_blocks.png"); plt.close(fig)

    # co-occurrence network (threshold scales with corpus size)
    thr = max(cfg.MIN_KEYWORD_OCC, int(round(len(df) / 140)))
    G = nx.Graph()
    for k, v in kwc.items():
        if v >= thr:
            G.add_node(k)
    for l in df["kw"]:
        l = [k for k in l if k in G]
        for a, b in itertools.combinations(l, 2):
            G.add_edge(a, b, weight=G[a][b]["weight"] + 1 if G.has_edge(a, b) else 1)
    G.remove_nodes_from([n for n in list(G) if G.degree(n) == 0])
    comms = sorted(nx.community.louvain_communities(G, weight="weight", seed=7), key=lambda c: -sum(kwc[k] for k in c))
    cid = {k: i for i, c in enumerate(comms) for k in c}
    S["network"] = {"min_occ": thr, "nodes": G.number_of_nodes(), "edges": G.number_of_edges(), "n_clusters": len(comms),
                    "clusters": [sorted(c, key=lambda k: -kwc[k])[:10] for c in comms]}
    pos = nx.spring_layout(G, weight="weight", seed=3, k=0.9)
    fig, ax = plt.subplots(figsize=(7.0, 5.2), dpi=300); ax.axis("off")
    for a, b, d in G.edges(data=True):
        if d["weight"] >= 2:
            ax.plot(*zip(pos[a], pos[b]), color="#bbbbbb", lw=0.25 + 0.1 * d["weight"], alpha=0.5, zorder=1)
    mx = max(kwc[n] for n in G) if len(G) else 1
    for n in G:
        ax.scatter(*pos[n], s=12 + 250 * kwc[n] / mx, color=COLS[cid[n] % 10], edgecolor="white", lw=0.4, zorder=2)
    for n in sorted(G, key=lambda k: -kwc[k])[:50]:
        ax.text(pos[n][0], pos[n][1], n, fontsize=4.8 + 4 * kwc[n] / mx, ha="center", va="center", zorder=3)
    fig.tight_layout(); fig.savefig(P["fig"] / "fig06_cooccurrence.png"); plt.close(fig)

    # thematic map + evolution
    rows = []
    for i, c in enumerate(comms):
        c = set(c)
        inw = sum(d["weight"] for a, b, d in G.edges(data=True) if a in c and b in c)
        ext = sum(d["weight"] for a, b, d in G.edges(data=True) if (a in c) != (b in c))
        rows.append({"cluster": i + 1, "label": ", ".join(sorted(c, key=lambda k: -kwc[k])[:3]),
                     "size": sum(kwc[k] for k in c), "centrality": 10 * ext, "density": 100 * inw / max(len(c), 1)})
    tm = pd.DataFrame(rows); tm.to_csv(P["out"] / "thematic_map.csv", index=False, encoding="utf-8-sig")
    S["thematic_map"] = tm.to_dict("records")
    ev = {}
    for a, b in cfg.PERIODS:
        sub = df[df["year"].between(a, b)]
        c = collections.Counter(k for l in sub["kw"] for k in l)
        ev[f"{a}-{min(b, last_year)}"] = {"n": int(len(sub)), "top": c.most_common(12)}
    S["evolution"] = ev
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.9), dpi=300, gridspec_kw={"width_ratios": [1, 1.25]})
    ax = axes[0]
    ax.axhline(tm["density"].median(), color="#999", lw=0.6, ls="--"); ax.axvline(tm["centrality"].median(), color="#999", lw=0.6, ls="--")
    ax.scatter(tm["centrality"], tm["density"], s=tm["size"] / tm["size"].max() * 900 + 30, color=[COLS[i % 10] for i in range(len(tm))], alpha=0.75)
    for _, r in tm.iterrows():
        ax.text(r["centrality"], r["density"], r["label"].replace(", ", "\n"), fontsize=4.6, ha="center", va="center")
    xr = max(tm["centrality"].max() - tm["centrality"].min(), 1); yr_ = max(tm["density"].max() - tm["density"].min(), 1)
    ax.set_xlim(tm["centrality"].min() - 0.6 * xr, tm["centrality"].max() + 0.45 * xr)
    ax.set_ylim(tm["density"].min() - 0.3 * yr_, tm["density"].max() + 0.3 * yr_)
    ax.set_xlabel("Centrality (external link strength)"); ax.set_ylabel("Density (internal link strength)")
    for (x, y, t) in [(0.98, 0.98, "Motor themes"), (0.02, 0.98, "Niche themes"), (0.02, 0.02, "Emerging or\ndeclining"), (0.98, 0.02, "Basic themes")]:
        ax.text(x, y, t, transform=ax.transAxes, ha="right" if x > 0.5 else "left", va="top" if y > 0.5 else "bottom", fontsize=6, color="#555", style="italic")
    ax.set_title("(a) Thematic map (clusters of Fig. 6)", fontsize=7, loc="left")
    ax = axes[1]; ax.axis("off"); ax.set_title("(b) Most frequent author keywords by period", fontsize=7, loc="left", pad=22)
    allk = {}
    for j, (per, d) in enumerate(ev.items()):
        ax.text(j / 3 + 0.02, 0.97, f"{per}\n(n = {d['n']:,})", fontsize=6.3, weight="bold", va="top")
        for i, (k, v) in enumerate(d["top"][:12]):
            y = 0.86 - i * 0.07; allk.setdefault(k, []).append((j, y))
            ax.text(j / 3 + 0.02, y, f"{k} ({v})", fontsize=5.2, va="center")
    for k, pts in allk.items():
        for (j1, y1), (j2, y2) in zip(pts, pts[1:]):
            if j2 == j1 + 1:
                ax.plot([j1 / 3 + 0.30, j2 / 3 + 0.015], [y1, y2], color="#9aa", lw=0.5)
    fig.tight_layout(); fig.savefig(P["fig"] / "fig08_thematic.png"); plt.close(fig)

    # ---------- map of core study areas
    sc = df.loc[core, "study_country"].fillna("").replace("", np.nan).dropna().value_counts()
    sc.to_csv(P["out"] / "core_study_countries.csv", header=["studies"], encoding="utf-8-sig")
    try:
        import geopandas as gpd, cartopy.io.shapereader as shpreader
        w = gpd.read_file(shpreader.natural_earth(resolution="110m", category="cultural", name="admin_0_countries"))
        fix = {"United States": "United States of America", "Czech Republic": "Czechia"}
        w["n"] = w["ADMIN"].map({fix.get(k, k): v for k, v in sc.items()}).fillna(0)
        fig, ax = plt.subplots(figsize=(7.2, 3.6), dpi=300)
        w[w["ADMIN"] != "Antarctica"].plot(ax=ax, column="n", cmap="Blues", edgecolor="#999", linewidth=0.2, vmin=0, legend=True,
                                           legend_kwds={"label": "Core studies (study area)", "shrink": 0.6})
        ax.set_axis_off()
        ins = fig.add_axes([0.02, 0.08, 0.26, 0.42])
        w.plot(ax=ins, column="n", cmap="Blues", edgecolor="#777", linewidth=0.3, vmin=0, vmax=w["n"].max())
        ins.set_xlim(-12, 30); ins.set_ylim(35, 62); ins.set_xticks([]); ins.set_yticks([]); ins.set_title("Europe", fontsize=6)
        fig.savefig(P["fig"] / "fig05_map.png", bbox_inches="tight"); plt.close(fig)
        S["map"] = "ok"
    except Exception as e:
        S["map"] = f"failed: {e}"
    dump(S, P["out"] / "stats_biblio.json")
    return S
