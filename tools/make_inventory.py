"""Write a dated inventory of every script in a repository.

    python tools/make_inventory.py                 # GBEM code repository -> docs/INVENTORY.md
    python tools/make_inventory.py --root <dir> --out <file>

For each .py / .R / .ipynb file: folder, purpose (first docstring or comment line), date of the last
commit that changed it, file modification date, and status (current, superseded, archived, snapshot).
"""
import argparse, ast, datetime, json, pathlib, re, subprocess

SUPERSEDED = {  # earlier review figure scripts, archived; their function is now provided by review/
    "scripts/visualization/archive/keywords_CA.py": "review/s02_bibliometrics.py (keyword blocks, Fig. 7)",
    "scripts/visualization/archive/prisma_CA.py": "review/s05_figures.py (PRISMA 2020 diagram)",
    "scripts/visualization/archive/CAP_prisma.py": "review/s05_figures.py (workflow figure)",
    "scripts/visualization/archive/CAP_prisma_animate.py": "review/s05_figures.py (workflow figure)",
}
SKIP_DIRS = {".git", "__pycache__", ".ipynb_checkpoints", "osm", "scraping", "uk-lidar-program", "data"}


def purpose(p):
    try:
        if p.suffix == ".ipynb":
            nb = json.loads(p.read_text(encoding="utf-8"))
            for c in nb.get("cells", []):
                src = "".join(c.get("source", [])).strip()
                if src:
                    return re.sub(r"^[#\s]+", "", src.splitlines()[0])[:110]
            return "Notebook"
        txt = p.read_text(encoding="utf-8", errors="ignore")
        if p.suffix == ".py":
            try:
                d = ast.get_docstring(ast.parse(txt))
                if d:
                    return d.strip().splitlines()[0][:110]
            except SyntaxError:
                pass
        for line in txt.splitlines()[:15]:
            s = line.strip()
            if s.startswith("#") and not s.startswith("#!") and "coding" not in s and len(s) > 3:
                return s.lstrip("# ").strip()[:110]
    except Exception:
        pass
    return "(no description in file header)"


def last_commit(root, rel):
    r = subprocess.run(["git", "log", "-1", "--format=%ad", "--date=short", "--", rel], cwd=root, capture_output=True, text=True)
    return r.stdout.strip() or "not committed"


def status(rel):
    if rel in SUPERSEDED:
        return "archived; superseded by " + SUPERSEDED[rel]
    if "/archive/" in f"/{rel}":
        return "archived"
    if rel.startswith("iterations/"):
        return "snapshot (iteration record)"
    return "current"


def main():
    ap = argparse.ArgumentParser()
    here = pathlib.Path(__file__).resolve().parents[1]
    ap.add_argument("--root", default=str(here)); ap.add_argument("--out", default=None)
    ap.add_argument("--title", default="Code inventory")
    a = ap.parse_args()
    root = pathlib.Path(a.root).resolve()
    out = pathlib.Path(a.out) if a.out else root / "docs" / "INVENTORY.md"
    tracked = set(subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True).stdout.split("\n"))
    rows = []
    for p in sorted(root.rglob("*")):
        if p.suffix not in (".py", ".R", ".ipynb") or any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        rel = p.relative_to(root).as_posix()
        if tracked and rel not in tracked:
            continue
        rows.append((str(pathlib.PurePosixPath(rel).parent), p.name, purpose(p), last_commit(root, rel),
                     datetime.date.fromtimestamp(p.stat().st_mtime).isoformat(), status(rel)))
    today = datetime.date.today().isoformat()
    md = [f"# {a.title}", "", f"Generated {today} by `tools/make_inventory.py`. Dates: last commit that changed the file, and file modification date.", ""]
    for folder in sorted({r[0] for r in rows}):
        md += [f"## `{folder}/`", "", "| File | Purpose | Last commit | Modified | Status |", "|---|---|---|---|---|"]
        md += [f"| `{f}` | {pu.replace('|', '/')} | {lc} | {mo} | {st} |" for fo, f, pu, lc, mo, st in rows if fo == folder]
        md.append("")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md), encoding="utf-8")
    print(f"{len(rows)} scripts -> {out}")


if __name__ == "__main__":
    main()
