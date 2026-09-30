"""Create the next time-stamped iteration, run the pipeline, build PDF and Word.

    python new_iteration.py --version 0.3 [--scopus ...] [--wos ...] [--skip-fulltext] [--no-build]

- Copies latex/ (sources, bibliography, tools) and analysis/inputs/ (human-edited CSVs) from the
  latest iteration, so reviewer decisions and extraction work carry forward.
- Runs run_all.py into the new folder.
- Compiles Review_v<version>.pdf (latexmk) and Review_v<version>.docx (tools/make_docx.py) into build/,
  and copies both to PDF/ and DOC/ with the time stamp.
"""
import argparse, datetime, pathlib, shutil, subprocess, sys
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
    a = ap.parse_args()
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
    args = ["--iteration", str(new)] + (["--scopus", *a.scopus] if a.scopus else []) + (["--wos", *a.wos] if a.wos else [])
    run_all.main(args + (["--skip-fulltext"] if a.skip_fulltext else []))
    if a.no_build:
        return
    job = f"Review_v{a.version}"
    subprocess.run(["latexmk", "-pdf", f"-jobname={job}", "-interaction=nonstopmode", "main.tex"], cwd=new / "latex")
    (new / "build").mkdir(exist_ok=True)
    pdf = new / "latex" / f"{job}.pdf"
    if pdf.exists():
        shutil.copy(pdf, new / "build" / pdf.name); shutil.copy(pdf, cfg.PHD / "PDF" / f"{stamp}_Review_Paper_v{a.version}.pdf")
    docx = new / "build" / f"{job}.docx"
    subprocess.run([sys.executable, str(new / "latex" / "tools" / "make_docx.py"), str(docx)])
    tmp = docx.with_suffix(".pandoc.tex")
    if tmp.exists():
        tmp.unlink()
    if docx.exists():
        shutil.copy(docx, cfg.PHD / "DOC" / f"{stamp}_Review_Paper_v{a.version}.docx")
    print("Iteration ready:", new)


if __name__ == "__main__":
    main()
