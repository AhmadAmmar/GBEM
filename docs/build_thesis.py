"""Build the thesis: results tables, figures, PDF and Word versions from the same LaTeX source.

    python build_thesis.py [--no-docx] [--no-tables]

1. Results tables from the results files (thesis_tables.py) and figures from Outputs/publication/<figure>/<figure>.pdf
   into Manuscripts/02_Thesis/generated/.
2. PDF: pdflatex, BibTeX, makeglossaries, pdflatex twice, under the job name thesis_build (so that a PDF open in a
   viewer does not block the build). Undefined references and citations, and the open markers "[To confirm" and
   "[Results pending" in the source, are counted and reported.
3. Word: make4ht converts the same LaTeX run to OpenDocument (numbering, cross-references and citations as in the
   PDF, internal links kept); Microsoft Word then applies the Ulster page set-up (A4, binding margin 40 mm, others
   25 mm, Arial 12 pt, 1.5 line spacing) and saves .docx. Word is driven only when it is not already open, so that
   documents being edited are never touched; otherwise the .odt is kept and the step is reported as skipped.
4. Every build is written to a new folder Manuscripts/02_Thesis/iterations/<YYYY-MM-DD_HHMM>/ (Thesis.pdf,
   Thesis.docx or Thesis.odt, build_report.txt); earlier builds are never replaced.
"""
import argparse, datetime, pathlib, re, shutil, subprocess, sys, tempfile

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


def odt(report):
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="thesis_odt_"))
    shutil.copytree(LATEX, tmp / "latex", ignore=shutil.ignore_patterns("*.pdf", "thesis_build.*", "_archive"))
    shutil.copytree(GEN, tmp / "generated", ignore=shutil.ignore_patterns("_archive", "*.xlsx"))
    for ext in ("bbl", "acr", "acn", "glo", "ist"):              # bibliography and glossary from the PDF run
        src = LATEX / f"thesis_build.{ext}"
        if src.exists():
            shutil.copy(src, tmp / "latex" / f"main.{ext}")
    code, out = run(["make4ht", "-u", "-f", "odt", "main.tex", "mathml", "", "", "-interaction=nonstopmode"],
                    tmp / "latex", timeout=1800)
    f = tmp / "latex" / "main.odt"
    report.append(f"ODT: {'ok' if f.exists() else 'failed (exit ' + str(code) + ')'}")
    if not f.exists():
        (tmp / "make4ht.log").write_text(out, encoding="utf-8")
        report.append(f"  log: {tmp / 'make4ht.log'}")
    return f if f.exists() else None


WORD_PS = r"""
$ErrorActionPreference = 'Stop'
if (Get-Process WINWORD -ErrorAction SilentlyContinue) { Write-Output 'WORD_OPEN'; exit 0 }
$w = New-Object -ComObject Word.Application
try {
  $w.Visible = $false; $w.DisplayAlerts = 0
  $d = $w.Documents.Open('{src}', $false, $false)
  $mm = 2.8346456693
  foreach ($s in $d.Sections) { $p = $s.PageSetup; $p.PaperSize = 7; $p.LeftMargin = 40 * $mm; $p.RightMargin = 25 * $mm
    $p.TopMargin = 25 * $mm; $p.BottomMargin = 25 * $mm }
  foreach ($name in @(-1, -2, -3, -4, -5)) {
    $st = $d.Styles.Item($name); $st.Font.Name = 'Arial'
    if ($name -eq -1) { $st.Font.Size = 12; $st.ParagraphFormat.LineSpacingRule = 1; $st.ParagraphFormat.SpaceAfter = 6 } }
  $d.Content.Font.Name = 'Arial'
  $d.Fields.Update() | Out-Null
  $d.SaveAs2('{dst}', 16); $d.Close($false); Write-Output 'DOCX_OK'
} finally { $w.Quit() }
"""


def docx(odt_file, dest, report):
    ps = WORD_PS.replace("{src}", str(odt_file)).replace("{dst}", str(dest))
    script = pathlib.Path(tempfile.mkdtemp()) / "to_docx.ps1"
    script.write_text(ps, encoding="utf-8")
    code, out = run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], PHD, timeout=900)
    if "WORD_OPEN" in out:
        report.append("DOCX: skipped (Word is open; the .odt is kept - close Word and run again, or open the .odt in Word)")
        return False
    report.append("DOCX: ok" if "DOCX_OK" in out and dest.exists() else f"DOCX: failed ({out.strip()[-300:]})")
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
        src = PHD / "Outputs/publication" / f / f"{f}.pdf"
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
        o = odt(report)
        if o:
            shutil.copy2(o, out_dir / "Thesis.odt")
            if docx(out_dir / "Thesis.odt", out_dir / "Thesis.docx", report):
                (out_dir / "Thesis.odt").unlink()                 # the .docx replaces the intermediate file
    (out_dir / "build_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report)); print(f"-> {out_dir}")


if __name__ == "__main__":
    main()
