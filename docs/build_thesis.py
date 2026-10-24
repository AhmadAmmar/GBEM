"""Build the thesis: results tables, figures, PDF and Word versions from the same LaTeX source.

    python build_thesis.py [--no-docx] [--no-tables]

1. Results tables from the results files (thesis_tables.py) and figures from Outputs/publication/<figure>/<figure>.pdf
   into Manuscripts/02_Thesis/generated/.
2. PDF: pdflatex, BibTeX, makeglossaries, pdflatex twice, under the job name thesis_build (so that a PDF open in a
   viewer does not block the build). Undefined references and citations, and the open markers "[To confirm" and
   "[Results pending" in the source, are counted and reported.
3. Word: docs/thesis_docx.py converts the same LaTeX source through pandoc, with the numbering, cross-references and
   citations of the PDF and the Ulster page set-up in its reference document (adapted from the review manuscript's
   make_docx.py).
4. Every build is written to a new folder Manuscripts/02_Thesis/iterations/<YYYY-MM-DD_HHMM>/ (Thesis.pdf,
   Thesis.docx, build_report.txt); earlier builds are never replaced.
"""
import argparse, datetime, pathlib, re, shutil, subprocess, sys

CODE = pathlib.Path(__file__).resolve().parents[1]
PHD = CODE.parent
TH = PHD / "Manuscripts/02_Thesis"
LATEX, GEN = TH / "latex", TH / "generated"
FIGURES = ["fig_ceiling", "fig_random", "fig_scale"]
PY = sys.executable


def run(cmd, cwd, timeout=1800):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, errors="replace")
    return r.returncode, r.stdout + r.stderr


def pdf(report):
    job = "thesis_build"
    for step in (["pdflatex", "-interaction=nonstopmode", f"-jobname={job}", "main.tex"], ["bibtex", job],
                 ["makeglossaries", job], ["pdflatex", "-interaction=nonstopmode", f"-jobname={job}", "main.tex"],
                 ["pdflatex", "-interaction=nonstopmode", f"-jobname={job}", "main.tex"]):
        run(step, LATEX)
    log = (LATEX / f"{job}.log").read_text(encoding="utf-8", errors="replace")
    errors = sorted(set(re.findall(r"^! (.*)$", log, re.M)))
    undef = sorted(set(re.findall(r"(?:Reference|Citation) `([^']+)' on page \d+ undefined", log)))
    report += [f"PDF errors: {len(errors)}"] + [f"  {e}" for e in errors]
    report += [f"Undefined references or citations: {len(undef)}"] + [f"  {u}" for u in undef]
    pages = re.search(r"Output written on .*?\((\d+) pages", log)
    report.append(f"Pages: {pages.group(1) if pages else '?'}")
    return LATEX / f"{job}.pdf"


def docx(dest, report):
    """Word version through pandoc (docs/thesis_docx.py); needs no Word installation and never touches open documents"""
    code, out = run([PY, str(CODE / "docs/thesis_docx.py"), str(dest)], CODE, timeout=900)
    extra = [l for l in out.splitlines() if "references without a target" in l or "WARNING" in l]
    report.append("DOCX: ok" if dest.exists() and code == 0 else f"DOCX: failed ({out.strip()[-300:]})")
    report += [f"  {l}" for l in extra]
    for f in [dest.with_suffix(".pandoc.tex"), dest.with_name("reference_ulster.docx")] + list(dest.parent.glob("_*.bib")):
        if f.exists():
            f.unlink()                                            # intermediate files of this build
    return dest.exists()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-docx", action="store_true"); ap.add_argument("--no-tables", action="store_true")
    a = ap.parse_args()
    report = [f"Thesis build {datetime.datetime.now():%Y-%m-%d %H:%M}"]
    if not a.no_tables:
        code, out = run([PY, str(CODE / "docs/thesis_tables.py")], CODE)
        report.append(next((l for l in reversed(out.splitlines()) if "tables ->" in l), f"tables: exit {code}"))
    (GEN / "figures").mkdir(parents=True, exist_ok=True)
    for f in FIGURES:
        for ext in ("pdf", "png"):                                  # PDF for the PDF build, PNG for Word
            src = PHD / "Outputs/publication" / f / f"{f}.{ext}"
            if src.exists():
                shutil.copy2(src, GEN / "figures" / src.name)
    src_text = "\n".join(p.read_text(encoding="utf-8") for p in (LATEX / "chapters").glob("*.tex"))
    report.append(f"Open markers: {src_text.count('[To confirm') + src_text.count('[to confirm')} to confirm, "
                  f"{src_text.count('[Results pending')} results pending")
    out_dir = TH / "iterations" / f"{datetime.datetime.now():%Y-%m-%d_%H%M}"
    out_dir.mkdir(parents=True, exist_ok=False)
    p = pdf(report)
    if p.exists():
        shutil.copy2(p, out_dir / "Thesis.pdf")
    if not a.no_docx:
        docx(out_dir / "Thesis.docx", report)
    (out_dir / "build_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report)); print(f"-> {out_dir}")


if __name__ == "__main__":
    main()
