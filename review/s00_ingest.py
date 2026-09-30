"""Stage 0 - read Scopus CSV and Web of Science exports, harmonise, de-duplicate.

Output: outputs/records.csv (one row per unique record, common schema)
        outputs/duplicates.csv, outputs/stats_ingest.json
Feeds : PRISMA identification boxes; every later stage.
"""
import glob, pathlib
import pandas as pd
from common import norm_doi, norm_title, dump

SCHEMA = ["rid", "db", "doi", "title", "abstract", "author_keywords", "index_keywords", "authors", "year",
          "source_title", "doc_type", "cited_by", "affiliations", "references", "language", "open_access"]

WOS_DT = {"Article": "Article", "Review": "Review", "Proceedings Paper": "Conference Paper",
          "Article; Proceedings Paper": "Conference Paper", "Review; Early Access": "Review", "Article; Early Access": "Article"}


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


def run(cfg, P, scopus_files=None, wos_files=None):
    scopus_files = scopus_files if scopus_files is not None else sorted(glob.glob(cfg.SEARCH["scopus_glob"]))
    wos_files = wos_files if wos_files is not None else sorted(glob.glob(cfg.SEARCH["wos_glob"]))
    if not scopus_files and not wos_files:
        raise FileNotFoundError("No database exports found. Check SEARCH['scopus_glob'] / ['wos_glob'] in config.py")
    S, W = read_scopus(scopus_files), read_wos(wos_files)
    n_scopus_raw, n_wos_raw = len(S), len(W)
    allr = pd.concat([x for x in (S, W) if len(x)], ignore_index=True)
    allr["doi_n"] = allr["doi"].map(norm_doi)
    allr["title_n"] = allr["title"].map(norm_title)
    allr["year"] = pd.to_numeric(allr["year"], errors="coerce").astype("Int64")
    allr["cited_by"] = pd.to_numeric(allr["cited_by"], errors="coerce").fillna(0)
    # priority: Scopus record kept (richer affiliation/keyword fields), then the more complete abstract
    allr["prio"] = (allr["db"] != "Scopus").astype(int)
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
    # which databases held each unique record
    dbs = allr.groupby(allr["doi_n"].where(allr["doi_n"] != "", allr["title_n"]))["db"].agg(lambda s: "; ".join(sorted(set(s))))
    rec["found_in"] = rec["doi_n"].where(rec["doi_n"] != "", rec["title_n"]).map(dbs)
    rec[SCHEMA + ["doi_n", "title_n", "found_in"]].to_csv(P["out"] / "records.csv", index=False, encoding="utf-8-sig")
    st = {"files_scopus": [pathlib.Path(f).name for f in scopus_files], "files_wos": [pathlib.Path(f).name for f in wos_files],
          "n_scopus": int(cfg.SEARCH["scopus_hits"] or n_scopus_raw), "n_wos": int(cfg.SEARCH["wos_hits"] or n_wos_raw),
          "n_scopus_export": n_scopus_raw, "n_wos_export": n_wos_raw, "n_identified": int(len(allr)),
          "n_duplicates": int(dup.sum()), "n_unique": int(len(rec)),
          "n_both_databases": int(rec["found_in"].str.contains(";").sum()),
          "search_date": cfg.SEARCH["search_date"], "field": cfg.SEARCH["field"]}
    dump(st, P["out"] / "stats_ingest.json")
    return st
