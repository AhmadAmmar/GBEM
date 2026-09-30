"""Stage 0 - read Scopus CSV and Web of Science exports, harmonise, de-duplicate.

Output: outputs/records.csv (one row per unique record, common schema)
        outputs/duplicates.csv, outputs/stats_ingest.json
Feeds : PRISMA identification boxes; every later stage.
"""
import glob, pathlib, re
import pandas as pd
from common import norm_doi, norm_title, dump, read_csv

SCHEMA = ["rid", "db", "doi", "title", "abstract", "author_keywords", "index_keywords", "authors", "year",
          "source_title", "doc_type", "cited_by", "affiliations", "references", "language", "open_access"]

WOS_DT = {"Article": "Article", "Review": "Review", "Proceedings Paper": "Conference Paper",
          "Article; Proceedings Paper": "Conference Paper", "Review; Early Access": "Review", "Article; Early Access": "Article"}
# Scopus spells the type "Conference paper" in current exports and "Conference Paper" in older ones
DT_CANON = {"article": "Article", "review": "Review", "conference paper": "Conference Paper"}


def read_scopus(files):
    frames = []
    for f in files:
        d = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
        frames.append(pd.DataFrame({
            "rid": d.get("EID"), "db": "Scopus", "doi": d.get("DOI"), "title": d.get("Title"),
            "abstract": d.get("Abstract"), "author_keywords": d.get("Author Keywords"),
            "index_keywords": d.get("Index Keywords"), "authors": d.get("Authors"), "year": d.get("Year"),
            "source_title": d.get("Source title"), "doc_type": d.get("Document Type"), "cited_by": d.get("Cited by"),
            "affiliations": d.get("Affiliations"), "references": d.get("References"),
            "language": d.get("Language of Original Document"), "open_access": d.get("Open Access")}))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=SCHEMA)


def read_wos(files):
    frames = []
    for f in files:
        d = pd.read_csv(f, sep="\t", quoting=3, dtype=str, encoding="utf-8-sig", index_col=False)
        g = lambda c: d[c] if c in d else None
        aff = g("C1")
        if aff is not None:   # "[Authors] Institution, City, Country; [..] .." -> "Institution, City, Country; .."
            aff = aff.fillna("").str.replace(r"\[[^\]]*\]\s*", "", regex=True)
        frames.append(pd.DataFrame({
            "rid": g("UT"), "db": "WoS", "doi": g("DI"), "title": g("TI"), "abstract": g("AB"),
            "author_keywords": g("DE"), "index_keywords": g("ID"), "authors": g("AU"), "year": pd.to_numeric(g("PY"), errors="coerce"),
            "source_title": g("SO"), "doc_type": g("DT").map(lambda x: WOS_DT.get(x, x)) if g("DT") is not None else None,
            "cited_by": pd.to_numeric(g("TC"), errors="coerce"), "affiliations": aff, "references": g("CR"),
            "language": g("LA"), "open_access": g("OA")}))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=SCHEMA)


def query_blocks(query_file):
    """Concept blocks of a Scopus TITLE-ABS-KEY query as regular expressions (truncation * -> word characters)."""
    t = pathlib.Path(query_file).read_text(encoding="utf-8")
    step1 = t.split("STEP 1b")[0]
    blocks = []
    for b in re.findall(r"TITLE-ABS-KEY\s*\((.*?)\)\s*(?:AND|\n\s*AND|$)", step1, flags=re.S):
        terms = [x.strip() for x in re.findall(r'"([^"]+)"|(\S+)', b) for x in x if x.strip() and x.strip().upper() not in ("OR", "AND")]
        rx = []
        for term in terms:
            words = [re.escape(w).replace(r"\*", r"\w*") for w in re.split(r"[\s\-]+", term.strip("()")) if w]
            if words:
                rx.append(r"\b" + r"[\s\-]+".join(words) + (r"(?:s|es)?\b" if not words[-1].endswith(r"\w*") else ""))
        blocks.append(re.compile("|".join(rx), re.I))
    return blocks


def diagnose(r, blocks, years, doc_types):
    """Why the current search strategy does not retrieve a record (checked against title, abstract and keywords)."""
    text = " ".join(str(r.get(c, "") or "") for c in ("title", "abstract", "author_keywords", "index_keywords"))
    if not text.strip() or not str(r.get("abstract", "") or "").strip():
        why = ["no abstract available to check"]
    else:
        why = [f"no term of concept block {'ABC'[i]}" for i, b in enumerate(blocks) if not b.search(text)]
    y = pd.to_numeric(r.get("year"), errors="coerce")
    if pd.notna(y) and not (years[0] <= int(y) <= years[1]):
        why.append("outside publication years")
    dt = DT_CANON.get(str(r.get("doc_type", "")).strip().lower(), r.get("doc_type"))
    if dt and str(dt) != "nan" and dt not in doc_types:
        why.append(f"document type {dt}")
    return "; ".join(why) if why else "all concept blocks matched (indexing or export difference)"


def run(cfg, P, scopus_files=None, wos_files=None):
    scopus_files = scopus_files if scopus_files is not None else sorted(glob.glob(cfg.SEARCH["scopus_glob"]))
    wos_files = wos_files if wos_files is not None else sorted(glob.glob(cfg.SEARCH["wos_glob"]))
    if not scopus_files and not wos_files:
        raise FileNotFoundError("No database exports found. Check SEARCH['scopus_glob'] / ['wos_glob'] in config.py")
    current = f"Scopus {cfg.SEARCH['search_date']}"
    S, W = read_scopus(scopus_files).assign(search=current), read_wos(wos_files).assign(search=f"WoS {cfg.SEARCH['search_date']}")
    n_scopus_raw, n_wos_raw = len(S), len(W)
    # earlier documented searches (combined with the current one; each record keeps the searches that found it)
    E, earlier = [], []
    for s in getattr(cfg, "EARLIER_SEARCHES", []):
        files = sorted(glob.glob(s["glob"]))
        if files:
            e = read_scopus(files).assign(search=f"Scopus {s['date']}")
            E.append(e)
            earlier.append({"label": s["label"], "date": s["date"], "field": s["field"], "n": int(len(e)),
                            "files": [pathlib.Path(f).name for f in files], "query_file": pathlib.Path(s["query_file"]).name})
    allr = pd.concat([x for x in [S, *E, W] if len(x)], ignore_index=True)
    allr["doi_n"] = allr["doi"].map(norm_doi)
    allr["title_n"] = allr["title"].map(norm_title)
    allr["year"] = pd.to_numeric(allr["year"], errors="coerce").astype("Int64")
    allr["cited_by"] = pd.to_numeric(allr["cited_by"], errors="coerce").fillna(0)
    allr["doc_type"] = allr["doc_type"].map(lambda x: DT_CANON.get(str(x).strip().lower(), x))
    # priority: current Scopus record, then earlier Scopus records (richer fields than WoS), then the more complete abstract
    allr["prio"] = (allr["search"] != current).astype(int) + (allr["db"] != "Scopus").astype(int)
    allr["abs_len"] = allr["abstract"].fillna("").str.len()
    allr = allr.sort_values(["prio", "abs_len"], ascending=[True, False]).reset_index(drop=True)
    within = allr.duplicated(subset=["rid"]) & allr["rid"].notna()
    by_doi = allr["doi_n"].ne("") & allr.duplicated(subset=["doi_n"])
    by_title = allr["title_n"].ne("") & allr.duplicated(subset=["title_n", "year"])
    dup = within | by_doi | by_title
    allr.loc[dup, ["rid", "db", "doi", "title", "year"]].assign(
        reason=["same record id" if a else "same DOI" if b else "same title and year" for a, b in zip(within[dup], by_doi[dup])]
    ).to_csv(P["out"] / "duplicates.csv", index=False, encoding="utf-8-sig")
    rec = allr[~dup].copy()
    # which databases and which searches held each unique record (matched by record id, DOI, or title and year)
    key = lambda d: d["doi_n"].where(d["doi_n"] != "", d["title_n"] + "|" + d["year"].astype(str))
    allr["k"], rec["k"] = key(allr), key(rec)
    rid2k = dict(zip(allr["rid"], allr["k"]))
    allr["k"] = allr["rid"].map(lambda r: rid2k.get(r)).fillna(allr["k"])
    rec["found_in"] = rec["k"].map(allr.groupby("k")["db"].agg(lambda s: "; ".join(sorted(set(s)))))
    rec["searches"] = rec["k"].map(allr.groupby("k")["search"].agg(lambda s: "; ".join(sorted(set(s), reverse=True))))
    rec["arm"] = "database"
    # records found only by an earlier search: why the current strategy does not retrieve them
    blocks = query_blocks(cfg.SEARCH["query_file"]) if pathlib.Path(cfg.SEARCH["query_file"]).exists() else []
    only_earlier = ~rec["searches"].str.contains(current, regex=False)
    rec["not_in_current_search_because"] = ""
    rec.loc[only_earlier, "not_in_current_search_because"] = rec[only_earlier].apply(
        lambda r: diagnose(r, blocks, cfg.SEARCH["years"], ("Article", "Review", "Conference Paper")), axis=1)
    rec, prior_status = prior_records(cfg, P, rec, blocks)
    cols = SCHEMA + ["doi_n", "title_n", "found_in", "searches", "arm", "prior_sources", "not_in_current_search_because"]
    rec[rec["arm"] == "database"][cols].to_csv(P["out"] / "records.csv", index=False, encoding="utf-8-sig")
    rec[rec["arm"] == "other methods"][cols].to_csv(P["out"] / "prior_records.csv", index=False, encoding="utf-8-sig")
    db = rec[rec["arm"] == "database"]
    st = {"files_scopus": [pathlib.Path(f).name for f in scopus_files], "files_wos": [pathlib.Path(f).name for f in wos_files],
          "n_scopus": int(cfg.SEARCH["scopus_hits"] or n_scopus_raw), "n_wos": int(cfg.SEARCH["wos_hits"] or n_wos_raw),
          "n_scopus_export": n_scopus_raw, "n_wos_export": n_wos_raw, "n_identified": int(len(allr)),
          "n_duplicates": int(dup.sum()), "n_unique": int(len(db)),
          "n_both_databases": int(db["found_in"].str.contains(";").sum()),
          "earlier_searches": earlier, "n_only_earlier": int((db["searches"].str.contains(current, regex=False) == False).sum()),
          "only_earlier_reasons": db.loc[only_earlier.reindex(db.index, fill_value=False), "not_in_current_search_because"]
                                  .str.split("; ").explode().value_counts().to_dict(),
          "search_date": cfg.SEARCH["search_date"], "field": cfg.SEARCH["field"], "current_search": current}
    st.update(prior_status)
    dump(st, P["out"] / "stats_ingest.json")
    return st


CROSSREF_DT = {"journal-article": "Article", "proceedings-article": "Conference Paper", "posted-content": "Preprint",
               "book-chapter": "Book chapter", "book": "Book", "report": "Report", "dataset": "Dataset",
               "dissertation": "Thesis", "monograph": "Book", "reference-entry": "Book chapter", "standard": "Standard"}


def prior_records(cfg, P, rec, blocks):
    """Link the authors' previous literature (reports, presentations, reference library, PDF library) to the records.

    Works found by a database search are tagged (prior_sources). Works not found by any search become
    'other methods' records (PRISMA), with metadata from any earlier Scopus export, else from Crossref and the PDF,
    and are screened with the same rules. Writes outputs/prior_literature_status.csv (one row per prior work).
    """
    rec["prior_sources"] = ""
    pdir = pathlib.Path(cfg.PRIOR["out_dir"]) if hasattr(cfg, "PRIOR") else None
    files = sorted(pdir.glob("*_prior_literature_*.csv")) if pdir and pdir.exists() else []
    supp_path = P["inputs"] / cfg.HUMAN["supplementary_studies"]
    if not files and not supp_path.exists():
        return rec, {"n_prior_works": 0}
    pl = read_csv(files[-1]) if files else pd.DataFrame(columns=["doi", "title", "year", "sources", "source_types", "status"])
    # citations that could not be resolved to a DOI (grey literature, slides, incomplete citations) cannot be screened
    # on a verified identity: they are listed as not assessed
    unres = pl[pl["doi"].fillna("") == ""].copy()
    pl = pl[pl["doi"].fillna("") != ""].copy()
    if supp_path.exists():   # citation searching / expert suggestion
        s = read_csv(supp_path)
        s = s.rename(columns={"study": "first_author"}).assign(title=s.get("title", ""), sources="citation searching / expert suggestion",
                                                               source_types="citation searching / expert suggestion", status="supplementary list")
        pl = pd.concat([pl, s[[c for c in ["doi", "title", "year", "first_author", "sources", "source_types", "status"] if c in s]]],
                       ignore_index=True)
    pl["doi_n"] = pl["doi"].map(norm_doi); pl["title_n"] = pl["title"].map(norm_title)
    pl = pl.groupby(pl["doi_n"].where(pl["doi_n"] != "", "t:" + pl["title_n"]), as_index=False).agg(
        lambda s: "; ".join(sorted(set(str(x) for x in s if str(x) not in ("", "nan")))) if s.name in ("sources", "source_types", "status")
        else next((x for x in s if str(x) not in ("", "nan")), ""))
    # metadata from all Scopus exports on disk (including exploratory ones not used as searches)
    meta = read_scopus(sorted(glob.glob(str(cfg.LIT / "Scopus" / "*scopus*.csv"))))
    meta["doi_n"], meta["title_n"] = meta["doi"].map(norm_doi), meta["title"].map(norm_title)
    meta["doc_type"] = meta["doc_type"].map(lambda x: DT_CANON.get(str(x).strip().lower(), x))
    meta_doi = meta[meta["doi_n"] != ""].drop_duplicates("doi_n").set_index("doi_n")
    meta_t = meta.drop_duplicates("title_n").set_index("title_n")
    by_doi = {d: i for i, d in rec["doi_n"].items() if d}
    by_t = {t: i for i, t in rec["title_n"].items() if t}
    new, status = [], []
    for _, w in pl.iterrows():
        i = by_doi.get(w["doi_n"]) if w["doi_n"] else None
        i = i if i is not None else by_t.get(w["title_n"])
        row = {"doi": w["doi"], "title": w["title"], "year": w["year"], "sources": w["sources"], "source_types": w["source_types"],
               "citation_check": w["status"]}
        if i is not None:
            rec.at[i, "prior_sources"] = w["source_types"]
            row.update(rid=rec.at[i, "rid"], arm="database", searches=rec.at[i, "searches"],
                       not_in_current_search_because=rec.at[i, "not_in_current_search_because"])
        else:
            m = meta_doi.loc[w["doi_n"]] if w["doi_n"] in meta_doi.index else meta_t.loc[w["title_n"]] if w["title_n"] in meta_t.index else None
            if m is not None:
                r = {c: m[c] for c in SCHEMA if c in m.index}
                r["db"] = "Scopus (earlier export)"
            else:
                typ = CROSSREF_DT.get(str(w.get("type", "")), str(w.get("type", "")) or "Unknown")
                if typ == "Article" and re.search(r"\breview\b|\bsurvey\b|state[- ]of[- ]the[- ]art", str(w["title"]), re.I):
                    typ = "Review"
                r = {"title": w["title"], "abstract": w.get("abstract", ""), "year": w["year"], "doi": w["doi"],
                     "source_title": w.get("container", ""), "doc_type": typ, "authors": w.get("first_author", ""),
                     "db": "Crossref / PDF", "cited_by": 0}
            r["rid"] = "prior:" + (w["doi_n"] or w["title_n"][:80])
            r.update(doi_n=w["doi_n"], title_n=w["title_n"], found_in=r["db"], searches="", arm="other methods",
                     prior_sources=w["source_types"])
            r["not_in_current_search_because"] = ("not indexed in the exports of any search" if m is None else "") or ""
            if m is not None:
                r["not_in_current_search_because"] = diagnose(r, blocks, cfg.SEARCH["years"], ("Article", "Review", "Conference Paper"))
            new.append(r)
            row.update(rid=r["rid"], arm="other methods", searches="", not_in_current_search_because=r["not_in_current_search_because"])
        status.append(row)
    for _, w in unres.iterrows():
        status.append({"doi": "", "title": w.get("title") or w.get("example_citation", ""), "year": w.get("year", ""),
                       "sources": w["sources"], "source_types": w["source_types"], "citation_check": w["status"], "rid": "",
                       "arm": "not assessed (not resolvable to a DOI)", "searches": "",
                       "not_in_current_search_because": "grey literature or incomplete citation; no verified identity"})
    if new:
        rec = pd.concat([rec, pd.DataFrame(new)], ignore_index=True)
    pd.DataFrame(status).to_csv(P["out"] / "prior_literature_status.csv", index=False, encoding="utf-8-sig")
    S = pd.DataFrame(status)
    return rec, {"prior_file": files[-1].name if files else "", "n_prior_works": int(len(S)),
                 "n_prior_in_current": int(S["searches"].fillna("").str.contains(f"Scopus {cfg.SEARCH['search_date']}", regex=False).sum()),
                 "n_prior_in_earlier_only": int(((S["arm"] == "database") & ~S["searches"].fillna("").str.contains(
                     f"Scopus {cfg.SEARCH['search_date']}", regex=False)).sum()),
                 "n_prior_other_methods": int((S["arm"] == "other methods").sum()),
                 "n_prior_unresolved": int(S["arm"].str.startswith("not assessed").sum()),
                 "n_prior_verified": int((S["arm"] != "").sum() - S["arm"].str.startswith("not assessed").sum())}
