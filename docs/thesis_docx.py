"""Word version of the thesis from the same LaTeX source, with research-helpers' LaTeX-to-Word converter.

    python thesis_docx.py <out.docx>

The converter (research_helpers.latex2docx, https://github.com/GeospatialGeeks/research-helpers) flattens main.tex and
its inputs for pandoc and lays the result out like the PDF:
  - headings, tables and figures carry the numbers of the PDF (Chapter 5, 5.2, Table 5.2, Appendix A) and every
    \\ref / \\cref is a link with the same text as in the PDF; result macros (generated/numbers.tex) become values;
  - longtable, tabularx, adjustbox and \\multicolumn become plain tables with booktabs rules; PNG beside each PDF figure;
  - title page as in the PDF (word-count statement at the foot, no page number), roman page numbers for the preliminary
    pages and arabic from Chapter 1; contents and lists of figures and tables as Word fields;
  - citations by pandoc citeproc from the same BibTeX files, in the Ulster Harvard (LHS) style of ulster-harvard-lhs.csl;
  - Ulster page set-up: A4, binding margin 40 mm, others 25 mm, Arial 12 pt, 1.5 line spacing, page numbers top right.
research-helpers is used from its installed package or, when it is not installed in this environment, from the source
folder in RESEARCH_HELPERS_SRC (default ~/dev/research-helpers/src).
"""
import os, pathlib, re, sys

CODE = pathlib.Path(__file__).resolve().parents[1]
TH = CODE.parent / "Manuscripts/02_Thesis"
LATEX, GEN = TH / "latex", TH / "generated"
CSL = LATEX / "ulster-harvard-lhs.csl"                      # (Author Year): Ulster Library Harvard LHS
_conda_pandoc = pathlib.Path(sys.executable).parent / "Scripts" / "pandoc.exe"   # pandoc of the conda environment
if _conda_pandoc.exists():
    os.environ.setdefault("RH_PANDOC", str(_conda_pandoc))

try:
    from research_helpers.latex2docx import convert, PageSetup, TitlePage
except ImportError:
    sys.path.insert(0, os.environ.get("RESEARCH_HELPERS_SRC", str(pathlib.Path.home() / "dev/research-helpers/src")))
    from research_helpers.latex2docx import convert, PageSetup, TitlePage


def main():
    out = pathlib.Path(sys.argv[1])
    main_tex = (LATEX / "main.tex").read_text(encoding="utf-8")
    info = (LATEX / "chapters/00_abbreviations.tex").read_text(encoding="utf-8")
    month = re.search(r"SubmissionMonthYear\}\{([^}]*)\}", info + main_tex)
    title = re.search(r"\{\\Large\\bfseries (.*?)\\par\}", main_tex, re.S).group(1).strip()
    author = re.search(r"\{\\large (.*?)\\par\}", main_tex).group(1)
    statement = re.search(r"\\vfill\s*(I confirm.*?)\\par", main_tex, re.S).group(1).replace("\n", " ")
    front = (f"\\textbf{{{title}}}\n\n{author}\n\nFaculty of Life and Health Sciences of Ulster University\n\n"
             f"Thesis submitted for the degree of Doctor of Philosophy\n\n{month.group(1) if month else ''}\n\n{statement}\n\n")
    code = convert(LATEX / "main.tex", out, csl=CSL if CSL.exists() else None, numbers=[GEN / "numbers.tex"], front_matter=front,
                   page=PageSetup(left_mm=40, right_mm=25, top_mm=25, bottom_mm=25, font="Arial", size_pt=12, line_spacing=1.5),
                   title_page=TitlePage(sizes_pt=(17.28, 14.4), gaps_mm=(0, 20, 15, 10, 10), bottom=1))
    print(code)
    return code


if __name__ == "__main__":
    sys.exit(main())
