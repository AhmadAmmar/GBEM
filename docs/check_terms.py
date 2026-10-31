"""Check that every abbreviation is spelled out where a reader first meets it, in the thesis (chapter order) and in
other manuscripts.

    python check_terms.py [--tex <main.tex> ...] [--window 250]

For each \\newacronym{key}{SHORT}{Long form} in the thesis abbreviations, the first use of SHORT in the main text (in
the order the chapters are input) is located; it counts as defined if the long form occurs within the window of
characters before or after it. The abstract is checked on its own (it must stand alone). Prints the abbreviations used
before being defined, and those defined but never used.
"""
import argparse, pathlib, re

PHD = pathlib.Path(__file__).resolve().parents[2]
THESIS = PHD / "Manuscripts/02_Thesis/latex"


def flatten(tex_path, seen=None):
    """main text in input order (chapters and generated tables), without comments"""
    seen = seen or set()
    base = tex_path.parent
    text = re.sub(r"(?<!\\)%.*", "", tex_path.read_text(encoding="utf-8"))

    def inc(m):
        name = m.group(1)
        for c in (base / name, base / (name + ".tex")):
            if c.is_file() and c not in seen:
                seen.add(c)
                return flatten(c, seen)
        return ""
    return re.sub(r"\\(?:input|include|InputIfFileExists)\{([^}]+)\}(?:\{[^}]*\}\{[^}]*\})?", inc, text)


def acronyms():
    t = (THESIS / "chapters/00_abbreviations.tex").read_text(encoding="utf-8")
    return re.findall(r"\\newacronym(?:\[[^\]]*\])?\{([^}]*)\}\{(.*?)\}\{(.*?)\}\s*$", t, re.M)


def plain(s):
    s = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", s)
    return re.sub(r"[{}$\\]", "", s).lower()


def check(text, label, acr, window):
    out = []
    for key, short, long in acr:
        s = re.sub(r"[{}$\\]", "", short)
        if not s or len(s) < 2:
            continue
        m = re.search(r"(?<![A-Za-z])" + re.escape(short if "\\" in short else s) + r"(?![A-Za-z])", text)
        if not m:
            continue
        around = plain(text[max(0, m.start() - window): m.end() + window])
        if plain(long).strip() not in around:
            line = text[:m.start()].count("\n") + 1
            out.append((label, s, long, text[max(0, m.start() - 70): m.end() + 70].replace("\n", " ")))
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--tex", nargs="*", default=[]); ap.add_argument("--window", type=int, default=250)
    a = ap.parse_args()
    acr = acronyms()
    main_tex = (THESIS / "main.tex").read_text(encoding="utf-8")
    body = flatten(THESIS / "main.tex")
    abstract = (THESIS / "chapters/00_abstract.tex").read_text(encoding="utf-8")
    start = body.find(r"\pagenumbering{arabic}")
    issues = check(re.sub(r"(?<!\\)%.*", "", abstract), "thesis abstract", acr, a.window) + check(body[start:], "thesis main text", acr, a.window)
    for extra in a.tex:
        p = pathlib.Path(extra)
        issues += check(flatten(p), p.parent.name, acr, a.window)
    for label, s, long, ctx in issues:
        print(f"[{label}] {s} ({long}) first used without its long form:\n    ...{ctx}...")
    used = {s for _, s, _ in acr if re.search(r"(?<![A-Za-z])" + re.escape(re.sub(r'[{}$\\]', '', s)) + r"(?![A-Za-z])", body[start:])}
    print("\ndefined but not used in the main text:", sorted({re.sub(r'[{}$\\]', '', s) for _, s, _ in acr} - used))
    print(f"{len(issues)} abbreviations first used without their long form")


if __name__ == "__main__":
    main()
