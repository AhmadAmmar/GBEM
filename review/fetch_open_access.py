"""Retrieve open-access full texts of the focused-subset candidates.

    python fetch_open_access.py [--iteration <iteration folder>] [--all-core] [--limit N]

For every candidate with a DOI that has no PDF in the literature library yet, the open-access locations of the
work are looked up in OpenAlex (no account or e-mail address is sent) and the first location that returns a PDF
is saved to <Lit>/Review_fulltexts/. Only locations that OpenAlex marks as open access are used; nothing behind
a paywall is requested. A file is kept only if its first pages contain the DOI or the title of the work;
otherwise it is moved to <Lit>/Review_fulltexts/_unverified/.

The PDFs stay in the private literature folder and are not part of the repository. Every attempt is written to
<Lit>/Review_fulltexts/download_log.csv, so the run can be repeated and audited. Stage s04 then indexes the new
files like any other PDF of the library.
"""
import argparse, json, pathlib, re, sys, time, urllib.parse, urllib.request
import pandas as pd
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config as cfg
from common import norm_doi, norm_title, read_csv
from s04_fulltext import build_index, pdf_text

UA = {"User-Agent": "Mozilla/5.0 (compatible; systematic-review full-text retrieval; open-access locations only)"}
MAX_BYTES = 60 * 1024 * 1024


def get(url, timeout=60, accept=None):
    h = dict(UA)
    if accept:
        h["Accept"] = accept
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        return r.read(MAX_BYTES + 1), r.headers.get("Content-Type", "")


def openalex(dois):
    """OpenAlex records for a list of DOIs (batches of 40), keyed by normalised DOI."""
    out = {}
    for i in range(0, len(dois), 40):
        part = dois[i:i + 40]
        url = ("https://api.openalex.org/works?per-page=50&select=doi,title,open_access,best_oa_location,locations&filter=doi:"
               + "|".join(urllib.parse.quote("https://doi.org/" + d, safe=":/") for d in part))
        for attempt in range(6):
            try:
                data, _ = get(url, accept="application/json")
                for w in json.loads(data).get("results", []):
                    out[norm_doi(w.get("doi") or "")] = w
                break
            except Exception as e:
                time.sleep(6 + 6 * attempt)
        time.sleep(1.5)
    return out


def pdf_urls(w):
    """Open-access PDF addresses of one work, best location first."""
    locs = [w.get("best_oa_location") or {}] + [l for l in (w.get("locations") or []) if l.get("is_oa")]
    urls = []
    for l in locs:
        for u in (l.get("pdf_url"), l.get("landing_page_url")):
            if not u:
                continue
            m = re.search(r"arxiv\.org/abs/([\w.\-/]+)", u)
            if m:
                u = "https://arxiv.org/pdf/" + m.group(1)
            elif u == l.get("landing_page_url"):
                continue        # a landing page is not a PDF
            if u not in urls:
                urls.append(u)
    return urls


def matches(pdf, doi, title):
    t = pdf_text(pdf, 1, 3)
    if doi and doi.lower() in re.sub(r"\s+", "", t).lower():
        return True
    words = [x for x in norm_title(title).split() if len(x) > 3]
    head = norm_title(t[:6000])
    return bool(words) and sum(x in head for x in words) / len(words) >= 0.8


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iteration"); ap.add_argument("--all-core", action="store_true"); ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    its = sorted(p for p in (cfg.REVIEW / "iterations").glob("*_v*") if p.is_dir())
    P = cfg.paths(a.iteration or its[-1])
    dest = cfg.LIT / "Review_fulltexts"; (dest / "_unverified").mkdir(parents=True, exist_ok=True)
    sheet = read_csv(P["inputs"] / cfg.HUMAN["focused_extraction"])
    want = sheet[sheet["include_focused"].astype(str).str.upper().isin(["Y", "?"])][["doi", "title", "study"]]
    if a.all_core:
        dec = read_csv(P["out"] / "screening_decisions.csv")
        want = pd.concat([want, dec[dec["decision"] == "Included (core)"][["doi", "title"]]], ignore_index=True)
    want["d"] = want["doi"].map(norm_doi)
    want = want[want["d"] != ""].drop_duplicates("d")
    have = set(build_index(cfg, P)["doi_n"].dropna())
    todo = want[~want["d"].isin(have)]
    print(f"{len(want)} works with a DOI; {len(want) - len(todo)} already in the library; {len(todo)} to look up")
    if a.limit:
        todo = todo.head(a.limit)
    meta = openalex(list(todo["d"]))
    log_path = dest / "download_log.csv"
    log = read_csv(log_path).to_dict("records") if log_path.exists() else []
    done = {r["doi"] for r in log if r.get("status") == "saved"}
    for n, r in enumerate(todo.itertuples(), 1):
        if r.d in done:
            continue
        w = meta.get(r.d)
        row = {"doi": r.d, "title": (w or {}).get("title") or r.title, "date": time.strftime("%Y-%m-%d"),
               "oa_status": ((w or {}).get("open_access") or {}).get("oa_status", "") if w else "not in OpenAlex",
               "licence": ((w or {}).get("best_oa_location") or {}).get("license") or "", "url": "", "file": "", "status": ""}
        urls = pdf_urls(w) if w else []
        ax = re.match(r"(?:arxiv:|10\.48550/arxiv\.)(\d{4}\.\d{4,5})", r.d)     # arXiv preprints: the PDF address follows from the identifier
        if ax:
            urls.insert(0, "https://arxiv.org/pdf/" + ax.group(1)); row["oa_status"] = "green (arXiv)"
        if not urls:
            row["status"] = "no open-access PDF location"
        for u in urls:
            try:
                data, ctype = get(u)
            except Exception as e:
                row["status"], row["url"] = "request failed: " + str(e)[:60], u; continue
            if not data.startswith(b"%PDF") or len(data) > MAX_BYTES:
                row["status"], row["url"] = "location did not return a PDF", u; continue
            f = dest / (re.sub(r"[^A-Za-z0-9._-]+", "_", r.d) + ".pdf")
            f.write_bytes(data)
            if matches(f, r.d, row["title"] or ""):
                row.update(status="saved", url=u, file=f.name); break
            f.replace(dest / "_unverified" / f.name)
            row.update(status="PDF does not match the work (moved to _unverified)", url=u, file="_unverified/" + f.name)
        log = [x for x in log if x.get("doi") != r.d] + [row]
        if n % 10 == 0 or n == len(todo):
            pd.DataFrame(log).to_csv(log_path, index=False, encoding="utf-8-sig")
            print(f"  {n}/{len(todo)}  saved so far: {sum(x.get('status') == 'saved' for x in log)}", flush=True)
        time.sleep(1.0)
    pd.DataFrame(log).to_csv(log_path, index=False, encoding="utf-8-sig")
    print(pd.DataFrame(log)["status"].str.replace(r":.*", "", regex=True).value_counts().to_string())


if __name__ == "__main__":
    main()
