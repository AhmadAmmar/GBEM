"""Stage 6 - write LaTeX fragments that the manuscript \\input{}s.

latex/generated/numbers.tex        \\newcommand macros for every number quoted in the text
latex/generated/tab_sources.tex    Table 6 body       latex/generated/tab_modalities.tex  Table 7 body
latex/generated/tab_performance.tex Table 8 body      latex/generated/tab_validation.tex  Table 9 body
latex/generated/tab_appraisal.tex  Table D body       latex/generated/tab_studies.tex     Table E body
Also fetches BibTeX (by DOI) for focused studies that have no citation key yet and appends it to references.bib.
"""
import pathlib, re, time, unicodedata, urllib.request
import pandas as pd
from common import load, read_csv, norm_doi

VORDER = ["Random split", "Held-out city", "Held-out area", "Spatially blocked CV", "Temporal hold-out",
          "Transfer with local fine-tuning", "Internal (not specified)", "Not reported"]
VLABEL = {"Random split": "Random split or $k$-fold (single area)", "Held-out city": "Held-out city",
          "Held-out area": "Held-out area within a city", "Spatially blocked CV": "Spatially blocked cross-validation",
          "Temporal hold-out": "Temporal hold-out", "Transfer with local fine-tuning": "Transfer with local fine-tuning",
          "Internal (not specified)": "Internal (unspecified)", "Not reported": "Not reported"}


def esc(s):
    s = "" if pd.isna(s) else str(s)
    for a, b in [("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("_", r"\_"), ("#", r"\#"), ("$", r"\$")]:
        s = s.replace(a, b)
    return s.replace("A-G", "A--G").replace("A-D vs E-G", "A--D vs E--G")


def fmt(x, d=0):
    return f"{x:,.{d}f}" if isinstance(x, (int, float)) else str(x)


def macro_name(k):
    return "\\" + re.sub(r"[^A-Za-z]", "", k)


def ascii_bib(s):
    acc = {"́": "'", "̀": "`", "̂": "^", "̈": '"', "̃": "~", "̧": "c", "̌": "v"}
    sp = {"–": "--", "—": "---", "‘": "`", "’": "'", "“": "``", "”": "''", "‐": "-",
          " ": " ", "ß": r"{\ss}", "ø": r"{\o}", "ł": r"{\l}", "ı": r"{\i}"}
    out = []
    for ch in s:
        if ord(ch) < 128: out.append(ch); continue
        if ch in sp: out.append(sp[ch]); continue
        d = unicodedata.normalize("NFD", ch)
        if len(d) == 2 and d[1] in acc:
            a = acc[d[1]]; out.append("{\\%s{%s}}" % (a, d[0]) if a.isalpha() else "{\\%s%s}" % (a, d[0])); continue
        out.append("?")
    return "".join(out)


def sync_bib(cfg, P):
    """Give every focused study a citation key; fetch missing BibTeX entries by DOI."""
    sheet_path = P["inputs"] / cfg.HUMAN["focused_extraction"]
    sheet = read_csv(sheet_path)
    bibp = P["it"] / "latex" / "references.bib"
    bib = bibp.read_text(encoding="utf-8")
    keys = set(re.findall(r"@\w+\{([^,]+),", bib))
    added = []
    for i, r in sheet.iterrows():
        if str(r.get("include_focused")).upper() != "Y":
            continue
        k = r.get("key")
        if isinstance(k, str) and k in keys:
            continue
        doi = norm_doi(r.get("doi"))
        if not doi.startswith("10."):
            continue
        try:
            req = urllib.request.Request("https://doi.org/" + doi, headers={"Accept": "application/x-bibtex"})
            b = urllib.request.urlopen(req, timeout=40).read().decode("utf-8").strip()
        except Exception:
            continue
        last = re.search(r"author\s*=\s*\{([^,}]+)", b)
        base = re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", last.group(1) if last else "study").encode("ascii", "ignore").decode().lower())
        base += str(int(r["year"])) if pd.notna(r.get("year")) else ""
        k = base
        for suf in "abcdefgh":
            if k not in keys:
                break
            k = base + suf
        b = re.sub(r"^@(\w+)\{[^,]+,", lambda m: "@" + m.group(1) + "{" + k + ",", b, count=1)
        b = re.sub(r",\s*month\s*=\s*\{?[A-Za-z]+\}?", "", b)
        b = re.sub(r",\s*url\s*=\s*\{https?://(dx\.)?doi\.org/[^}]*\}", "", b)
        bib += "\n\n" + ascii_bib(b); keys.add(k); sheet.at[i, "key"] = k; added.append(k)
        time.sleep(0.3)
    if added:
        bibp.write_text(bib, encoding="utf-8"); sheet.to_csv(sheet_path, index=False, encoding="utf-8-sig")
    return added


def cite(r, keys):
    k = r.get("key")
    return f"\\citet{{{k}}}" if isinstance(k, str) and k in keys else esc(f"{r['study']} ({int(r['year'])})")


def run(cfg, P):
    added = sync_bib(cfg, P)
    I, S, B, Fs = (load(P["out"] / f) for f in ["stats_ingest.json", "stats_screening.json", "stats_biblio.json", "stats_focused.json"])
    F = read_csv(P["out"] / "focused_final.csv")
    sheet = read_csv(P["inputs"] / cfg.HUMAN["focused_extraction"])
    F = F.drop(columns=["key"]).merge(sheet[["doi", "key"]], on="doi", how="left")
    keys = set(re.findall(r"@\w+\{([^,]+),", (P["it"] / "latex" / "references.bib").read_text(encoding="utf-8")))
    G = P["tex_gen"]

    # ---------------- numbers.tex
    n = {}
    n["SearchDate"] = I["search_date"]; n["SearchField"] = I["field"]
    n["NScopus"] = fmt(I["n_scopus"]); n["NWoS"] = fmt(I["n_wos"]); n["NIdentified"] = fmt(I["n_identified"])
    n["NDuplicates"] = fmt(I["n_duplicates"]); n["NBothDatabases"] = fmt(I["n_both_databases"])
    n["NRemovedType"] = fmt(S["n_removed_record_type"]); n["NScreened"] = fmt(S["n_screened"])
    n["NReviews"] = fmt(S["n_reviews"]); n["NExcludedTA"] = fmt(S["n_excluded_ta"]); n["NCore"] = fmt(S["n_core"])
    n["NCoreConference"] = fmt(S["n_core_conference"]); n["NVerified"] = fmt(S["n_verified_by_reviewer"]); n["NRuleChanged"] = fmt(S.get("n_rule_decisions_changed", 0))
    n["KappaValue"] = fmt(S["kappa"]["kappa"], 2) if S["kappa"] else "--"
    n["NKappaSample"] = fmt(S["kappa"]["n"] if S["kappa"] else S.get("n_dual_sample", 0))
    reasons = sorted(S["excluded_reasons"].items(), key=lambda x: -x[1])
    for i in range(8):
        L = "ABCDEFGH"[i]
        n["NExclReason" + L] = fmt(reasons[i][1]) if i < len(reasons) else "0"
        n["ExclReason" + L] = (reasons[i][0][0].lower() + reasons[i][0][1:] if reasons[i][0][1:2].islower() else reasons[i][0]) if i < len(reasons) else "--"
    n["RecallRetrieved"] = str(cfg.SEARCH["recall_benchmark"]["retrieved"] or "--")
    n["RecallN"] = str(cfg.SEARCH["recall_benchmark"]["n"])
    for i in range(6):
        cl = B["network"]["clusters"][i] if i < len(B["network"]["clusters"]) else ["--"]
        n["Cluster" + "ABCDEF"[i]] = ", ".join(cl[:6])
    n["NClusterShown"] = str(min(6, len(B["network"]["clusters"])))
    items = [f"({i + 1}) " + ", ".join(cl[:6]) for i, cl in enumerate(B["network"]["clusters"][:6])]
    n["ClusterList"] = items[0] if len(items) == 1 else "; ".join(items[:-1]) + "; and " + items[-1] if items else "--"
    n["NCoreCountries"] = fmt(S["core_n_countries"]); n["NCoreCountryFromText"] = fmt(S["n_core_title_abstract_country"])
    n["NCoreNoValidation"] = fmt(S["core_no_validation_terms"])
    n["PctCoreNoValidation"] = fmt(100 * S["core_no_validation_terms"] / max(S["n_core"], 1), 1)
    for grp, pre in [("core_modality", "Mod"), ("core_target", "Tgt"), ("core_method", "Met")]:
        for k, v in S[grp].items():
            nm = pre + re.sub(r"[^A-Za-z]", "", k.title())
            n["N" + nm] = fmt(v["n"]); n["Pct" + nm] = fmt(v["pct"], 1)
    ml_recent = sum(v for k, v in S["core_ml_by_year"].items() if int(k) >= B["last_year"] - 2)
    n["NMLRecent"] = fmt(ml_recent)
    top_c = list(S["core_countries"].items())[:4]
    for i, (c, v) in enumerate(top_c):
        n["CoreCountry" + "ABCD"[i]] = c; n["NCoreCountry" + "ABCD"[i]] = fmt(v)
    n["NCorpus"] = fmt(B["n_corpus"]); n["CAGR"] = fmt(B["cagr_pct"], 1); n["CAGRStart"] = str(B["cagr_years"][0]); n["CAGREnd"] = str(B["cagr_years"][1])
    n["PctSince"] = fmt(B["share_since_2020"], 1); n["PctCoreSince"] = fmt(B["core_share_since_2020"], 1)
    n["PeakYear"] = str(B["peak_year"]); n["NPeak"] = fmt(B["peak_n"]); n["LastYear"] = str(B["last_year"])
    n["NLastYear"] = fmt(B["by_year"].get(str(B["last_year"]), B["by_year"].get(B["last_year"], 0)))
    n["NSources"] = fmt(B["n_sources"]); n["NSourcesThird"] = fmt(B["sources_for_third"])
    n["NCountriesAff"] = fmt(B["n_countries_aff"]); n["PctIntl"] = fmt(B["intl_collab_pct"], 1)
    n["MedianCites"] = fmt(B["median_citations"]); n["HIndex"] = fmt(B["h_index"])
    n["NKeywords"] = fmt(B["n_keywords_unique"]); n["NDocsKw"] = fmt(B["docs_with_kw"])
    n["NetThreshold"] = fmt(B["network"]["min_occ"]); n["NetNodes"] = fmt(B["network"]["nodes"])
    n["NetEdges"] = fmt(B["network"]["edges"]); n["NetClusters"] = fmt(B["network"]["n_clusters"])
    for i, (k, v) in enumerate(list(B["top_keywords"].items())[:5]):
        n["TopKw" + "ABCDE"[i]] = k; n["NTopKw" + "ABCDE"[i]] = fmt(v)
    n["NFocused"] = fmt(Fs["n_focused"]); n["NFocusedDB"] = fmt(Fs["n_focused_db"]); n["NFocusedOther"] = fmt(Fs["n_focused_other"])
    n["NFocusedUK"] = fmt(Fs["n_uk"]); n["NPredictive"] = fmt(Fs["n_predictive"]); n["NHeldOut"] = fmt(Fs["n_heldout"])
    n["NRandom"] = fmt(Fs["n_random"]); n["NTemporal"] = fmt(Fs["n_temporal"]); n["NMetrics"] = fmt(Fs["n_metrics"])
    n["NFullText"] = fmt(Fs["n_fulltext"]); n["NPending"] = fmt(Fs["n_pending"])
    if Fs["binary_f1_range"]:
        n["BinFOneMin"], n["BinFOneMax"] = fmt(Fs["binary_f1_range"][0], 2), fmt(Fs["binary_f1_range"][1], 2)
    n["NSupplementary"] = fmt(len(read_csv(P["inputs"] / cfg.HUMAN["supplementary_studies"])))
    # earlier searches and the authors' previous literature
    E = I.get("earlier_searches", [])
    n["NScopusEarlier"] = fmt(sum(e["n"] for e in E)); n["EarlierSearchDate"] = E[0]["date"] if E else "--"
    n["EarlierSearchField"] = E[0]["field"] if E else "--"; n["NOnlyEarlier"] = fmt(I.get("n_only_earlier", 0))
    n["NCoreDB"] = fmt(S.get("n_core_db", S["n_core"])); n["NCoreOther"] = fmt(S.get("n_core_other", 0))
    n["NOtherIdentified"] = fmt(S.get("n_other_identified", 0)); n["NOtherScreened"] = fmt(S.get("n_other_screened", 0))
    n["NPriorWorks"] = fmt(I.get("n_prior_works", 0)); n["NPriorInCurrent"] = fmt(I.get("n_prior_in_current", 0))
    n["NPriorEarlierOnly"] = fmt(I.get("n_prior_in_earlier_only", 0)); n["NPriorOther"] = fmt(I.get("n_prior_other_methods", 0))
    tp = P["out"] / "stats_triage.json"
    Tr = load(tp) if tp.exists() else {"triage": {}, "check_included": {}}
    for k in ("Likely", "Unclear", "Unlikely"):
        n["NTriage" + k] = fmt(Tr["triage"].get(k, 0)); n["NTriageCheck" + k] = fmt(Tr["check_included"].get(k, 0))
    n["NTriageFullText"] = fmt(Tr.get("n_with_fulltext", 0)); n["NTriageCheckN"] = fmt(Tr["check_included"].get("n", 0))
    n["NCoreRouteGeo"] = fmt(S.get("n_core_route_geo", 0)); n["NCoreRouteRating"] = fmt(S.get("n_core_route_rating", 0)); n["NToVerify"] = fmt(S.get("n_to_verify", 0))
    n["NScopingOther"] = fmt(S.get("n_other_scoping", 0)); n["NCoreScoping"] = fmt(S.get("n_core_other_scoping", 0))
    n["NPriorCore"] = fmt(S.get("n_prior_core", 0)); n["NTitleOnly"] = fmt(S.get("n_title_only", 0)); n["NReviewsTotal"] = fmt(S.get("n_reviews_total", S["n_reviews"]))
    lines = ["% Generated by the review pipeline (s06_tex_outputs.py). Do not edit by hand; re-run the pipeline."]
    lines += [f"\\providecommand{{{macro_name(k)}}}{{}}\\renewcommand{{{macro_name(k)}}}{{{esc(v) if not re.fullmatch(r'[0-9.,]+', str(v)) else v}}}"
              for k, v in n.items()]
    lines.append("\\providecommand{\\IfPending}[2]{}\\renewcommand{\\IfPending}[2]{" + ("#1" if Fs["n_pending"] and tp.exists() else "#2") + "}")
    lines.append("\\providecommand{\\IfDual}[2]{}\\renewcommand{\\IfDual}[2]{" + ("#1" if S.get("dual_screening", True) else "#2") + "}")
    lines.append("\\providecommand{\\IfKappa}[2]{}\\renewcommand{\\IfKappa}[2]{" + ("#1" if S["kappa"] else "#2") + "}")
    lines.append("\\providecommand{\\IfVerified}[2]{}\\renewcommand{\\IfVerified}[2]{" + ("#1" if S["n_verified_by_reviewer"] else "#2") + "}")
    lines.append("\\providecommand{\\IfRecall}[2]{}\\renewcommand{\\IfRecall}[2]{" + ("#1" if cfg.SEARCH["recall_benchmark"]["retrieved"] else "#2") + "}")
    _rb = cfg.SEARCH["recall_benchmark"]
    lines.append("\\providecommand{\\IfRecallAll}[2]{}\\renewcommand{\\IfRecallAll}[2]{" + ("#1" if _rb["retrieved"] and _rb["retrieved"] == _rb["n"] else "#2") + "}")
    lines.append("\\providecommand{\\IfPeakLast}[2]{}\\renewcommand{\\IfPeakLast}[2]{" + ("#1" if B["peak_year"] == B["last_year"] else "#2") + "}")
    lines.append("\\providecommand{\\IfScoping}[2]{}\\renewcommand{\\IfScoping}[2]{" + ("#1" if S.get("n_other_scoping", 0) else "#2") + "}")
    lines.append("\\providecommand{\\IfEarlier}[2]{}\\renewcommand{\\IfEarlier}[2]{" + ("#1" if I.get("earlier_searches") else "#2") + "}")
    lines.append("\\providecommand{\\IfWoS}[2]{}\\renewcommand{\\IfWoS}[2]{" + ("#1" if I["n_wos"] else "#2") + "}")
    (G / "numbers.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ---------------- search string (Appendix A) from the query file, STEP 1 block
    qf = cfg.SEARCH["query_file"]
    if qf.exists():
        q = qf.read_text(encoding="utf-8")
        m = re.search(r"STEP 1 .*?\n-+\n(.*?)\n-{10,}", q, re.S)
        s = re.sub(r"\s+", " ", (m.group(1) if m else q)).strip()
        (G / "search_string.tex").write_text("\\begin{flushleft}\\ttfamily\\scriptsize\n" + esc(s) + "\n\\end{flushleft}\n", encoding="utf-8")
    # earlier documented searches (their strings start with the field code, e.g. TITLE(( ... )
    earlier = []
    for e in getattr(cfg, "EARLIER_SEARCHES", []):
        if pathlib.Path(e["query_file"]).exists():
            q = pathlib.Path(e["query_file"]).read_text(encoding="utf-8")
            m = re.search(r"^(TITLE[-A-Z]*\s*\(.*?)$", q, re.M | re.S)
            if m:
                earlier.append(f"\\textit{{Search of {e['date']} ({e['field']}):}}\\\\\n" + esc(re.sub(r"\s+", " ", m.group(1)).strip()))
    (G / "search_string_earlier.tex").write_text(("\\begin{flushleft}\\ttfamily\\scriptsize\n" + "\n\n".join(earlier) + "\n\\end{flushleft}\n")
                                                  if earlier else "\n", encoding="utf-8")

    # ---------------- Table 6 sources + countries
    src = B["top_sources"]; cty = list(B["countries_top"].items())
    rows = []
    for i in range(10):
        a = src[i] if i < len(src) else None; c = cty[i] if i < len(cty) else None
        left = f"{esc(a['source_title'])} & {a['docs']:,} & {int(a['cites']):,} & {a['core']:,}" if a else "& & &"
        right = f"{esc(c[0])} & {c[1]['n']:,} & {c[1]['pct']:.1f}" if c else "& &"
        rows.append(f"{left} & {right} \\\\")
    (G / "tab_sources.tex").write_text("\n".join(rows) + "\n", encoding="utf-8")

    # ---------------- Table 7 modalities
    role = {"Climate / LCZ / UHI": ("Urban heat island intensity, LCZ class, microclimate; context for demand", "100\\,m--km"),
            "GIS / cadastral": ("Footprints, age, use, height; certificate mapping; archetypes", "Vector"),
            "Thermal / LST": ("Roof and facade temperature, heat-loss anomalies, surface UHI", "0.1--100\\,m"),
            "LiDAR / 3D": ("Height, volume, roof shape, compactness, shared walls, age", "0.25--2\\,m"),
            "Aerial / UAV": ("Roof material and condition, geometry; thermal flights", "0.05--0.5\\,m"),
            "Optical satellite": ("Built-up and vegetation indices, land cover, roof reflectance", "0.3--30\\,m"),
            "Street-level imagery": ("Facade materials, windows, condition, style", "Image"),
            "SAR": ("Height and density", "5--20\\,m")}
    mod = sorted(S["core_modality"].items(), key=lambda x: -x[1]["n"])
    (G / "tab_modalities.tex").write_text("\n".join(f"{esc(k)} & {role[k][0]} & {role[k][1]} & {v['n']:,} & {v['pct']:.1f} \\\\" for k, v in mod) + "\n", encoding="utf-8")

    # ---------------- Table 8 performance
    Pp = F[~F["validation"].fillna("").isin(["Not applicable", "Not applicable (zero-shot)", ""])].copy()
    order = {"Binary": 0, "Multi-class": 1, "Ordinal (A-G)": 1, "Continuous": 2}
    Pp["o"] = Pp["target_type"].map(order).fillna(3); Pp = Pp.sort_values(["o", "year"])
    heads = {0: "Binary", 1: "Multi-class and ordinal", 2: "Continuous", 3: "Other"}
    rows, cur = [], None
    for _, r in Pp.iterrows():
        if r["o"] != cur:
            cur = r["o"]; rows.append(f"\\multicolumn{{6}}{{@{{}}l}}{{\\textit{{{heads[cur]}}}}} \\\\")
        val = "Not reported" if pd.isna(r["value"]) else f"{esc(r['metric'])} {float(r['value']):.3g}"
        rows.append(f"{cite(r, keys)} & {esc(r['area'])} & {esc(r['data'])} & {esc(r['target'])} & {esc(r['validation'])} & {val} \\\\")
    (G / "tab_performance.tex").write_text("\n".join(rows) + "\n", encoding="utf-8")

    # ---------------- Table 9 validation
    rows = []
    for v in VORDER:
        sub = Pp[Pp["validation"] == v]
        cites = "; ".join(cite(r, keys) for _, r in sub.iterrows()) or "--"
        rows.append(f"{VLABEL[v]} & {len(sub)} & {100 * len(sub) / max(len(Pp), 1):.1f} & {cites} \\\\")
    (G / "tab_validation.tex").write_text("\n".join(rows) + "\n", encoding="utf-8")

    # ---------------- Appendix D appraisal and E studies
    q = ["q2_timegap", "q3_spatial", "q4_unseen", "q5_classwise", "q7_uncertainty", "q8_open"]
    rows = [f"{cite(r, keys)} & " + " & ".join(esc(r.get(c, "-")) if pd.notna(r.get(c)) else "--" for c in q) + " \\\\" for _, r in Pp.iterrows()]
    (G / "tab_appraisal.tex").write_text("\n".join(rows) + "\n", encoding="utf-8")
    arm = lambda a: "D" if a == "Database" else "O"
    rows = [f"{cite(r, keys)} ({arm(r['arm_now'])}) & {esc(r['area'])} & {esc(r['data'])} & {esc(r['target'])} & {esc(r['model_family'])}; {esc(r['validation']).lower() if pd.notna(r['validation']) else '--'} \\\\"
            for _, r in F.sort_values("year").iterrows()]
    (G / "tab_studies.tex").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return {"macros": len(n), "bib_added": added}
