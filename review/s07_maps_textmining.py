"""Stage 7 - supplementary bibliometrics: word clouds, minimal maps, country profiles, collaboration, table workbook.

Figures (latex/figures/):
  figS1_wordcloud_keywords     author keywords of the bibliometric corpus
  figS2_wordcloud_abstracts    terms and two-word phrases in abstracts of the core set
  figS3_wordcloud_conclusions  terms in the Conclusions sections of the focused studies (from s04 output)
  figS4_map_affiliations       where the papers come from (author affiliations, documents per country)
  figS5_map_modalities         where each data modality is studied (study areas of the core set)
  figS6_map_focused            focused studies by study area, coloured by validation design
  figS7_country_profiles       what sort of studies come from each leading country (targets and methods)
  figS8_country_collaboration  international co-authorship network
  figS9_country_trends         annual output of the leading affiliation countries
Tables: outputs/review_tables.xlsx (one sheet per table), outputs/top_authors.csv
Stats : outputs/stats_extras.json
"""
import collections, itertools, re
import numpy as np, pandas as pd, networkx as nx
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from common import CNORM, norm_kw, dump, load, read_csv

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.spines.top": False, "axes.spines.right": False})
LAND, EDGE, INK = "#e9edf1", "#ffffff", "#1f3b5c"
NE_NAME = {"United States": "United States of America", "Czech Republic": "Czechia", "Serbia": "Republic of Serbia",
           "Tanzania": "United Republic of Tanzania", "Hong Kong": "China"}
# study-area gazetteer for the focused subset (lon, lat); matched against the 'area' field
PLACES = {"westminster": (-0.137, 51.497), "london": (-0.128, 51.507), "peterborough": (-0.242, 52.573), "coventry": (-1.512, 52.407),
          "oxford": (-1.258, 51.752), "cambridge": (0.122, 52.205), "newcastle": (-1.618, 54.978), "glasgow": (-4.252, 55.864),
          "edinburgh": (-3.189, 55.953), "belfast": (-5.930, 54.597), "dublin": (-6.260, 53.350), "copenhagen": (12.568, 55.676),
          "saint-etienne": (4.387, 45.439), "saint-étienne": (4.387, 45.439), "turin": (7.686, 45.070), "naples": (14.268, 40.852),
          "bologna": (11.343, 44.495), "tuzla": (29.30, 40.82), "istanbul": (28.978, 41.008), "seville": (-5.984, 37.389),
          "paris": (2.352, 48.857), "berlin": (13.405, 52.520), "sheffield": (-1.470, 53.381), "manchester": (-2.244, 53.483),
          "england": (-1.5, 52.6), "ireland": (-8.0, 53.3), "italy": (12.5, 42.8), "denmark": (9.5, 56.0), "france": (2.5, 46.6)}
STOP = set("""a an the and or of in on for to with by from as at is are was were be been this that these those it its their our we
study studies paper research results result method methods approach approaches based using use used proposed also can may
however different various new two one three analysis data model models modelling modeling framework case show shows shown
among within while which such than more most high higher low lower well significant significantly total including provide
provides provided present presents important effect effects impact impacts findings found work performance per
has have had not all but will could would should into then when how other over both each only under due across further
furthermore respectively overall obtained showed show applied current compared increase increased increasing average mean
key typical level year years time during between through considering considered given main respectively thus therefore""".split())
# words that define the search itself; excluded from abstract word clouds so that content terms are visible
SEARCH_TERMS = set("energy building buildings urban city cities".split())


def world():
    import geopandas as gpd, cartopy.io.shapereader as shpreader
    w = gpd.read_file(shpreader.natural_earth(resolution="110m", category="cultural", name="admin_0_countries"))
    w = w[w["ADMIN"] != "Antarctica"].copy()
    w["pt"] = w.representative_point()
    return w


def centroid(w, country):
    r = w[w["ADMIN"] == NE_NAME.get(country, country)]
    return (float(r["pt"].x.iloc[0]), float(r["pt"].y.iloc[0])) if len(r) else None


def base_map(ax, w, extent=None):
    w.plot(ax=ax, color=LAND, edgecolor=EDGE, linewidth=0.3)
    ax.set_axis_off()
    if extent:
        ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
    else:
        ax.set_xlim(-170, 180); ax.set_ylim(-58, 84)


def countries_of(aff):
    out = []
    for part in str(aff).split(";"):
        c = part.split(",")[-1].strip()
        c = CNORM.get(c, c)
        if c and c != "nan" and len(c) < 40:
            out.append(c)
    return out


def cloud(freqs, path, title, cmap="Blues"):
    from wordcloud import WordCloud
    if not freqs:
        return False
    wc = WordCloud(width=2000, height=1000, background_color="white", colormap=cmap, prefer_horizontal=0.95,
                   max_words=150, relative_scaling=0.5, min_font_size=8, random_state=7).generate_from_frequencies(freqs)
    fig, ax = plt.subplots(figsize=(7.2, 3.6), dpi=300)
    ax.imshow(wc, interpolation="bilinear"); ax.axis("off"); ax.set_title(title, fontsize=8, loc="left")
    fig.tight_layout(); fig.savefig(path); plt.close(fig)
    return True


def ngram_freqs(texts, n_max=160):
    from sklearn.feature_extraction.text import CountVectorizer
    texts = [re.sub(r"©.*", "", str(t)) for t in texts if isinstance(t, str) and t.strip()]
    if not texts:
        return {}
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
    cv = CountVectorizer(ngram_range=(1, 2), stop_words=sorted(ENGLISH_STOP_WORDS | STOP | SEARCH_TERMS), token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9-]{2,}\b",
                         min_df=3 if len(texts) > 30 else 1, lowercase=True)
    X = cv.fit_transform(texts)
    f = dict(zip(cv.get_feature_names_out(), np.asarray(X.sum(axis=0)).ravel()))
    # drop unigrams that are fully explained by a retained bigram
    top = dict(sorted(f.items(), key=lambda x: -x[1])[: n_max * 2])
    for bg in [k for k in top if " " in k]:
        for u in bg.split():
            if u in top and top[u] <= top[bg] * 1.2:
                top.pop(u, None)
    return dict(sorted(top.items(), key=lambda x: -x[1])[:n_max])


def run(cfg, P):
    rec = read_csv(P["out"] / "records.csv")
    dec = read_csv(P["out"] / "screening_decisions.csv")
    df = rec.merge(dec[["rid", "decision", "study_country", "modality", "target", "method"]], on="rid")
    df = df[df["decision"] != "Excluded (record type)"].copy()
    df["year"] = df["year"].astype(int)
    core = df["decision"].eq("Included (core)")
    # core-set analyses use every included study: database records and records identified via other methods
    allrec = rec
    if (P["out"] / "prior_records.csv").exists():
        allrec = pd.concat([rec, read_csv(P["out"] / "prior_records.csv")], ignore_index=True)
    CC = allrec.merge(dec[["rid", "decision", "study_country", "modality", "target", "method"]], on="rid")
    CC = CC[CC["decision"].eq("Included (core)")].copy()
    fig_, S = P["fig"], {}

    # ---------------- word clouds
    kw = collections.Counter(norm_kw(k) for s in df["author_keywords"].fillna("") for k in str(s).split(";") if k.strip())
    S["wc_keywords"] = cloud(dict(kw.most_common(150)), fig_ / "figS1_wordcloud_keywords.png", f"Author keywords, bibliometric corpus (n = {len(df):,})")
    S["wc_abstracts"] = cloud(ngram_freqs(CC["abstract"]), fig_ / "figS2_wordcloud_abstracts.png", f"Terms in abstracts, core set (n = {len(CC):,}; search terms excluded)", "Greens")
    sn = P["out"] / "fulltext_snippets.csv"
    if sn.exists():
        snips = read_csv(sn)
        F = read_csv(P["out"] / "focused_final.csv")
        conc = snips[snips["doi"].isin(F["doi"])]["conclusions"]
        S["n_conclusions"] = int(conc.fillna("").str.len().gt(200).sum())
        S["wc_conclusions"] = cloud(ngram_freqs(conc, 120), fig_ / "figS3_wordcloud_conclusions.png",
                                    f"Terms in the Conclusions of focused studies (n = {S['n_conclusions']})", "Purples")

    w = world()
    # ---------------- where the papers come from (affiliations)
    df["aff_c"] = df["affiliations"].map(countries_of)
    cnt = collections.Counter(c for l in df["aff_c"] for c in set(l))
    pts = [(c, n, centroid(w, c)) for c, n in cnt.items()]
    pts = [(c, n, xy) for c, n, xy in pts if xy]
    fig, ax = plt.subplots(figsize=(7.2, 3.4), dpi=300)
    base_map(ax, w)
    mx = max(n for _, n, _ in pts) if pts else 1
    for c, n, (x, y) in sorted(pts, key=lambda t: -t[1]):
        ax.scatter(x, y, s=8 + 520 * n / mx, color=INK, alpha=0.55, edgecolor="white", linewidth=0.4, zorder=3)
    # labels for the ten largest, placed beside the bubble with a thin leader line
    offsets = {"United Kingdom": (-22, 9), "Germany": (14, 12), "Italy": (14, -9), "Spain": (-22, -10), "France": (-24, -2),
               "Netherlands": (-18, 14), "China": (20, 10), "South Korea": (18, 8), "Japan": (18, -6), "United States": (0, -18)}
    for c, n, (x, y) in sorted(pts, key=lambda t: -t[1])[:10]:
        dx, dy = offsets.get(c, (16, 8))
        ax.annotate(f"{c} ({n})", (x, y), xytext=(x + dx, y + dy), fontsize=5, color=INK, ha="center", va="center",
                    arrowprops=dict(arrowstyle="-", lw=0.4, color="#7a8a9c"), zorder=4)
    # manual size legend (bottom left), circles drawn in data space so they do not overlap
    for i, n in enumerate([max(1, mx // 10), max(1, mx // 3), mx]):
        yy = -30 + i * 13
        ax.scatter(-155, yy, s=8 + 520 * n / mx, color=INK, alpha=0.55, edgecolor="white", linewidth=0.4)
        ax.text(-140, yy, f"{n}", fontsize=5.5, va="center")
    ax.text(-160, -14 + 3 * 13 - 13, "Documents", fontsize=6, va="bottom")
    fig.tight_layout(); fig.savefig(fig_ / "figS4_map_affiliations.png"); plt.close(fig)
    S["n_affiliation_countries"] = len(cnt)

    # ---------------- what sort of studies from where: modality small multiples (study areas)
    C = CC.fillna("")
    mods = ["GIS / cadastral", "Climate / LCZ / UHI", "Thermal / LST", "LiDAR / 3D", "Aerial / UAV", "Optical satellite", "Street-level imagery", "SAR"]
    fig, axes = plt.subplots(2, 4, figsize=(7.2, 2.9), dpi=300)
    for ax, m in zip(axes.ravel(), mods):
        base_map(ax, w, (-130, 155, -45, 72))
        sub = C[C["modality"].str.contains(m, regex=False)]["study_country"].replace("", np.nan).dropna().value_counts()
        mm = max(sub.max(), 1) if len(sub) else 1
        for c, n in sub.items():
            xy = centroid(w, c)
            if xy:
                ax.scatter(*xy, s=4 + 90 * n / mm, color="#c0504d", alpha=0.6, edgecolor="white", linewidth=0.3, zorder=3)
        ax.set_title(f"{m} (n = {int(C['modality'].str.contains(m, regex=False).sum())})", fontsize=5.8)
    fig.tight_layout(pad=0.4); fig.savefig(fig_ / "figS5_map_modalities.png"); plt.close(fig)

    # ---------------- focused studies by study area
    F = read_csv(P["out"] / "focused_final.csv")
    vcol = {"Held-out city": "#c0392b", "Held-out area": "#e67e22", "Transfer with local fine-tuning": "#8e44ad", "Random split": "#2f5d8a"}
    rows = []
    for _, r in F.iterrows():
        area = str(r.get("area", "")).lower()
        xy = next((PLACES[k] for k in PLACES if k in area), None) or centroid(w, str(r.get("country", "")))
        if xy:
            rows.append((r["study"], int(r["year"]), xy, vcol.get(r.get("validation"), "#8c8c8c")))
    fig, ax = plt.subplots(figsize=(6.2, 4.4), dpi=300)
    base_map(ax, w, (-24, 32, 36, 60))
    label = lambda s, y: f"{s.split(' et al')[0].split(' and ')[0].split(' (')[0]} {y}"
    uk = sorted([r for r in rows if r[2][0] < 2.5 and r[2][1] > 50], key=lambda r: -r[2][1])
    other = [r for r in rows if r not in uk]
    # British Isles: labels stacked in a column in the Atlantic, joined by leader lines
    seen = collections.Counter()
    for i, (s, y, (x, yy), c) in enumerate(uk):
        k = (round(x, 1), round(yy, 1)); j = seen[k]; seen[k] += 1
        x, yy = x + 0.45 * (j % 3), yy - 0.35 * (j // 3)     # fan out studies sharing a location
        ly = 59 - i * (18 / max(len(uk), 1))
        ax.plot([x, -13.2], [yy, ly], color="#9aa7b5", lw=0.35, zorder=2)
        ax.scatter(x, yy, s=26, color=c, edgecolor="white", linewidth=0.5, zorder=3)
        ax.text(-13.5, ly, label(s, y), fontsize=4.6, ha="right", va="center", color="#333")
    placed = []   # labels of neighbouring points go below the marker instead of above
    for s, y, (x, yy), c in sorted(other, key=lambda o: o[2][0]):
        ax.scatter(x, yy, s=26, color=c, edgecolor="white", linewidth=0.5, zorder=3)
        near = any(abs(x - px) < 6 and abs(yy - py) < 2 for px, py in placed)
        ax.text(x + 0.6, yy - 0.5 if near else yy + 0.4, label(s, y), fontsize=4.6, color="#333", zorder=4,
                va="top" if near else "baseline")
        placed.append((x, yy))
    for k, c in list(vcol.items()) + [("Other / not reported", "#8c8c8c")]:
        ax.scatter([], [], s=30, color=c, label=k)
    ax.legend(frameon=False, fontsize=5, loc="upper right", title="Validation design", title_fontsize=5.5)
    fig.tight_layout(); fig.savefig(fig_ / "figS6_map_focused.png"); plt.close(fig)

    # ---------------- country profiles (study area): targets and methods
    top = C["study_country"].replace("", np.nan).dropna().value_counts().head(12).index[::-1]
    tg = ["Heating / cooling demand", "Energy use intensity / benchmark", "Envelope / heat loss", "Retrofit potential", "Rating / label"]
    me = ["Physics-based simulation / UBEM", "Statistical / spatial statistics", "Machine / deep learning"]
    prof = {}
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.4), dpi=300, sharey=True)
    for ax, (col, cats, cmap) in zip(axes, [("target", tg, plt.cm.Blues), ("method", me, plt.cm.Oranges)]):
        left = np.zeros(len(top))
        for i, k in enumerate(cats):
            v = np.array([int((C["study_country"].eq(c) & C[col].str.contains(k, regex=False)).sum()) for c in top])
            ax.barh(range(len(top)), v, left=left, color=cmap(0.35 + 0.6 * i / max(len(cats) - 1, 1)), label=k, height=0.7)
            left += v
            prof[k] = dict(zip(top, v.tolist()))
        ax.set_yticks(range(len(top))); ax.set_yticklabels(top, fontsize=6); ax.set_xlabel("Studies (a study can have several codes)", fontsize=6)
        ax.legend(frameon=False, fontsize=5.2, loc="lower right"); ax.set_title("(a) Energy-efficiency targets" if col == "target" else "(b) Method families", fontsize=7, loc="left")
    fig.tight_layout(); fig.savefig(fig_ / "figS7_country_profiles.png"); plt.close(fig)
    S["country_profiles"] = prof

    # ---------------- international collaboration network
    G = nx.Graph()
    for l in df["aff_c"]:
        s = sorted(set(l))
        for c in s:
            G.add_node(c, n=G.nodes[c]["n"] + 1 if c in G else 1)
        for a, b in itertools.combinations(s, 2):
            G.add_edge(a, b, weight=G[a][b]["weight"] + 1 if G.has_edge(a, b) else 1)
    H = G.subgraph([n for n in G if G.degree(n) > 0 and G.nodes[n]["n"] >= 5]).copy()
    S["collab_edges"] = sorted(((a, b, d["weight"]) for a, b, d in G.edges(data=True)), key=lambda x: -x[2])[:15]
    if len(H):
        pos = nx.spring_layout(H, weight="weight", seed=11, k=1.2)
        fig, ax = plt.subplots(figsize=(6.2, 4.6), dpi=300); ax.axis("off")
        mw = max(d["weight"] for *_, d in H.edges(data=True))
        for a, b, d in H.edges(data=True):
            ax.plot(*zip(pos[a], pos[b]), color="#9fb1c7", lw=0.3 + 3 * d["weight"] / mw, alpha=0.6, zorder=1)
        mn = max(H.nodes[n]["n"] for n in H)
        for n in H:
            ax.scatter(*pos[n], s=15 + 600 * H.nodes[n]["n"] / mn, color=INK, alpha=0.8, edgecolor="white", lw=0.5, zorder=2)
            ax.text(pos[n][0], pos[n][1] - 0.06, n, fontsize=5, ha="center", va="top", zorder=3)
        fig.tight_layout(); fig.savefig(fig_ / "figS8_country_collaboration.png"); plt.close(fig)

    # ---------------- annual output of leading countries
    lead = [c for c, _ in cnt.most_common(6)]
    fig, ax = plt.subplots(figsize=(6.0, 2.8), dpi=300)
    yrs = range(max(2005, df["year"].min()), df["year"].max() + 1)
    for i, c in enumerate(lead):
        s = df[df["aff_c"].map(lambda l: c in l)]["year"].value_counts()
        ax.plot(list(yrs), [s.get(y, 0) for y in yrs], lw=1.2, color=plt.cm.tab10(i), label=c)
    ax.set_xlabel("Publication year"); ax.set_ylabel("Documents"); ax.legend(frameon=False, fontsize=6, ncol=2)
    fig.tight_layout(); fig.savefig(fig_ / "figS9_country_trends.png"); plt.close(fig)

    # ---------------- authors and the table workbook
    au = collections.Counter(a.strip() for s in df["authors"].fillna("") for a in re.split(r";", str(s)) if a.strip())
    pd.DataFrame(au.most_common(25), columns=["author", "documents"]).to_csv(P["out"] / "top_authors.csv", index=False, encoding="utf-8-sig")
    S["top_authors"] = au.most_common(10)
    sheets = {"screening_summary": pd.json_normalize(load(P["out"] / "stats_screening.json"), max_level=0).T.rename(columns={0: "value"}),
              "top_sources": read_csv(P["out"] / "top_sources.csv"), "affiliation_countries": read_csv(P["out"] / "countries_affiliation.csv"),
              "study_countries_core": read_csv(P["out"] / "core_study_countries.csv"), "top_authors": read_csv(P["out"] / "top_authors.csv"),
              "keywords": read_csv(P["out"] / "keyword_frequencies.csv").head(300), "thematic_map": read_csv(P["out"] / "thematic_map.csv"),
              "top_cited": read_csv(P["out"] / "top_cited.csv"), "top_cited_references": read_csv(P["out"] / "top_cited_references.csv"),
              "focused_studies": F, "country_profiles": pd.DataFrame(prof)}
    if (P["out"] / "prior_literature_status.csv").exists():   # the authors' previous literature and where each work stands
        sheets["prior_literature"] = read_csv(P["out"] / "prior_literature_status.csv")
    with pd.ExcelWriter(P["out"] / "review_tables.xlsx") as xw:
        for name, t in sheets.items():
            t.to_excel(xw, sheet_name=name[:31], index=name in ("screening_summary", "country_profiles"))
    dump(S, P["out"] / "stats_extras.json")
    return {k: v for k, v in S.items() if k.startswith(("wc_", "n_"))}
