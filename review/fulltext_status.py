"""Live checklist of the full texts still to retrieve, with their status in Zotero and in the review folder.

    python fulltext_status.py                 # one pass: collect, update the status, (re)write the checklist page
    python fulltext_status.py --watch 60      # repeat every 60 seconds until stopped with Ctrl+C

The checklist (<Lit>/Review_fulltexts/remaining_to_download.html) lists the candidates for the focused subset that
the triage rates likely or unclear and that had no PDF when the list was made. Each pass of this script
  1. copies newly saved, review-relevant PDFs from Zotero and from the download folders (DOWNLOAD_DIRS) to
     <Lit>/Review_fulltexts/ (collect_fulltexts.collect: copy only, manifest and log updated),
  2. looks every listed work up in a copy of the Zotero database and in the review folder,
  3. gives Zotero the review PDFs it does not hold yet (saved by hand or downloaded) through Zotero's own connector
     service, as the browser Connector does; Zotero recognises each paper and files it in the collection
     fulltext_to_download (each file once; zotero_push_log.csv). Zotero has to be running.
  4. writes remaining_status.js next to the page. The page reads that file when it is opened and again every
     30 seconds, so the status of each row (PDF in the review folder; PDF in Zotero; record in Zotero without a PDF;
     not in Zotero) updates without reloading, while this script runs in watch mode.
A row whose PDF has reached the review folder is ticked automatically. Manual ticks are kept in the browser.
"""
import argparse, datetime, html, json, pathlib, re, shutil, sqlite3, sys, tempfile, time, urllib.request, uuid
import pandas as pd
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config as cfg
from common import norm_doi, norm_title, read_csv
from collect_fulltexts import collect

PUB = {"10.1016": "Elsevier (ScienceDirect)", "10.3390": "MDPI", "10.1007": "Springer", "10.1109": "IEEE", "10.1088": "IOP", "10.1111": "Wiley",
       "10.1002": "Wiley", "10.1080": "Taylor & Francis", "10.1177": "Sage", "10.1117": "SPIE", "10.1061": "ASCE", "10.1145": "ACM"}
LABEL = {"folder": "PDF in the review folder", "zotero_pdf": "PDF in Zotero (copied on the next pass)",
         "zotero_record": "In Zotero without a PDF: save the PDF again", "missing": "Not in Zotero yet"}


def zotero_items(zdir):
    """Every regular Zotero record with its DOI, title, collections and whether a PDF file is attached."""
    with tempfile.TemporaryDirectory() as tmp:
        for ext in ("", "-wal", "-shm"):
            if (zdir / ("zotero.sqlite" + ext)).exists():
                shutil.copy(zdir / ("zotero.sqlite" + ext), pathlib.Path(tmp) / ("zotero.sqlite" + ext))
        con = sqlite3.connect(str(pathlib.Path(tmp) / "zotero.sqlite"))
        items = pd.read_sql_query(
            "SELECT i.itemID, i.key FROM items i JOIN itemTypes t ON t.itemTypeID = i.itemTypeID "
            "WHERE t.typeName NOT IN ('attachment', 'note', 'annotation') AND i.itemID NOT IN (SELECT itemID FROM deletedItems)", con)
        data = pd.read_sql_query("SELECT d.itemID, f.fieldName, v.value FROM itemData d JOIN fields f ON f.fieldID = d.fieldID "
                                 "JOIN itemDataValues v ON v.valueID = d.valueID WHERE f.fieldName IN ('DOI', 'title', 'extra')", con)
        att = pd.read_sql_query("SELECT ia.parentItemID, ai.key, ia.path FROM itemAttachments ia JOIN items ai ON ai.itemID = ia.itemID "
                                "WHERE ia.path LIKE 'storage:%' AND ia.itemID NOT IN (SELECT itemID FROM deletedItems)", con)
        coll = pd.read_sql_query("SELECT ci.itemID, c.collectionName FROM collectionItems ci JOIN collections c ON c.collectionID = ci.collectionID", con)
        con.close()
    w = data.pivot_table(index="itemID", columns="fieldName", values="value", aggfunc="first")
    items["DOI"] = items["itemID"].map(w["DOI"]) if "DOI" in w else ""
    # some item types keep the DOI in the Extra field ("DOI: 10....")
    extra = items["itemID"].map(w["extra"]) if "extra" in w else pd.Series("", index=items.index)
    items["DOI"] = items["DOI"].fillna(extra.fillna("").str.extract(r"DOI:\s*(10\.\S+)", flags=re.I)[0])
    items["title"] = items["itemID"].map(w["title"]) if "title" in w else ""
    att["pdf"] = [p.lower().endswith(".pdf") and (zdir / "storage" / k / p.split(":", 1)[1]).exists() for k, p in zip(att["key"], att["path"])]
    has_pdf = set(att.loc[att["pdf"], "parentItemID"].dropna().astype(int))
    items["has_pdf"] = items["itemID"].isin(has_pdf)
    items["collections"] = items["itemID"].map(coll.groupby("itemID")["collectionName"].agg(lambda s: "; ".join(sorted(set(s))))).fillna("")
    items["d"], items["tn"] = items["DOI"].map(norm_doi), items["title"].fillna("").map(norm_title)
    return items


def checklist(P):
    """The works to retrieve: the iteration's list, likely ones first."""
    L = read_csv(P["out"] / "fulltext_to_download.csv").fillna("")
    L["d"] = L["doi_link"].map(norm_doi)
    L["tn"] = L["title"].map(norm_title)
    L["publisher"] = L["d"].str.extract(r"^(10\.\d+)")[0].map(lambda p: PUB.get(p, "Other") if isinstance(p, str) else "No DOI")
    L["o"] = L["triage"].map({"Likely": 0, "Unclear": 1})
    L = L.sort_values(["o", "publisher", "year"], ascending=[True, True, False]).drop(columns="o").reset_index(drop=True)
    L["id"] = ["w" + (r.d or r.tn)[:120] for r in L.itertuples()]
    L["id"] = L["id"].str.replace(r"[^A-Za-z0-9]+", "_", regex=True)
    return L


def status(L, dest):
    zdir = getattr(cfg, "ZOTERO", None)
    Z = zotero_items(zdir) if zdir and (zdir / "zotero.sqlite").exists() else pd.DataFrame(columns=["d", "tn", "has_pdf", "collections", "key"])
    man = read_csv(dest / "fulltext_manifest.csv").fillna("") if (dest / "fulltext_manifest.csv").exists() else pd.DataFrame(columns=["doi", "title", "file"])
    fd = dict(zip(man["doi"].map(norm_doi), man["file"])); ft = dict(zip(man["title"].map(norm_title), man["file"]))
    out = {}
    for r in L.itertuples():
        z = Z[(Z["d"] == r.d)] if r.d else Z.iloc[0:0]
        if not len(z) and len(r.tn) > 25:
            z = Z[Z["tn"] == r.tn]
        f = fd.get(r.d) if r.d else None
        f = f or ft.get(r.tn)
        s = "folder" if f else ("zotero_pdf" if len(z) and z["has_pdf"].any() else ("zotero_record" if len(z) else "missing"))
        out[r.id] = {"status": s, "label": LABEL[s], "file": f or "", "zotero": "; ".join(sorted(set("; ".join(z["collections"]).split("; ")) - {""}))[:120],
                     "records": int(len(z)), "in_zotero_with_pdf": bool(len(z) and z["has_pdf"].any()),
                     "zotero_keys": "; ".join(z["key"]) if "key" in z else "", "title": r.title, "doi": r.d}
    # PDFs that reached the review folder outside Zotero (saved by hand): their Zotero records still lack the file
    todo = [{"title": v["title"], "doi": v["doi"], "pdf": str(dest / v["file"]), "zotero_records": v["zotero_keys"]}
            for v in out.values() if v["status"] == "folder" and not v["in_zotero_with_pdf"]]
    pd.DataFrame(todo, columns=["title", "doi", "pdf", "zotero_records"]).to_csv(dest / "zotero_to_attach.csv", index=False, encoding="utf-8-sig")
    return out


CONNECTOR = "http://127.0.0.1:23119/connector/"


def connector(endpoint, data, headers):
    req = urllib.request.Request(CONNECTOR + endpoint, data=data, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.status, r.read()


def push_to_zotero(dest, collection="fulltext_to_download", say=print):
    """Give Zotero the review PDFs that it does not hold yet (saved by hand or downloaded), through Zotero's own
    connector service, as the browser Connector does: Zotero stores the file, recognises the paper and files it in the
    collection. Each file is offered once (zotero_push_log.csv). Nothing happens if Zotero is not running."""
    zdir = getattr(cfg, "ZOTERO", None)
    man = dest / "fulltext_manifest.csv"
    if not zdir or not man.exists():
        return 0
    try:
        urllib.request.urlopen(CONNECTOR + "ping", timeout=5).read()
    except Exception:
        say("Zotero is not running: PDFs not offered to Zotero in this pass"); return 0
    M = read_csv(man).fillna("")
    M = M[~M["origin"].str.startswith("Zotero attachment") & M["review_status"].ne("not matched to a record of the review")]
    Z = zotero_items(zdir)
    in_z = set(Z.loc[Z["has_pdf"], "d"]) - {""}
    lp = dest / "zotero_push_log.csv"
    done = set(read_csv(lp)["sha256"]) if lp.exists() else set()
    todo = M[~M["doi"].map(norm_doi).isin(in_z) & ~M["sha256"].isin(done)]
    if not len(todo):
        return 0
    try:
        _, b = connector("getSelectedCollection", b"{}", {"Content-Type": "application/json"})
        target = next((t["id"] for t in json.loads(b).get("targets", []) if t.get("name") == collection), None)
    except Exception:
        target = None
    log = []
    for r in todo.itertuples():
        sid = uuid.uuid4().hex
        meta = {"sessionID": sid, "title": r.title or r.file, "url": ("https://doi.org/" + r.doi) if r.doi else ""}
        row = {"date": datetime.date.today().isoformat(), "file": r.file, "doi": r.doi, "sha256": r.sha256, "collection": collection if target else "(selected collection)"}
        try:
            st, b = connector("saveStandaloneAttachment", (dest / r.file).read_bytes(), {"Content-Type": "application/pdf", "X-Metadata": json.dumps(meta)})
            if target:
                connector("updateSession", json.dumps({"sessionID": sid, "target": target}).encode(), {"Content-Type": "application/json"})
            row["result"] = f"saved in Zotero (HTTP {st})"
        except Exception as e:
            row["result"] = "failed: " + str(e)[:80]
        log.append(row)
        time.sleep(3)          # Zotero recognises each PDF in turn
    pd.concat([read_csv(lp), pd.DataFrame(log)] if lp.exists() else [pd.DataFrame(log)], ignore_index=True).to_csv(lp, index=False, encoding="utf-8-sig")
    return sum(x["result"].startswith("saved") for x in log)


def write_status(dest, st):
    counts = {k: sum(v["status"] == k for v in st.values()) for k in LABEL}
    payload = {"updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "counts": counts, "labels": LABEL, "rows": st}
    tmp = dest / "remaining_status.js.tmp"
    tmp.write_text("window.FT_STATUS = " + json.dumps(payload, ensure_ascii=False) + ";\n", encoding="utf-8")
    tmp.replace(dest / "remaining_status.js")
    pd.DataFrame([{"id": k, **v} for k, v in st.items()]).to_csv(dest / "remaining_status.csv", index=False, encoding="utf-8-sig")
    return counts


def write_page(dest, L):
    e = html.escape
    rows = []
    for i, r in enumerate(L.itertuples(), 1):
        q = re.sub(r"\s+", "+", str(r.title))
        link = (f'<a href="{e(r.doi_link)}" target="_blank" rel="noopener">{e(r.doi_link.replace("https://doi.org/", ""))}</a>' if r.doi_link else
                f'<a href="https://scholar.google.com/scholar?q={e(q)}" target="_blank" rel="noopener">search by title</a>')
        oa = f' &middot; <a href="{e(r.open_access_pdf)}" target="_blank" rel="noopener">open-access PDF</a>' if r.open_access_pdf else ""
        yr = str(int(float(r.year))) if str(r.year).strip() else ""
        rows.append(f'<tr id="{r.id}" class="{r.triage.lower()}"><td><input type="checkbox" aria-label="done"></td><td>{i}</td>'
                    f'<td><span class="tag">{e(r.triage)}</span></td><td>{e(str(r.study))} ({yr})<br>{e(str(r.title))}</td>'
                    f'<td>{e(r.publisher)}</td><td>{link}{oa}</td><td class="st"><span class="dot"></span><span class="lab">waiting for status</span><div class="sub"></div></td></tr>')
    page = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Full texts to retrieve</title>
<style>
:root { --bg:#ffffff; --fg:#1c2530; --mut:#5b6672; --line:#d9dee4; --likely:#1f6f43; --unclear:#8a5a00; --link:#1a4f8b;
        --ok:#1f7a45; --zot:#2b62b0; --warn:#b35c00; --none:#8a939d; }
@media (prefers-color-scheme: dark) { :root { --bg:#14181d; --fg:#e6eaee; --mut:#9aa5b1; --line:#2c343d; --likely:#6fd09a; --unclear:#e0b060;
        --link:#8fbcf0; --ok:#5fd08d; --zot:#7fb0f5; --warn:#f0a05a; --none:#7d8791; } }
body { background:var(--bg); color:var(--fg); font:15px/1.45 system-ui, Segoe UI, sans-serif; margin:0; padding:20px 16px 60px; }
main { max-width:1200px; margin:0 auto; } h1 { font-size:1.35rem; margin:0 0 6px; } p, ol { color:var(--mut); max-width:80ch; }
.summary { display:flex; flex-wrap:wrap; gap:8px 18px; margin:10px 0 14px; font-size:.9rem; }
.summary span b { font-variant-numeric:tabular-nums; }
.filters { margin:0 0 10px; font-size:.9rem; color:var(--mut); } .filters label { margin-right:14px; }
table { border-collapse:collapse; width:100%; } th, td { text-align:left; vertical-align:top; padding:7px 8px; border-bottom:1px solid var(--line); }
th { font-size:.8rem; color:var(--mut); font-weight:600; position:sticky; top:0; background:var(--bg); }
a { color:var(--link); word-break:break-all; } .tag { font-size:.75rem; font-weight:600; }
.likely .tag { color:var(--likely); } .unclear .tag { color:var(--unclear); }
.st { font-size:.82rem; min-width:150px; } .sub { color:var(--mut); font-size:.75rem; }
.dot { display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:6px; background:var(--none); }
tr.s-folder .dot { background:var(--ok); } tr.s-zotero_pdf .dot { background:var(--zot); } tr.s-zotero_record .dot { background:var(--warn); }
tr.s-folder td:not(.st) { opacity:.45; } tr.s-zotero_record .lab { color:var(--warn); font-weight:600; }
.hide-done tr.s-folder { display:none; } .wrap { overflow-x:auto; }
</style></head><body><main>
<h1>Full texts to retrieve (__N__)</h1>
<p>Candidates for the focused subset that the triage rates likely or unclear and that had no PDF when this list was made
(__LIKELY__ likely, __UNCLEAR__ unclear; list made __DATE__). The status column is filled in by <code>fulltext_status.py</code>; while it runs with
<code>--watch</code>, this page refreshes the status every 30 seconds without reloading.</p>
<ol><li>On the university network, click a DOI. The article opens in a new tab.</li>
<li>Click the Zotero Connector button and check that the save panel lists a <em>Full Text PDF</em>. If it is greyed out, open the PDF and save it from there.</li>
<li>The row turns green once the PDF has reached the review folder.</li></ol>
<div class="summary" id="summary">Status not loaded yet: run <code>python code/review/fulltext_status.py --watch 60</code>.</div>
<div class="filters"><label><input type="checkbox" id="hidedone"> hide rows already in the review folder</label></div>
<div class="wrap"><table id="t"><thead><tr><th>Done</th><th>#</th><th>Triage</th><th>Study and title</th><th>Publisher</th><th>Link</th><th>Status</th></tr></thead><tbody>
__ROWS__
</tbody></table></div></main>
<script>
function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }
document.querySelectorAll('#t tbody tr').forEach(function (tr) {
  var c = tr.querySelector('input'); c.checked = store('ft-' + tr.id) === '1';
  c.addEventListener('change', function () { store('ft-' + tr.id, c.checked ? '1' : '0'); });
});
var hd = document.getElementById('hidedone');
hd.checked = store('ft-hide') === '1'; document.body.classList.toggle('hide-done', hd.checked);
hd.addEventListener('change', function () { document.body.classList.toggle('hide-done', hd.checked); store('ft-hide', hd.checked ? '1' : '0'); });
function apply() {
  var S = window.FT_STATUS; if (!S) return;
  document.querySelectorAll('#t tbody tr').forEach(function (tr) {
    var s = S.rows[tr.id]; if (!s) return;
    tr.className = tr.className.replace(/\\bs-\\S+/g, '').trim() + ' s-' + s.status;
    tr.querySelector('.lab').textContent = s.label;
    tr.querySelector('.sub').textContent = s.status === 'folder' ? (s.in_zotero_with_pdf ? s.file : s.file + ' (not attached in Zotero yet)')
                                         : (s.zotero ? 'Zotero: ' + s.zotero : '');
    if (s.status === 'folder') tr.querySelector('input').checked = true;
  });
  var c = S.counts, L = S.labels, el = document.getElementById('summary'); el.textContent = '';
  ['folder', 'zotero_pdf', 'zotero_record', 'missing'].forEach(function (k) {
    var sp = document.createElement('span'); var b = document.createElement('b'); b.textContent = c[k];
    sp.appendChild(b); sp.appendChild(document.createTextNode(' ' + L[k].replace(/:.*$/, '').replace(/ \\(.*\\)$/, '')));
    el.appendChild(sp);
  });
  var u = document.createElement('span'); u.textContent = 'status of ' + S.updated; u.style.color = 'var(--mut)'; el.appendChild(u);
}
function load() {
  var old = document.getElementById('ftstatus'); if (old) old.remove();
  var s = document.createElement('script'); s.id = 'ftstatus'; s.src = 'remaining_status.js?t=' + Date.now(); s.onload = apply;
  document.head.appendChild(s);
}
load(); setInterval(load, 30000);
</script></body></html>"""
    page = (page.replace("__N__", str(len(L))).replace("__LIKELY__", str(int((L.triage == "Likely").sum())))
                .replace("__UNCLEAR__", str(int((L.triage == "Unclear").sum()))).replace("__DATE__", datetime.date.today().isoformat())
                .replace("__ROWS__", "\n".join(rows)))
    (dest / "remaining_to_download.html").write_text(page, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iteration"); ap.add_argument("--watch", type=int, default=0, help="seconds between passes; 0 = one pass")
    ap.add_argument("--no-collect", action="store_true", help="only report the status, do not copy PDFs")
    ap.add_argument("--no-zotero", action="store_true", help="do not offer hand-saved PDFs to Zotero")
    a = ap.parse_args()
    its = sorted(p for p in (cfg.REVIEW / "iterations").glob("*_v*") if p.is_dir())
    P = cfg.paths(a.iteration or max(its, key=lambda p: p.stat().st_mtime))
    dest = cfg.LIT / "Review_fulltexts"; dest.mkdir(parents=True, exist_ok=True)
    L = checklist(P)
    write_page(dest, L)
    print(f"Checklist: {len(L)} works from {P['it'].name}; page {dest / 'remaining_to_download.html'}")
    while True:
        if not a.no_collect:
            log = collect(P, dest, manifest="if changed", only_new_in_log=True, say=lambda *x: None)
            n = int((log["action"] == "copied").sum()) if len(log) else 0
        else:
            n = 0
        z = 0 if a.no_zotero else push_to_zotero(dest)
        c = write_status(dest, status(L, dest))
        print(f"{datetime.datetime.now():%H:%M:%S}  copied {n} new PDF(s); gave {z} to Zotero; " + ", ".join(f"{LABEL[k].split(':')[0].split(' (')[0]}: {v}" for k, v in c.items()), flush=True)
        if not a.watch:
            break
        time.sleep(a.watch)


if __name__ == "__main__":
    main()
