"""References from DOIs, verified on Crossref, written to BibTeX and recorded in Zotero.

    python doi_bib.py <out.bib> key=doi [key=doi ...] [--collection "PhD citations"]
    python doi_bib.py --push-queue                      (offer queued references to Zotero again)
    e.g. python doi_bib.py refs.bib roberts2017=10.1111/ecog.02881 meyer2021=10.1111/2041-210X.13650

1. Each DOI is looked up in the Crossref API (title, journal and year are printed for checking); unresolved DOIs are
   reported and left out. The BibTeX record comes from doi.org by content negotiation; the entry key is replaced by
   the given key, dashes are kept as -- / ---, month fields are removed (month names break several BibTeX styles) and
   the text is converted to ASCII (BibTeX 0.99 is not UTF-8 safe). An existing .bib is archived (safeio.keep).
2. Every verified reference is offered to Zotero through its local connector (as the browser Connector does), into
   the collection given (or the collection selected in Zotero), unless Zotero already holds that DOI. Zotero then
   finds the PDF with "Find Full Text" (open access or library access). If Zotero is not running, the references are
   queued in code/docs/zotero_queue.csv and offered next time (--push-queue, or the next run).
"""
import csv, datetime, json, pathlib, re, shutil, sqlite3, sys, tempfile, unicodedata, urllib.request, uuid
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

HDR = {"User-Agent": "research-bibliography/1.0"}
CONNECTOR = "http://127.0.0.1:23119/connector/"
QUEUE = pathlib.Path(__file__).with_name("zotero_queue.csv")
ZOTERO_DIR = pathlib.Path(r"D:\Zotero")


def crossref(doi):
    return json.loads(urllib.request.urlopen(urllib.request.Request(f"https://api.crossref.org/works/{doi}", headers=HDR), timeout=60).read())["message"]


def bibtex(key, doi):
    bib = urllib.request.urlopen(urllib.request.Request(f"https://doi.org/{doi}", headers={**HDR, "Accept": "application/x-bibtex"}), timeout=60).read().decode("utf-8")
    bib = re.sub(r"@(\w+)\{[^,]+,", lambda x: f"@{x.group(1)}{{{key},", bib, count=1)
    bib = bib.replace("\u2013", "--").replace("\u2014", "---").replace("\u2010", "-").replace("\u2011", "-")
    bib = re.sub(r",\s*month\s*=\s*\{?\w+\}?", "", bib)
    return unicodedata.normalize("NFKD", bib).encode("ascii", "ignore").decode().strip()


def zotero_item(m):
    """Crossref record -> Zotero connector item"""
    kind = {"journal-article": "journalArticle", "proceedings-article": "conferencePaper", "book-chapter": "bookSection",
            "book": "book", "report": "report", "dataset": "dataset"}.get(m.get("type"), "journalArticle")
    date = "-".join(str(p) for p in (m.get("issued", {}).get("date-parts") or [[None]])[0] if p)
    item = {"itemType": kind, "title": (m.get("title") or [""])[0], "DOI": m.get("DOI", ""), "url": f"https://doi.org/{m.get('DOI', '')}",
            "date": date, "volume": m.get("volume", ""), "issue": m.get("issue", ""), "pages": m.get("page", "").replace("-", "–"),
            "creators": [{"firstName": a.get("given", ""), "lastName": a.get("family", a.get("name", "")), "creatorType": "author"} for a in m.get("author", [])],
            "attachments": [], "tags": [{"tag": "cited"}]}
    venue = (m.get("container-title") or [""])[0]
    item["publicationTitle" if kind == "journalArticle" else "proceedingsTitle" if kind == "conferencePaper" else "bookTitle"] = venue
    return item


def zotero_dois():
    """DOIs already in the Zotero library (read from a copy of zotero.sqlite; Zotero keeps the file locked)"""
    db = ZOTERO_DIR / "zotero.sqlite"
    if not db.exists():
        return set()
    tmp = pathlib.Path(tempfile.mkdtemp()) / "z.sqlite"
    shutil.copy2(db, tmp)
    con = sqlite3.connect(tmp)
    rows = con.execute("SELECT v.value FROM itemData d JOIN fields f USING(fieldID) JOIN itemDataValues v USING(valueID) WHERE f.fieldName='DOI'").fetchall()
    con.close()
    return {r[0].lower() for r in rows}


def connector(endpoint, payload):
    req = urllib.request.Request(CONNECTOR + endpoint, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Zotero-Connector-API-Version": "3"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.read()


def to_zotero(records, collection):
    """records: list of (doi, crossref message); returns the ones not delivered (Zotero closed or failed)"""
    try:
        connector("ping", {})
    except Exception:
        return records
    have = zotero_dois()
    todo = [(d, m) for d, m in records if d.lower() not in have]
    target = None
    try:
        _, b = connector("getSelectedCollection", {})
        target = next((t["id"] for t in json.loads(b).get("targets", []) if t.get("name") == collection), None)
    except Exception:
        pass
    failed = []
    for d, m in todo:
        sid = uuid.uuid4().hex
        try:
            connector("saveItems", {"sessionID": sid, "uri": f"https://doi.org/{d}", "items": [zotero_item(m)]})
            if target:
                connector("updateSession", {"sessionID": sid, "target": target})
            print("  Zotero: added", d)
        except Exception as e:
            print("  Zotero: failed", d, str(e)[:80]); failed.append((d, m))
    print(f"  Zotero: {len(records) - len(todo)} already there, {len(todo) - len(failed)} added")
    return failed


def queue(records, collection):
    new = not QUEUE.exists()
    with open(QUEUE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "doi", "collection"])
        for d, _ in records:
            w.writerow([datetime.date.today().isoformat(), d, collection])
    print(f"  Zotero not running: {len(records)} references queued in {QUEUE.name}")


def push_queue():
    if not QUEUE.exists():
        return
    rows = list(csv.DictReader(open(QUEUE, encoding="utf-8")))
    left = []
    for coll in {r["collection"] for r in rows}:
        recs = [(r["doi"], crossref(r["doi"])) for r in rows if r["collection"] == coll]
        left += [(d, coll) for d, _ in to_zotero(recs, coll)]
    keep(QUEUE)
    if left:
        with open(QUEUE, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["date", "doi", "collection"])
            w.writerows([[datetime.date.today().isoformat(), d, c] for d, c in left])
    print(f"queue: {len(rows) - len(left)} delivered, {len(left)} still queued")


def main():
    args = sys.argv[1:]
    if args == ["--push-queue"]:
        return push_queue()
    collection = "PhD citations"
    if "--collection" in args:
        i = args.index("--collection"); collection = args[i + 1]; del args[i:i + 2]
    out, pairs = pathlib.Path(args[0]), [a.split("=", 1) for a in args[1:]]
    entries, records = [], []
    for key, doi in pairs:
        try:
            m = crossref(doi)
            entries.append(bibtex(key, doi)); records.append((doi, m))
            print("OK", key, "|", (m.get("title") or [""])[0][:90], "|", (m.get("container-title") or [""])[0],
                  (m.get("issued", {}).get("date-parts") or [[None]])[0][0])
        except Exception as e:
            print("NOT FOUND", key, doi, e)
    keep(out).write_text("\n\n".join(entries) + "\n", encoding="ascii")
    print(f"{len(entries)} of {len(pairs)} references -> {out}")
    left = to_zotero(records, collection)
    if left:
        queue(left, collection)
    elif QUEUE.exists():
        push_queue()


if __name__ == "__main__":
    main()
