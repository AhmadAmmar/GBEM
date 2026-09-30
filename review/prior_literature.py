"""Harvest and verify the literature used in the authors' previous work.

    python prior_literature.py --version v1 [--offline]

Sources (config.PRIOR):
  - reference lists and DOIs in assessment reports and other documents (.docx) and presentations (.pptx);
  - the reference library (BibTeX export);
  - the PDF library (DOI from the PDF metadata or first page).
Every citation is resolved to a DOI and checked against Crossref: a DOI given in a citation must belong to
the cited title; citations without a DOI are matched by bibliographic search and accepted only when the
Crossref title is contained in the citation text. Unresolved and mismatched citations are listed, not guessed.

Outputs (config.PRIOR["out_dir"], dated and versioned; earlier versions are never overwritten):
  <date>_prior_literature_<version>.csv   one row per unique work (DOI or normalised title)
  <date>_prior_citations_<version>.csv    one row per citation occurrence, with the check result
  crossref_cache.json                     cached Crossref responses (re-runs are reproducible offline)
"""
import argparse, datetime, json, pathlib, re, subprocess, sys, time, urllib.parse, urllib.request, zipfile
import pandas as pd
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config as cfg
from common import norm_doi, norm_title

UA = "GBEM-review-pipeline (https://github.com/AhmadAmmar/GBEM)"
DOI_RX = re.compile(r"10\.\d{4,9}/[^\s\"<>{}|\\^`\[\]]+", re.I)
REF_HEAD = re.compile(r"^\s*(\d+(\.\d+)*\.?\s*)?(references?|reference list|bibliography|works cited|literature cited)\b.{0,30}$", re.I)
STOP_HEAD = re.compile(r"^\s*(appendix|appendices|annex)\b", re.I)
YEAR_RX = re.compile(r"\b(19[5-9]\d|20[0-3]\d)[a-z]?\b")
JUNK_TITLE = re.compile(r"^(microsoft (word|powerpoint)|powerpoint presentation|slide \d|untitled|title of|world bank document|proceedings of)|\.(docx?|dvi|pptx?)$|^\d+$|^\(?title", re.I)
ARXIV_RX = re.compile(r"(?:arxiv[:/ ]\s*|^)(\d{4}\.\d{4,5})(?:v\d+)?", re.I)


# ----------------------------------------------------------------------------- Crossref
class Crossref:
    def __init__(self, cache_file, offline=False):
        self.f, self.offline = cache_file, offline
        self.c = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}

    def _get(self, url):
        if url in self.c:
            return self.c[url]
        if self.offline:
            return None
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.loads(r.read().decode("utf-8"))["message"]
                break
            except urllib.error.HTTPError as e:
                data = None if e.code == 404 else "retry"
                if data is None:
                    break
            except Exception:
                data = "retry"
            time.sleep(2 * (attempt + 1))
        data = None if data == "retry" else data
        self.c[url] = data
        time.sleep(0.05)
        return data

    def work(self, doi):
        m = self._get("https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="/:;()"))
        return slim(m) if m else None

    def search(self, text):
        q = urllib.parse.quote(text[:400])
        m = self._get(f"https://api.crossref.org/works?query.bibliographic={q}&rows=3&select=DOI,title,issued,container-title,type,author,abstract,subject")
        return [slim(i) for i in (m or {}).get("items", [])]

    def arxiv(self, aid):
        url = f"https://export.arxiv.org/api/query?id_list={aid}"
        if url not in self.c and not self.offline:
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
                    x = r.read().decode("utf-8", "ignore")
                e = x.split("<entry>", 1)[1] if "<entry>" in x else ""
                g = lambda tag: re.sub(r"\s+", " ", (re.search(f"<{tag}[^>]*>(.*?)</{tag}>", e, re.S) or [None, ""])[1]).strip()
                self.c[url] = {"doi": "arxiv:" + aid, "title": g("title"), "year": int(g("published")[:4]) if g("published") else None,
                               "container": "arXiv", "type": "posted-content", "first_author": g("name").split(" ")[-1],
                               "n_authors": e.count("<author>"), "abstract": g("summary"), "subject": ""} if e else None
            except Exception:
                return None
            time.sleep(1)
        return self.c.get(url)

    def save(self):
        self.f.write_text(json.dumps(self.c), encoding="utf-8")


def slim(m):
    au = m.get("author") or []
    first = (au[0].get("family") or au[0].get("name") or "") if au else ""
    yr = ((m.get("issued") or {}).get("date-parts") or [[None]])[0][0]
    return {"doi": norm_doi(m.get("DOI", "")), "title": " ".join(m.get("title") or [""]).strip(), "year": yr,
            "container": " ".join(m.get("container-title") or [""]).strip(), "type": m.get("type", ""),
            "first_author": first, "n_authors": len(au),
            "abstract": re.sub(r"<[^>]+>", " ", m.get("abstract") or "").strip(), "subject": "; ".join(m.get("subject") or [])}


def contains_title(cited, title, need=0.85):
    """Share of the Crossref title's words (4+ letters) found in the cited text."""
    tw = [w for w in norm_title(title).split() if len(w) > 3]
    if not tw:
        return 0.0
    cw = set(norm_title(cited).split())
    return sum(w in cw for w in tw) / len(tw)


# ----------------------------------------------------------------------------- readers
def docx_paragraphs(p):
    x = zipfile.ZipFile(p).read("word/document.xml").decode("utf-8", "ignore")
    out = []
    for para in re.findall(r"<w:p[ >].*?</w:p>", x, flags=re.S):
        t = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", para))
        t = re.sub(r"\s+", " ", t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")).strip()
        if t:
            out.append(t)
    return out


def pptx_slides(p):
    z = zipfile.ZipFile(p)
    names = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)), key=lambda n: int(re.findall(r"\d+", n)[0]))
    slides = []
    for n in names:
        x = z.read(n).decode("utf-8", "ignore")
        paras = [re.sub(r"\s+", " ", "".join(re.findall(r"<a:t>([^<]*)</a:t>", a)).replace("&amp;", "&")).strip()
                 for a in re.findall(r"<a:p>.*?</a:p>", x, flags=re.S)]
        slides.append([q for q in paras if q])
    return slides


def looks_like_reference(t):
    return (len(t) > 40 and YEAR_RX.search(t) and (re.search(r"[A-Z][a-z'\-]+,? (?:[A-Z]\.|et al)", t) or DOI_RX.search(t))) or bool(DOI_RX.search(t))


def citations_from_document(p):
    """(cited text, where) pairs from a report or presentation."""
    out = []
    if p.suffix == ".docx":
        P = docx_paragraphs(p)
        heads = [i for i, t in enumerate(P) if REF_HEAD.match(t)]
        body_end = len(P)
        if heads:
            start = heads[-1] + 1
            for i in range(start, len(P)):
                if STOP_HEAD.match(P[i]):
                    body_end = i; break
            out += [(t, "reference list") for t in P[start:body_end] if looks_like_reference(t)]
            body = P[:heads[-1]]
        else:
            body = P
        out += [(t, "text (DOI)") for t in body if DOI_RX.search(t)]
    else:
        for k, s in enumerate(pptx_slides(p), 1):
            is_ref = any(REF_HEAD.match(t) for t in s)
            out += [(t, f"slide {k}") for t in s if (is_ref and looks_like_reference(t)) or DOI_RX.search(t)]
    return out


def bib_entries(p):
    t = p.read_text(encoding="utf-8", errors="ignore")
    out = []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\n]*),(.*?)\n\}", t, flags=re.S):
        body = m.group(3) + "\n"
        f = lambda k: (re.search(r"(?<![A-Za-z])" + k + r"\s*=\s*[{\"](.*?)[}\"]\s*,?\s*\n", body, flags=re.S | re.I) or [None, ""])[1]
        title = re.sub(r"[{}]", "", f("title")); doi = norm_doi(f("doi"))
        out.append({"key": m.group(2).strip(), "type": m.group(1).lower(), "title": re.sub(r"\s+", " ", title).strip(),
                    "year": f("year")[:4], "doi": doi, "author": re.sub(r"[{}]", "", f("author"))[:80]})
    return out


def pdf_info(p):
    meta = subprocess.run(["pdfinfo", str(p)], capture_output=True, text=True, errors="ignore").stdout
    first = subprocess.run(["pdftotext", "-l", "2", str(p), "-"], capture_output=True, text=True, errors="ignore").stdout
    title = (re.search(r"^Title:[ \t]*(\S.*)$", meta, flags=re.M) or [None, ""])[1].strip()
    if JUNK_TITLE.search(title) or len(title) < 12:
        title = ""
    cands = [norm_doi(d.rstrip(".,;)")) for d in DOI_RX.findall(meta + "\n" + first[:6000])]
    return title, list(dict.fromkeys(cands)), first[:6000]


# ----------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1"); ap.add_argument("--offline", action="store_true")
    a = ap.parse_args(argv)
    P = cfg.PRIOR; out = pathlib.Path(P["out_dir"]); out.mkdir(parents=True, exist_ok=True)
    cr = Crossref(out / "crossref_cache.json", a.offline)
    rows = []   # citation occurrences

    # 1. reports and presentations
    docs = [f for d in P["documents"] for f in sorted(pathlib.Path(d).glob("*")) if f.suffix in (".docx", ".pptx")
            and not f.name.startswith("~$") and not any(x in f.name for x in P["exclude"])]
    for f in docs:
        try:
            cits = citations_from_document(f)
        except Exception as e:
            print("  could not read", f.name, e); continue
        for text, where in cits:
            rows.append({"source_type": "presentation" if f.suffix == ".pptx" else "report/document", "source": f.name,
                         "where": where, "cited_text": text[:600]})
        print(f"  {len(cits):4d} citations  {f.name}")

    # 2. reference library
    for e in bib_entries(pathlib.Path(P["bib"])):
        rows.append({"source_type": "reference library", "source": pathlib.Path(P["bib"]).name, "where": e["key"],
                     "cited_text": f"{e['author']} ({e['year']}) {e['title']}" + (f" doi:{e['doi']}" if e["doi"] else ""),
                     "bib_title": e["title"], "bib_doi": e["doi"]})

    # 3. PDF library
    pdfs = [p for d in P["pdf_dirs"] for p in sorted(pathlib.Path(d).rglob("*.pdf"))]
    for p in pdfs:
        title, cands, first = pdf_info(p)
        rows.append({"source_type": "PDF library", "source": str(p.relative_to(cfg.LIT)), "where": "first pages",
                     "cited_text": title or first[:300].replace("\n", " "), "pdf_title": title,
                     "pdf_dois": ";".join(cands[:5]), "pdf_first": first})
    print(f"  {len(pdfs)} PDFs; {sum(r['source_type'] == 'reference library' for r in rows)} library entries")

    # resolve every occurrence
    for i, r in enumerate(rows):
        r.update(resolve(r, cr))
        if i % 50 == 0:
            cr.save(); print(f"  resolved {i}/{len(rows)}")
    cr.save()
    C = pd.DataFrame(rows).drop(columns=["pdf_first"], errors="ignore")

    # unique works
    C["work_key"] = C["doi"].where(C["doi"].fillna("") != "", "title:" + C["title"].fillna(C["cited_text"]).map(norm_title))
    for c in ("abstract", "abstract_source"):
        if c not in C:
            C[c] = ""
    longest = lambda s: max(s.fillna("").astype(str), key=len)
    agg = C[C["status"] != "not scholarly"].groupby("work_key").agg(
        doi=("doi", "first"), title=("title", "first"), year=("year", "first"), container=("container", "first"),
        type=("type", "first"), first_author=("first_author", "first"), abstract=("abstract", longest),
        abstract_source=("abstract_source", lambda s: "; ".join(sorted(set(x for x in s.fillna("") if x)))), subject=("subject", "first"),
        n_occurrences=("source", "size"), sources=("source", lambda s: "; ".join(sorted(set(s)))),
        source_types=("source_type", lambda s: "; ".join(sorted(set(s)))),
        status=("status", lambda s: "; ".join(sorted(set(s)))), example_citation=("cited_text", "first")).reset_index()
    stamp = datetime.date.today().isoformat()
    C.to_csv(out / f"{stamp}_prior_citations_{a.version}.csv", index=False, encoding="utf-8-sig")
    agg.to_csv(out / f"{stamp}_prior_literature_{a.version}.csv", index=False, encoding="utf-8-sig")
    print(C["status"].value_counts().to_string())
    print(f"{len(agg)} unique works -> {out}")


def pdf_abstract(first):
    """Abstract from the first pages of a PDF (text between 'Abstract' and 'Keywords'/'Introduction')."""
    m = re.search(r"\babstract\b[:.\s]*(.{200,3000}?)(?:\bkey ?words\b|\bindex terms\b|\n\s*1\.?\s+introduction\b|\bintroduction\b)",
                  first, flags=re.I | re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def resolve(r, cr):
    out = _resolve(r, cr)
    if re.match(r"\s*(retracted|retraction|withdrawn)\b", out.get("title") or "", re.I):
        out["status"] = out.get("status", "") + "; RETRACTED"
    if r["source_type"] == "PDF library" and not out.get("abstract"):
        ab = pdf_abstract(r.get("pdf_first", ""))
        if ab:
            out["abstract"], out["abstract_source"] = ab, "PDF first page"
    elif out.get("abstract"):
        out["abstract_source"] = "Crossref"
    return out


def _resolve(r, cr):
    text = r["cited_text"]
    if r["source_type"] == "PDF library":
        ax = ARXIV_RX.search(pathlib.Path(r["source"]).stem) or ARXIV_RX.search(r.get("pdf_first", "")[:3000])
        if ax:
            m = cr.arxiv(ax.group(1))
            if m and m["title"]:
                pub = [h for h in cr.search(m["title"]) if contains_title(m["title"], h["title"]) >= 0.95 and h["type"] != "posted-content"]
                return dict(pub[0], status="PDF: arXiv preprint, published version found") if pub else dict(m, status="PDF: arXiv preprint")
        for d in (r.get("pdf_dois") or "").split(";"):
            m = d and cr.work(d)
            if m and (contains_title(r.get("pdf_first", ""), m["title"]) >= 0.8 or contains_title(r.get("pdf_title", ""), m["title"]) >= 0.8):
                return dict(m, status="PDF: DOI verified")
        hits = cr.search(r.get("pdf_title") or text) if (r.get("pdf_title") or len(text) > 30) else []
        for m in hits:
            if contains_title(r.get("pdf_first", ""), m["title"]) >= 0.9 and len(m["title"]) > 20:
                return dict(m, status="PDF: matched by title")
        return {"status": "PDF: unresolved", "title": r.get("pdf_title", "")}
    if r["source_type"] == "reference library" and r.get("bib_doi"):
        m = cr.work(r["bib_doi"])
        if m and contains_title(r.get("bib_title", ""), m["title"]) >= 0.7:
            return dict(m, status="library: DOI verified")
        if m:
            return dict(m, status="library: DOI does not match title")
    given = [norm_doi(d.rstrip(".,;)")) for d in DOI_RX.findall(text)]
    for d in given:
        m = cr.work(d)
        if m and contains_title(text, m["title"]) >= 0.6:
            return dict(m, status="DOI verified")
        if m and len(norm_title(text).split()) < 6:   # bare DOI with no title to check against
            return dict(m, status="DOI only (title not cited)")
    is_lib = r["source_type"] == "reference library" and len(r.get("bib_title") or "") > 20
    if not YEAR_RX.search(text) and not given and not is_lib:   # library entries are searched by title even without a year
        return {"status": "not scholarly"}
    if re.match(r"^\s*(https?://|www\.)", text) and not given:
        return {"status": "not scholarly"}
    for m in cr.search(r.get("bib_title") if is_lib else re.sub(DOI_RX, " ", text)):
        yr = YEAR_RX.search(text)
        ok_year = not yr or not m["year"] or abs(int(yr.group(1)) - int(m["year"])) <= 1
        if len(m["title"]) > 15 and contains_title(text, m["title"]) >= 0.85 and ok_year:
            return dict(m, status="DOI in citation does not match; corrected by title" if given else "matched by title")
    return {"status": "DOI in citation does not match; unresolved" if given else "unresolved"}


if __name__ == "__main__":
    main()
