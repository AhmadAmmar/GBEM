"""Stage 4 - full-text support for extraction.

1. Indexes every PDF under Lit/ by DOI (first pages via pdftotext; cached).
2. For focused candidates, finds the local PDF and extracts:
   - the Conclusions section (first 2,500 characters),
   - sentences mentioning validation designs, metrics, linkage, time gaps, uncertainty, code/data availability.
3. Lists focused studies with no local PDF (to retrieve).

These snippets speed up filling inputs/focused_extraction.csv; they are not used as data directly.
Output: outputs/pdf_doi_index.csv, outputs/fulltext_snippets.csv, outputs/fulltext_missing.csv
Feeds : Appendix D (appraisal), Tables 8-9 (via the reviewed extraction sheet).
"""
import re, subprocess, shutil
import pandas as pd
from common import norm_doi, norm_title, read_csv

PATTERNS = {
    "validation": r"cross-validation|k-fold|test set|train(ing)?[ /-]test|held[- ]out|hold[- ]out|unseen|generali[sz]|transfer|leave-one|spatial(ly)? (block|split|cross)",
    "metric": r"macro[- ]?f1|f1[- ]score|accuracy|kappa|within[- ]one|\bR2\b|R²|\bMAE\b|RMSE|AUC|balanced accuracy",
    "linkage": r"UPRN|address match|geocod|spatial join|footprint",
    "time_gap": r"lodg|inspection date|acquisition date|captured (in|between|on)|temporal (gap|mismatch)|image (date|year)",
    "uncertainty": r"uncertaint|calibrat|confidence interval|prediction interval|conformal",
    "open": r"github\.com|zenodo|figshare|data availability|code availability|publicly available",
}


def pdf_text(pdf, first=None, last=None):
    exe = shutil.which("pdftotext")
    if not exe:
        return ""
    cmd = [exe, "-q", "-enc", "UTF-8"] + (["-f", str(first), "-l", str(last)] if first else []) + [str(pdf), "-"]
    try:
        return subprocess.run(cmd, capture_output=True, timeout=120).stdout.decode("utf-8", "ignore")
    except Exception:
        return ""


def build_index(cfg, P):
    idx_path = P["out"] / "pdf_doi_index.csv"
    old = read_csv(idx_path) if idx_path.exists() else pd.DataFrame(columns=["pdf", "doi_n", "title_guess", "mtime"])
    seen = dict(zip(old["pdf"], old["mtime"]))
    rows = old.to_dict("records")
    for pdf in cfg.LIT.rglob("*.pdf"):
        m = pdf.stat().st_mtime
        if seen.get(str(pdf)) == m:
            continue
        t = pdf_text(pdf, 1, 2)
        d = re.search(r"10\.\d{4,9}/[^\s\"<>]+", t)
        rows = [r for r in rows if r["pdf"] != str(pdf)]
        rows.append({"pdf": str(pdf), "doi_n": norm_doi(d.group(0).rstrip(".,;)")) if d else "",
                     "title_guess": re.sub(r"\s+", " ", t[:200]), "head_n": norm_title(t[:4000]), "mtime": m})
    idx = pd.DataFrame(rows)
    idx.to_csv(idx_path, index=False, encoding="utf-8-sig")
    return idx


def conclusions(text):
    """Text of the last Conclusions-type heading up to the back matter."""
    heads = list(re.finditer(r"(?:^|\n)\s*(?:\d+\.?\s*)?(?:Conclusions?|Concluding remarks|Summary and conclusions?|Discussion and conclusions?)\b[^\n]{0,40}\n",
                             text, re.I))
    if not heads:
        return ""
    body = text[heads[-1].end():]
    end = re.search(r"\n\s*(References|Bibliography|Acknowledg|CRediT|Declaration of|Data availability|Appendix|Funding)\b", body, re.I)
    return re.sub(r"\s+", " ", body[:end.start()] if end else body)[:2500]


def run(cfg, P):
    idx = build_index(cfg, P)
    sheet = read_csv(P["inputs"] / cfg.HUMAN["focused_extraction"])
    sheet = sheet[sheet["include_focused"].astype(str).str.upper().isin(["Y", "?"])]
    by_doi = idx[idx["doi_n"].ne("")].drop_duplicates("doi_n").set_index("doi_n")["pdf"]
    snips, missing = [], []
    for _, r in sheet.iterrows():
        d = norm_doi(r["doi"])
        pdf = by_doi.get(d)
        if pdf is None:   # fall back to the title (DOI missing or truncated on page 1, preprints)
            tn = norm_title(r.get("title") or r.get("notes") or "")[:70]
            if len(tn) > 25:
                hit = idx[idx["head_n"].fillna("").str.contains(re.escape(tn), regex=True)]
                pdf = hit["pdf"].iloc[0] if len(hit) else None
        if pdf is None:
            missing.append({"doi": r["doi"], "study": r["study"], "year": r["year"]})
            continue
        t = pdf_text(pdf)
        flat = re.sub(r"\s+", " ", t)
        row = {"doi": r["doi"], "study": r["study"], "pdf": pdf, "conclusions": conclusions(t)}
        for k, p in PATTERNS.items():
            hits = [m.group(0) for m in re.finditer(r"[^.]{0,200}(?:" + p + r")[^.]{0,200}\.", flat, re.I)]
            row[k] = " || ".join(h.strip() for h in hits[:6])
        snips.append(row)
    pd.DataFrame(snips).to_csv(P["out"] / "fulltext_snippets.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(missing).to_csv(P["out"] / "fulltext_missing.csv", index=False, encoding="utf-8-sig")
    return {"n_pdfs_indexed": int(len(idx)), "n_with_fulltext": len(snips), "n_missing": len(missing)}
