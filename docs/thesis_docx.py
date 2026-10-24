"""Word version of the thesis from the same LaTeX source, through pandoc (adapted from the review manuscript's
tools/make_docx.py, which does the same for the review paper).

    python thesis_docx.py <out.docx>

pandoc 2.x reads LaTeX but does not number chapters, sections, tables or figures, resolve \\cref, read natbib-only
constructs, glossaries or longtable/tabularx reliably. The script therefore flattens main.tex and its inputs into a
pandoc-friendly file first:
  - \\input of chapters and generated tables is inlined; result macros (generated/numbers.tex) become their values;
  - headings get the numbers they have in the PDF (Chapter 5, 5.2, 5.2.1; Appendix A, A.1), tables and figures their
    chapter-based numbers (Table 5.2, Figure 5.1), and every \\ref / \\cref becomes a link to its target's bookmark
    with the same text as in the PDF;
  - longtable, tabularx, adjustbox and \\multicolumn are rewritten as plain tabular; layout-only commands are dropped;
  - the title page, abstract, abbreviations (from chapters/00_abbreviations.tex), acknowledgements and the declaration
    on generative AI are written as front matter;
  - citations are rendered by pandoc citeproc from the same BibTeX files, author-date (Harvard).
A reference document carries the Ulster page set-up (A4; binding margin 40 mm, others 25 mm; Arial 12 pt; 1.5 line
spacing; space after paragraphs; page numbers top right); it is built from pandoc's default by editing its XML, so
Microsoft Word is not needed.
"""
import io, pathlib, re, subprocess, sys, zipfile

CODE = pathlib.Path(__file__).resolve().parents[1]
TH = CODE.parent / "Manuscripts/02_Thesis"
LATEX, GEN = TH / "latex", TH / "generated"
PANDOC = r"C:\Users\Owner\anaconda3\envs\eo\Scripts\pandoc.exe"
CSL = LATEX / "ulster-harvard-lhs.csl"                      # (Author Year): Ulster Library Harvard LHS


def read(path):
    p = (LATEX / path) if not pathlib.Path(path).is_absolute() else pathlib.Path(path)
    for cand in (p, p.with_suffix(".tex")):
        if cand.exists() and cand.is_file():
            return cand.read_text(encoding="utf-8")
    return ""


def inline(text):
    text = re.sub(r"(?<!\\)%.*", "", text)                                   # comments
    for _ in range(3):
        text = re.sub(r"\\InputIfFileExists\{([^}]+)\}\{[^}]*\}\{[^}]*\}", lambda m: read(m.group(1)), text)
        text = re.sub(r"\\input\{([^}]+)\}", lambda m: re.sub(r"(?<!\\)%.*", "", read(m.group(1))), text)
    return text


def group(s, i):
    """the {...} argument starting at s[i] (after spaces): (content, end index)"""
    while i < len(s) and s[i].isspace():
        i += 1
    if i >= len(s) or s[i] != "{":
        return None, i
    depth, j = 1, i + 1
    while j < len(s) and depth:
        if s[j] == "\\":
            j += 2; continue
        depth += {"{": 1, "}": -1}.get(s[j], 0); j += 1
    return s[i + 1:j - 1], j


def bm(key):                                                                  # Word bookmark names
    s = re.sub(r"[^A-Za-z0-9]", "_", key.strip())
    return ("x" + s if not s[:1].isalpha() else s)[:40]


def main():
    out = pathlib.Path(sys.argv[1])
    main_tex = (LATEX / "main.tex").read_text(encoding="utf-8")
    body = main_tex.split(r"\begin{document}", 1)[1].split(r"\end{document}", 1)[0]
    body = inline(body)

    # front matter: title page, abstract, lists -> plain sections; contents/lists are left to Word
    body = re.sub(r"\\begin\{titlepage\}.*?\\end\{titlepage\}", "", body, flags=re.S)
    for cmd in (r"\tableofcontents", r"\listoffigures", r"\listoftables", r"\clearpage", r"\FloatBarrier", r"\centering",
                r"\appendix", r"\glsaddall", r"\onehalfspacing"):
        body = body.replace(cmd, "\n" if cmd == r"\appendix" else "")
    body = re.sub(r"\\pagenumbering\{[^}]*\}|\\addcontentsline\{[^}]*\}\{[^}]*\}\{[^}]*\}|\\vspace\*?\{[^}]*\}|\\vfill", "", body)
    abbr = read("chapters/00_abbreviations")
    acr = re.findall(r"\\newacronym\{[^}]*\}\{(.*?)\}\{(.*?)\}\s*$", abbr, re.M)
    rows = "\n".join(f"{s} & {l} \\\\" for s, l in acr)
    body = body.replace(r"\printglossary[type=\acronymtype,title=Abbreviations]",
                        "\\chapter*{Abbreviations}\n\\begin{tabular}{ll}\n" + rows + "\n\\end{tabular}\n")

    # tables: longtable / tabularx / adjustbox -> table + tabular; \multicolumn -> text and empty cells
    def lt_fix(m):
        spec, b = m.group(1), m.group(2)
        cap = re.search(r"\\caption\{(.*?)\}\\label\{([^}]*)\}", b, re.S)
        head = b.split(r"\endfirsthead", 1)[0]
        head = head[head.index(r"\toprule"):] if r"\toprule" in head else ""
        b = b.split(r"\endhead", 1)[1] if r"\endhead" in b else b
        cap_txt = (r"\caption{" + cap.group(1) + r"}\label{" + cap.group(2) + "}\n") if cap else ""
        return r"\begin{table}" + "\n" + cap_txt + r"\begin{tabular}{" + spec + "}\n" + head + b + r"\end{tabular}" + "\n" + r"\end{table}"
    body = re.sub(r"\\begin\{longtable\}\{((?:[^{}]|\{[^{}]*\})*)\}(.*?)\\end\{longtable\}", lt_fix, body, flags=re.S)
    body = re.sub(r"\\begin\{adjustbox\}\{[^}]*\}|\\end\{adjustbox\}", "", body)
    body = re.sub(r"\\multicolumn\{(\d+)\}\{(?:[^{}]|\{[^{}]*\})*\}\{((?:[^{}]|\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})*)\}",
                  lambda m: m.group(2) + " &" * (int(m.group(1)) - 1), body)

    def to_tabular(m):
        spec = re.sub(r"@\{(?:[^{}]|\{[^{}]*\})*\}", "", m.group(1))
        spec = re.sub(r"[pmP]\{[^}]*\}", "l", spec)
        spec = re.sub(r">\{[^}]*\}", "", spec)
        return r"\begin{tabular}{%s}" % "".join("l" if c in "lXYp" else c for c in spec if c in "lcrXYp")
    body = re.sub(r"\\begin\{tabularx\}\{[^}]*\}\{((?:[^{}]|\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})*)\}", to_tabular, body)
    body = body.replace(r"\end{tabularx}", r"\end{tabular}")
    body = re.sub(r"\\begin\{tabular\}\{((?:[^{}]|\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})*)\}", to_tabular, body)
    body = re.sub(r"\\par\\smallskip\\parbox\{[^}]*\}\{\\footnotesize (.*?)\}\n", r"\n\\emph{Note.} \1\n", body)
    body = re.sub(r"\\(small|footnotesize|scriptsize|normalsize)\b", "", body)
    body = re.sub(r"\\fbox\{\\parbox\{[^}]*\}\{(.*?)\}\}", r"\1", body, flags=re.S)
    body = body.replace(r"\crefalias{chapter}{appendix}", "")
    # figures: the PNG version beside each PDF figure (Word does not embed PDF)
    body = re.sub(r"\\includegraphics(\[[^\]]*\])?\{([^}.]+)\}", lambda m: r"\includegraphics[width=15cm]{" + m.group(2) + ".png}", body)

    # labels -> Word-safe bookmark names, in labels and references alike
    body = re.sub(r"\\label\{([^}]+)\}", lambda m: "\\label{" + bm(m.group(1)) + "}", body)
    body = re.sub(r"\\([cC]?ref)\{([^}]+)\}", lambda m: "\\" + m.group(1) + "{" + ",".join(bm(k) for k in m.group(2).split(",")) + "}", body)

    # headings: chapter / section numbers as in the PDF; floats numbered within chapters
    names, ctr = {}, {"chapter": 0, "app": 0, "section": 0, "subsection": 0, "table": 0, "figure": 0}
    in_app = [False]
    app_start = body.find("Data sources}")                                     # first appendix chapter
    pieces, pos = [], 0
    pat = re.compile(r"\\(chapter|section|subsection|subsubsection)(\*?)\{([^}]*)\}(\\label\{([^}]+)\})?|\\begin\{(table|figure)\}(.*?)\\end\{\6\}", re.S)
    for m in pat.finditer(body):
        pieces.append(body[pos:m.start()]); pos = m.end()
        if m.group(6):                                                        # float
            kind, content = m.group(6), m.group(7)
            if r"\caption" not in content:
                pieces.append(m.group(0)); continue
            ctr[kind] += 1
            chap = chr(64 + ctr["app"]) if in_app[0] else str(ctr["chapter"])
            name = f"{'Table' if kind == 'table' else 'Figure'} {chap}.{ctr[kind]}"
            lab = re.search(r"\\label\{([^}]+)\}", content)
            if lab:
                names[lab.group(1)] = name
            content = content.replace(r"\caption{", r"\caption{" + name + ". ", 1)
            pieces.append(r"\begin{%s}%s\end{%s}" % (kind, content, kind)); continue
        kind, star, title, lab = m.group(1), m.group(2), m.group(3), m.group(5)
        if star:
            pieces.append(m.group(0)); continue
        if kind == "chapter":
            if app_start != -1 and m.start() >= app_start - 20:
                in_app[0] = True
            if in_app[0]:
                ctr["app"] += 1; num = chr(64 + ctr["app"]); shown = f"Appendix {num}. {title}"; name = f"Appendix {num}"
            else:
                ctr["chapter"] += 1; num = str(ctr["chapter"]); shown = f"Chapter {num}. {title}"; name = f"Chapter {num}"
            ctr.update(section=0, subsection=0, table=0, figure=0)
            out_head = f"\\section*{{{shown}}}"
        elif kind == "section":
            ctr["section"] += 1; ctr["subsection"] = 0
            top = chr(64 + ctr["app"]) if in_app[0] else str(ctr["chapter"])
            num = f"{top}.{ctr['section']}"; name = f"Section {num}"; out_head = f"\\subsection*{{{num} {title}}}"
        elif kind == "subsection":
            ctr["subsection"] += 1
            top = chr(64 + ctr["app"]) if in_app[0] else str(ctr["chapter"])
            num = f"{top}.{ctr['section']}.{ctr['subsection']}"; name = f"Section {num}"; out_head = f"\\subsubsection*{{{num} {title}}}"
        else:
            name, out_head = title, f"\\paragraph{{{title}}}"
        if lab:
            names[lab] = name
        pieces.append(out_head + (f"\\label{{{lab}}}" if lab else ""))
    pieces.append(body[pos:]); body = "".join(pieces)
    body = body.replace(r"\chapter*{", r"\section*{")

    def resolve(m):
        keys = [k.strip() for k in m.group(2).split(",")]
        parts = [r"\hyperref[%s]{%s}" % (k, names.get(k, k)) for k in keys]
        txt = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
        return txt[0].upper() + txt[1:] if m.group(1) == "Cref" and txt[:1].islower() else txt
    body = re.sub(r"\\([cC]?ref)\{([^}]+)\}", resolve, body)

    # result macros -> values (numbers.tex: \newcommand{\Name}{value})
    vals = dict(re.findall(r"\\newcommand\{\\([A-Za-z]+)\}\{(.*?)\}\s*$", (GEN / "numbers.tex").read_text(encoding="utf-8"), re.M)) \
        if (GEN / "numbers.tex").exists() else {}
    vals["SubmissionMonthYear"] = re.search(r"SubmissionMonthYear\}\{([^}]*)\}", abbr).group(1) if "SubmissionMonthYear" in abbr else ""
    for k in sorted(vals, key=len, reverse=True):
        body = re.sub(r"\\" + k + r"(\{\})?(?![A-Za-z])", lambda m, v=vals[k]: v, body)
    body = re.sub(r"\\bibliographystyle\{[^}]*\}\s*\\bibliography\{[^}]*\}", r"\\section*{References}\n\\hypertarget{refs}{}\n", body)

    title = re.search(r"\{\\Large\\bfseries (.*?)\\par\}", main_tex, re.S).group(1).replace("\\\\", " ").strip()
    author = re.search(r"\{\\large (.*?)\\par\}", main_tex).group(1)
    statement = re.search(r"\\vfill\s*(I confirm.*?)\\par", main_tex, re.S).group(1).replace("\n", " ")
    front = (f"{author}\n\nFaculty of Life and Health Sciences of Ulster University\n\n"
             f"Thesis submitted for the degree of Doctor of Philosophy\n\n{vals['SubmissionMonthYear']}\n\n{statement}\n\n")
    tex = "\\documentclass{article}\n\\begin{document}\n" + front + body + "\n\\end{document}\n"
    tmp = out.with_suffix(".pandoc.tex"); tmp.write_text(tex, encoding="utf-8")

    # pandoc turns BibTeX titles into sentence case ("england and wales"); titles in double braces keep their case
    bibs = []
    for b in re.search(r"\\bibliography\{([^}]*)\}", main_tex).group(1).split(","):
        src = LATEX / (b.strip() + ".bib")
        if src.exists():
            t = re.sub(r"(\btitle\s*=\s*)\{((?:[^{}]|\{[^{}]*\})*)\}", r"\1{{\2}}", src.read_text(encoding="utf-8"))
            dst = out.with_name(f"_{b.strip()}.bib"); dst.write_text(t, encoding="utf-8"); bibs.append(dst)
    ref = out.with_name("reference_ulster.docx"); reference_doc(ref)
    cmd = [PANDOC, str(tmp), "-f", "latex", "-t", "docx", "-o", str(out), "--citeproc",
           "--resource-path", ";".join(str(p) for p in (LATEX / "figures", GEN / "figures")),
           "--metadata", "title=" + title, "--metadata", "lang=en-GB", "--metadata", "link-citations=true",
           "--reference-doc", str(ref)] + sum([["--bibliography", str(b)] for b in bibs], [])
    if CSL.exists():
        cmd += ["--csl", str(CSL)]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    print(r.returncode, (r.stderr or "")[:2000])
    unresolved = sorted(set(re.findall(r"\\hyperref\[([^\]]+)\]\{\1\}", body)))
    if unresolved:
        print("references without a target:", ", ".join(unresolved))
    return r.returncode


def reference_doc(dest):
    """pandoc's default reference.docx with the Ulster page set-up written into its XML"""
    raw = subprocess.run([PANDOC, "--print-default-data-file", "reference.docx"], capture_output=True).stdout
    zin = zipfile.ZipFile(io.BytesIO(raw)); buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/styles.xml":
                s = data.decode("utf-8")
                s = re.sub(r"<w:rFonts [^>]*/>", '<w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:eastAsia="Arial" w:cs="Arial" />', s)
                s = s.replace('w:val="en-US"', 'w:val="en-GB"')
                i = s.find("<w:pPrDefault>")                                    # 1.5 lines, space after paragraphs
                j = s.find("<w:spacing", i)
                if i != -1 and j != -1:
                    k = s.find("/>", j) + 2
                    s = s[:j] + '<w:spacing w:after="160" w:line="360" w:lineRule="auto" />' + s[k:]
                data = s.encode("utf-8")
            if item.filename == "word/document.xml":
                s = data.decode("utf-8")
                sect = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1417" w:right="1417" w:bottom="1417" '
                        'w:left="2268" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>')
                s = re.sub(r"<w:sectPr.*?</w:sectPr>", sect, s, flags=re.S) if "<w:sectPr" in s else s.replace("</w:body>", sect + "</w:body>")
                data = s.encode("utf-8")
            zout.writestr(item, data)
    dest.write_bytes(buf.getvalue())


if __name__ == "__main__":
    sys.exit(main())
