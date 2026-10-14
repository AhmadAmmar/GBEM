"""Collect the full texts of the review in one folder, with a record of where every file came from.

    python collect_fulltexts.py [--iteration <iteration folder>] [--dry-run]

1. Zotero. The Zotero data folder (ZOTERO_DIR in local_settings.py) keeps each attachment as
   storage/<8-character key>/<file>.pdf and links it to its bibliographic record in zotero.sqlite. A copy of the
   database is read (the live file is never opened), every PDF attachment is matched to the records of the review
   by DOI, or by title where there is no DOI, and the matching PDFs are copied to <Lit>/Review_fulltexts/.
2. Download folders. PDFs saved by hand from a browser (DOWNLOAD_DIRS in local_settings.py, for example the
   Downloads folder) are read on their first pages; a file whose DOI, or failing that title, belongs to a record
   of the review is copied in the same way. The files in the download folders are left where they are.
3. Manifest. <Lit>/Review_fulltexts/fulltext_manifest.csv lists every PDF in that folder with its DOI, its status
   in the review, its origin (open-access download, Zotero attachment, or placed by hand), its SHA-256 and the
   date it was first recorded. Each run adds to <Lit>/Review_fulltexts/collect_log.csv.

Files are only ever copied. Nothing is moved, renamed or deleted, in Zotero or in the literature folder. If a
different file already has the target name, the new copy gets the Zotero key appended to its name.
Only works that the review screened as included, as a review article, or as a candidate are collected; the rest of
the Zotero library is left alone.
"""
import argparse, datetime, hashlib, json, pathlib, re, shutil, sqlite3, sys, tempfile
import pandas as pd
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config as cfg
from common import norm_doi, norm_title, read_csv

KEEP = ("Included (core)", "Review (umbrella)")


_SHA = {}


def sha256(p):
    s = pathlib.Path(p).stat(); k = (str(p), s.st_mtime, s.st_size)
    if k in _SHA:
        return _SHA[k]
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    _SHA[k] = h.hexdigest()
    return _SHA[k]


def zotero_attachments(zdir):
    """PDF attachments of the Zotero library with the DOI, title and collections of their parent records."""
    with tempfile.TemporaryDirectory() as tmp:
        for ext in ("", "-wal", "-shm"):     # a copy, so that the running application is not disturbed
            src = zdir / ("zotero.sqlite" + ext)
            if src.exists():
                shutil.copy(src, pathlib.Path(tmp) / src.name)
        con = sqlite3.connect(str(pathlib.Path(tmp) / "zotero.sqlite"))
        att = pd.read_sql_query(
            "SELECT ia.itemID AS att_id, ai.key AS att_key, ia.path, ia.parentItemID AS parent_id, pi.key AS parent_key "
            "FROM itemAttachments ia JOIN items ai ON ai.itemID = ia.itemID LEFT JOIN items pi ON pi.itemID = ia.parentItemID "
            "WHERE ia.path LIKE 'storage:%' AND ia.itemID NOT IN (SELECT itemID FROM deletedItems)", con)
        data = pd.read_sql_query(
            "SELECT d.itemID, f.fieldName, v.value FROM itemData d JOIN fields f ON f.fieldID = d.fieldID "
            "JOIN itemDataValues v ON v.valueID = d.valueID WHERE f.fieldName IN ('DOI', 'title', 'date')", con)
        coll = pd.read_sql_query("SELECT ci.itemID, c.collectionName FROM collectionItems ci JOIN collections c ON c.collectionID = ci.collectionID", con)
        con.close()
    wide = data.pivot_table(index="itemID", columns="fieldName", values="value", aggfunc="first")
    colls = coll.groupby("itemID")["collectionName"].agg(lambda s: "; ".join(sorted(set(s))))
    att["item"] = att["parent_id"].fillna(att["att_id"]).astype(int)       # stand-alone PDFs carry their own fields
    for c in ("DOI", "title", "date"):
        att[c] = att["item"].map(wide[c]) if c in wide else ""
    att["collections"] = att["item"].map(colls).fillna("")
    att["file"] = [zdir / "storage" / k / p.split(":", 1)[1] for k, p in zip(att["att_key"], att["path"])]
    att = att[[f.suffix.lower() == ".pdf" and f.exists() for f in att["file"]]].copy()
    att["d"], att["tn"] = att["DOI"].map(norm_doi), att["title"].fillna("").map(norm_title)
    return att


def review_status(P):
    """Status in the review of every screened record, keyed by DOI and by normalised title."""
    dec = read_csv(P["out"] / "screening_decisions.csv")
    dec["d"], dec["tn"] = dec["doi"].map(norm_doi), dec["title"].map(norm_title)
    dec["status"] = dec["decision"].map({"Included (core)": "core study", "Review (umbrella)": "review article (context)"}).fillna("screened, not included")
    sheet = read_csv(P["inputs"] / cfg.HUMAN["focused_extraction"])
    sheet["d"], sheet["tn"] = sheet["doi"].map(norm_doi), sheet["title"].fillna("").map(norm_title)
    tri = read_csv(P["out"] / "focused_triage.csv") if (P["out"] / "focused_triage.csv").exists() else pd.DataFrame(columns=["doi", "title", "triage"])
    tri_d = dict(zip(tri["doi"].map(norm_doi), tri["triage"])); tri_t = dict(zip(tri["title"].fillna("").map(norm_title), tri["triage"]))
    foc = {}
    for r in sheet.itertuples():
        y = str(r.include_focused).upper()
        s = "focused study (included)" if y == "Y" else ("focused candidate: " + str(tri_d.get(r.d) or tri_t.get(r.tn) or "pending") if y == "?" else None)
        if s:
            foc[r.d or "t:" + r.tn] = s; foc["t:" + r.tn] = s
    by_d, by_t = {}, {}
    for r in dec.itertuples():
        s = foc.get(r.d) or foc.get("t:" + r.tn) or r.status
        if r.d:
            by_d[r.d] = (s, r.title)
        by_t[r.tn] = (s, r.title)
    for r in sheet.itertuples():       # focused studies identified by other routes may not be among the screened records
        s = foc.get(r.d or "t:" + r.tn)
        if s and r.d and r.d not in by_d:
            by_d[r.d] = (s, r.title if isinstance(r.title, str) else "")
    return by_d, by_t


def pdf_head(f, cache):
    """DOI and normalised text of the first two pages of a PDF (cached by path, time and size)."""
    from s04_fulltext import pdf_text
    s = f.stat(); k = f"{f}|{s.st_mtime}|{s.st_size}"
    if k not in cache:
        t = pdf_text(f, 1, 2)
        m = re.search(r"10\.\d{4,9}/[^\s\"<>]+", t)
        cache[k] = {"doi": norm_doi(m.group(0).rstrip(".,;)")) if m else "", "head": norm_title(t[:8000])}
    return cache[k]


def from_download_dirs(dest, by_d, by_t, have, today, dry_run, say):
    """Copy review PDFs saved by hand in the download folders; the originals stay where they are."""
    dirs = [d for d in getattr(cfg, "DOWNLOAD_DIRS", []) if d.exists()]
    if not dirs:
        return []
    cp = dest / ".pdf_head_cache.json"
    try:
        cache = json.loads(cp.read_text(encoding="utf-8")) if cp.exists() else {}
    except Exception:
        cache = {}
    titles = [(tn, v) for tn, v in by_t.items() if len(tn) > 30 and v[0] != "screened, not included"]
    log = []
    for d in dirs:
        for f in sorted({x for x in d.iterdir() if x.is_file() and x.suffix.lower() == ".pdf"}):
            try:
                h0 = pdf_head(f, cache)
            except Exception:
                continue
            hit, doi = (by_d.get(h0["doi"]), h0["doi"]) if h0["doi"] else (None, "")
            if not hit or hit[0] == "screened, not included":
                hit = next((v for tn, v in titles if tn in h0["head"]), None)
                doi = next((k for k, v in by_d.items() if v is hit), doi) if hit else doi
            if not hit or hit[0] == "screened, not included":
                continue
            h = sha256(f)
            row = {"date": today, "doi": doi, "title": hit[1], "status": hit[0], "zotero_key": "", "zotero_collections": "", "source_file": str(f), "sha256": h}
            if h in have:
                row.update(action="already in the folder (same content)", file=have[h])
            else:
                name = (re.sub(r"[^A-Za-z0-9._-]+", "_", doi) if doi else "title_" + re.sub(r"\s+", "_", norm_title(hit[1]))[:80]) + ".pdf"
                if (dest / name).exists():
                    name = name[:-4] + "__download-" + h[:8] + ".pdf"
                if not dry_run:
                    shutil.copy2(f, dest / name)
                have[h] = name
                row.update(action="copied" if not dry_run else "would be copied", file=name)
            log.append(row)
    try:
        cp.write_text(json.dumps(cache), encoding="utf-8")
    except Exception:
        pass
    say(f"Download folders: {len(log)} review PDFs found in {', '.join(map(str, dirs))}")
    return log


def collect(P, dest, dry_run=False, manifest="always", only_new_in_log=False, say=print):
    """Copy the review-relevant Zotero PDFs to dest and rebuild the manifest; returns the log of this run."""
    by_d, by_t = review_status(P)
    today = datetime.date.today().isoformat()
    log = []
    have = {}                                                  # checksums already in the destination folder
    for f in dest.glob("*.pdf"):
        have.setdefault(sha256(f), f.name)
    zdir = getattr(cfg, "ZOTERO", None)
    if zdir and (zdir / "zotero.sqlite").exists():
        att = zotero_attachments(zdir)
        say(f"Zotero: {len(att)} PDF attachments in {zdir}")
        for r in att.itertuples():
            hit = by_d.get(r.d) if r.d else None
            hit = hit or (by_t.get(r.tn) if len(r.tn) > 25 else None)
            if not hit or hit[0] == "screened, not included":
                continue
            h = sha256(r.file)
            name = (re.sub(r"[^A-Za-z0-9._-]+", "_", r.d) if r.d else "title_" + re.sub(r"\s+", "_", r.tn)[:80]) + ".pdf"
            row = {"date": today, "doi": r.d, "title": hit[1], "status": hit[0], "zotero_key": r.att_key, "zotero_collections": r.collections,
                   "source_file": str(r.file), "sha256": h}
            if h in have:
                row.update(action="already in the folder (same content)", file=have[h])
            else:
                if (dest / name).exists():
                    name = name[:-4] + "__zotero-" + r.att_key + ".pdf"
                if not dry_run:
                    shutil.copy2(r.file, dest / name)
                have[h] = name
                row.update(action="copied" if not dry_run else "would be copied", file=name)
            log.append(row)
    else:
        say("Zotero: no data folder configured (ZOTERO_DIR in local_settings.py)")
    log += from_download_dirs(dest, by_d, by_t, have, today, dry_run, say)
    L = pd.DataFrame(log)
    if len(L):
        say(L["action"].value_counts().to_string()); say(L[L["action"].str.contains("copied")]["status"].value_counts().to_string())
    if dry_run:
        return L
    lp = dest / "collect_log.csv"
    if len(L):
        L = L[L["action"] == "copied"] if only_new_in_log else L
    if len(L):
        pd.concat([read_csv(lp), L] if lp.exists() else [L], ignore_index=True).to_csv(lp, index=False, encoding="utf-8-sig")

    if manifest == "if changed" and (dest / "fulltext_manifest.csv").exists() and not (len(L) and (L["action"] == "copied").any()):
        return L
    # ---- manifest of the folder
    dl = read_csv(dest / "download_log.csv") if (dest / "download_log.csv").exists() else pd.DataFrame(columns=["doi", "file", "status", "url"])
    dl = dl[dl["status"] == "saved"].drop_duplicates("file", keep="last").set_index("file")
    cl = read_csv(lp).drop_duplicates("file", keep="first").set_index("file") if lp.exists() else pd.DataFrame()
    old = read_csv(dest / "fulltext_manifest.csv").set_index("file") if (dest / "fulltext_manifest.csv").exists() else pd.DataFrame()
    from s04_fulltext import pdf_text
    rows = []
    for f in sorted(dest.glob("*.pdf")):
        if f.name in dl.index:
            d, origin = norm_doi(dl.at[f.name, "doi"]), "open-access download: " + str(dl.at[f.name, "url"])
        elif len(cl) and f.name in cl.index:
            d = norm_doi(cl.at[f.name, "doi"]) if isinstance(cl.at[f.name, "doi"], str) else ""
            zk = cl.at[f.name, "zotero_key"]
            origin = (f"Zotero attachment {zk} ({cl.at[f.name, 'source_file']})" if isinstance(zk, str) and zk
                      else f"saved by hand, copied from {cl.at[f.name, 'source_file']}")
        else:
            m = re.search(r"10\.\d{4,9}/[^\s\"<>]+", pdf_text(f, 1, 2)); d = norm_doi(m.group(0).rstrip(".,;)")) if m else ""
            origin = "placed in the folder by hand"
        st = by_d.get(d, ("not matched to a record of the review", ""))
        if st[0].startswith("not matched") and len(cl) and f.name in cl.index:
            st = (cl.at[f.name, "status"], cl.at[f.name, "title"])
        rows.append({"file": f.name, "doi": d, "title": st[1], "review_status": st[0], "origin": origin, "bytes": f.stat().st_size, "sha256": sha256(f),
                     "first_recorded": old.at[f.name, "first_recorded"] if len(old) and f.name in old.index else today})
    M = pd.DataFrame(rows)
    M.to_csv(dest / "fulltext_manifest.csv", index=False, encoding="utf-8-sig")
    say(f"\nManifest: {len(M)} PDFs in {dest}"); say(M["review_status"].str.replace(r":.*", "", regex=True).value_counts().to_string())

    return L


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--iteration"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    its = sorted(p for p in (cfg.REVIEW / "iterations").glob("*_v*") if p.is_dir())
    P = cfg.paths(a.iteration or max(its, key=lambda p: p.stat().st_mtime))
    dest = cfg.LIT / "Review_fulltexts"; dest.mkdir(parents=True, exist_ok=True)
    collect(P, dest, dry_run=a.dry_run)

if __name__ == "__main__":
    main()
