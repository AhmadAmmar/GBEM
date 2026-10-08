"""Create the next time-stamped iteration, run the pipeline, build PDF and Word.

    python new_iteration.py --version 0.3 [--scopus ...] [--wos ...] [--skip-fulltext] [--no-build]
    python new_iteration.py --version 0.3 --rebuild <iteration folder> [--rerun]   # after editing its text

- Copies latex/ (sources, bibliography, tools) and analysis/inputs/ (human-edited CSVs) from the
  latest iteration, so reviewer decisions and extraction work carry forward.
- Runs run_all.py into the new folder.
- Compiles Review_v<version>.pdf (latexmk) and Review_v<version>.docx (tools/make_docx.py) into build/,
  and copies both to PDF/ and DOC/ with the time stamp.
- --rebuild compiles an existing iteration again (optionally re-running the analysis first with --rerun)
  and overwrites only that iteration's own build files and time-stamped copies.
"""
import argparse, datetime, pathlib, re, shutil, subprocess, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import config as cfg, run_all

SKIP = {".aux", ".log", ".bbl", ".blg", ".fls", ".fdb_latexmk", ".out", ".synctex.gz", ".spl", ".pdf"}


def latest_iteration():
    its = sorted(p for p in (cfg.REVIEW / "iterations").glob("*_v*") if p.is_dir())
    return its[-1] if its else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--scopus", nargs="*"); ap.add_argument("--wos", nargs="*")
    ap.add_argument("--skip-fulltext", action="store_true"); ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--rebuild", help="existing iteration folder to compile again"); ap.add_argument("--rerun", action="store_true")
    a = ap.parse_args()
    if a.rebuild:
        it = pathlib.Path(a.rebuild).resolve()
        if a.rerun:
            run_all.main(["--iteration", str(it)] + (["--skip-fulltext"] if a.skip_fulltext else []))
        build(it, a.version, it.name.rsplit("_v", 1)[0])
        return
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    new = cfg.REVIEW / "iterations" / f"{stamp}_v{a.version}"
    prev = latest_iteration()
    src_latex = (prev / "latex") if prev else (cfg.REVIEW / "latex")
    shutil.copytree(src_latex, new / "latex", ignore=lambda d, fs: [f for f in fs if pathlib.Path(f).suffix in SKIP or f.endswith(".synctex.gz")])
    # first pipeline-driven iteration: overlay the macro-based manuscript template
    if "generated/numbers" not in (new / "latex" / "main.tex").read_text(encoding="utf-8"):
        tpl = cfg.TEMPLATE / "latex"
        shutil.copy(tpl / "main.tex", new / "latex" / "main.tex")
        for f in (tpl / "sections").glob("*.tex"):
            shutil.copy(f, new / "latex" / "sections" / f.name)
        shutil.copy(tpl / "tools" / "make_docx.py", new / "latex" / "tools" / "make_docx.py")
    if prev and (prev / "analysis" / "inputs").exists():
        shutil.copytree(prev / "analysis" / "inputs", new / "analysis" / "inputs")
        # the second reviewer's sample is redrawn for the new record set unless decisions have been entered
        samp = new / "analysis" / "inputs" / cfg.HUMAN["second_screener"]
        if samp.exists():
            import pandas as pd
            d = pd.read_csv(samp, dtype=str, encoding="utf-8-sig")
            if d.get("decision_reviewer2", pd.Series(dtype=str)).fillna("").str.strip().eq("").all():
                samp.unlink()
    args = ["--iteration", str(new)] + (["--scopus", *a.scopus] if a.scopus else []) + (["--wos", *a.wos] if a.wos else [])
    run_all.main(args + (["--skip-fulltext"] if a.skip_fulltext else []))
    if a.no_build:
        return
    build(new, a.version, stamp)


def build(new, version, stamp):
    job = f"Review_v{version}"
    subprocess.run(["latexmk", "-pdf", f"-jobname={job}", "-interaction=nonstopmode", "main.tex"], cwd=new / "latex")
    (new / "build").mkdir(exist_ok=True)
    pdf = new / "latex" / f"{job}.pdf"
    # a PDF is only accepted if LaTeX reported no errors and no undefined citations or references
    log = (new / "latex" / f"{job}.log")
    logt = log.read_text(encoding="utf-8", errors="ignore") if log.exists() else "! no log file"
    n_err, n_undef = len(re.findall(r"^!", logt, flags=re.M)), len(re.findall(r"Warning: (?:Citation|Reference) .* undefined", logt))
    if n_err or n_undef:
        print(f"BUILD NOT ACCEPTED: {n_err} LaTeX errors, {n_undef} undefined citations/references. See {log}")
        print("Fix the source (often a character in references.bib), then run again with --rebuild.")
        return
    if pdf.exists():
        shutil.copy(pdf, new / "build" / pdf.name); shutil.copy(pdf, cfg.PHD / "PDF" / f"{stamp}_Review_Paper_v{version}.pdf")
        # companion contents document (table of contents, lists of figures and tables), if the template provides it
        mc = new / "latex" / "tools" / "make_contents.py"
        if mc.exists():
            subprocess.run([sys.executable, str(mc), version], cwd=new / "latex")
            toc = new / "build" / f"{job}_Contents.pdf"
            if toc.exists():
                shutil.copy(toc, cfg.PHD / "PDF" / f"{stamp}_Review_Paper_v{version}_Contents.pdf")
    docx = new / "build" / f"{job}.docx"
    subprocess.run([sys.executable, str(new / "latex" / "tools" / "make_docx.py"), str(docx)])
    tmp = docx.with_suffix(".pandoc.tex")
    if tmp.exists():
        tmp.unlink()
    if docx.exists():
        shutil.copy(docx, cfg.PHD / "DOC" / f"{stamp}_Review_Paper_v{version}.docx")
        # every table as printed: one CSV per table, a workbook and a PDF, if the template provides the tool
        mt = new / "latex" / "tools" / "make_tables.py"
        if mt.exists():
            subprocess.run([sys.executable, str(mt), version], cwd=new / "latex")
            for src, dst in ((new / "build" / f"{job}_Tables.xlsx", cfg.PHD / "DOC" / f"{stamp}_Review_Paper_v{version}_Tables.xlsx"),
                             (new / "build" / f"{job}_Tables.pdf", cfg.PHD / "PDF" / f"{stamp}_Review_Paper_v{version}_Tables.pdf")):
                if src.exists():
                    shutil.copy(src, dst)
    # version the iteration in the (internal) manuscript repository, if there is one
    if (cfg.REVIEW / ".git").exists():
        git = lambda *a: subprocess.run(["git", *a], cwd=cfg.REVIEW, capture_output=True, text=True)
        git("add", "-A")
        if git("diff", "--cached", "--quiet").returncode:
            git("commit", "-m", f"Iteration v{version} ({stamp})")
            git("tag", "-a", f"v{version}-draft", "-m", f"Draft v{version} ({cfg.SEARCH['search_date']} search)")
            print("Committed and tagged in the manuscript repository:", f"v{version}-draft")
    print("Iteration ready:", new)


if __name__ == "__main__":
    main()
