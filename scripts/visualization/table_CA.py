# -*- coding: utf-8 -*-
"""
Literature Insights Table — Confirmation Assessment (v1.0)
==========================================================

One‑click script to (re)build a clean, print‑ready "Literature Insights" table
for your confirmation assessment report. No CLI args needed.

What it does
------------
• Creates a CSV template if your source file doesn't exist yet (so you can paste rows).
• Validates and normalizes controlled vocab (methods, data sources, targets, etc.).
• Exports:
   1) Markdown table chunk (for your .md / .docx pipeline)
   2) DOCX (A4 landscape) with wrapped cells & sensible column widths
   3) LaTeX longtable (optional; off by default)
• Also writes small summary tables (method counts, data-source counts, targets, metrics)
  to help you write the narrative "insights" paragraph quickly.

Edit the I/O paths below and just run.

Dependencies
------------
    pip install pandas python-docx tabulate unidecode

Tested on Python 3.10+
"""

import os
import sys
import textwrap
from collections import Counter
from datetime import datetime
from typing import List, Dict

import pandas as pd
from tabulate import tabulate
from unidecode import unidecode

try:
    from docx import Document
    from docx.shared import Inches, Pt
    from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
    from docx.oxml.shared import OxmlElement, qn
except Exception as e:
    print("[WARN] python-docx not available — DOCX export will be skipped.")
    Document = None

# ───────────────────────── I/O CONFIG ─────────────────────────
BASE_OUT = r"D:/OneDrive - Ulster University/PhD/Output/lit_insights"
SRC_CSV = os.path.join(BASE_OUT, "literature_insights_master.csv")
OUT_MD = os.path.join(BASE_OUT, "literature_insights_table.md")
OUT_DOCX = os.path.join(BASE_OUT, "literature_insights_table.docx")
OUT_LATEX = os.path.join(BASE_OUT, "literature_insights_table.tex")

# Toggle LaTeX export
EXPORT_LATEX = False

# ───────────────────────── SCHEMA ─────────────────────────
COLUMNS = [
    "study_id",            # short key e.g., LON-2019-01
    "authors",             # "Surname et al."
    "year",                # 4‑digit
    "title",               # paper title
    "venue",               # journal/conf/thesis
    "doi_url",             # DOI or stable link
    "geography",           # country/city/region
    "scale",               # building / neighbourhood / city / region / national
    "building_type",       # domestic / non‑domestic / mixed / NA
    "data_sources",        # pipe‑separated: EPC|Sentinel‑2|Sentinel‑1|Landsat LST|LiDAR|TIR HR|Street View|NTL|Socioecon|Weather|LCZ|DEM
    "methods",             # pipe‑separated: RF|XGB|SVM|CNN|Transformer|OLS|GWR|SEM|KMeans|DBSCAN|SHAP|Calib|Ensemble
    "targets",             # pipe‑separated: EPC(A–G)|EUI|U‑value|Heat loss|LST|Consumption|Retrofit need
    "validation",          # k‑fold / spatial‑CV / temporal split / holdout / LOAO
    "metrics",             # pipe‑separated: Accuracy|Macro‑F1|RMSE|R2|AUROC|Kappa|Within‑one‑grade|MAE
    "key_findings",        # 1–2 sentences
    "limitations",         # 1–2 sentences
    "relevance",           # 1 sentence: why useful for our PhD
    "objective_link",      # 1|2|3|4 (your PhD objectives)
    "code_available",      # Y/N or link
    "dataset_available",   # Y/N or link
]

CONTROLLED_VOCAB = {
    "scale": {
        "building": ["building", "bldg", "house", "parcel"],
        "neighbourhood": ["neighborhood", "neighbourhood", "ward"],
        "city": ["city", "urban", "metro"],
        "region": ["region", "state", "province"],
        "national": ["national", "country", "nationwide"],
    },
    "building_type": {
        "domestic": ["domestic", "residential", "housing", "homes"],
        "non‑domestic": ["non-domestic", "nondomestic", "commercial", "tertiary", "public"],
        "mixed": ["mixed", "both"],
        "na": ["na", "n/a", "unknown", "—"]
    },
}

# Allowed tokens for pipe‑separated fields (case‑insensitive)
TOKENS = {
    "data_sources": [
        "EPC", "Sentinel-2", "Sentinel-1", "Landsat LST", "LiDAR", "TIR HR",
        "Street View", "NTL", "Socioecon", "Weather", "LCZ", "DEM"
    ],
    "methods": [
        "RF", "XGB", "SVM", "CNN", "Transformer", "OLS", "GWR", "SEM",
        "KMeans", "DBSCAN", "SHAP", "Calib", "Ensemble"
    ],
    "targets": [
        "EPC(A–G)", "EUI", "U-value", "Heat loss", "LST", "Consumption", "Retrofit need"
    ],
    "metrics": [
        "Accuracy", "Macro-F1", "RMSE", "R2", "AUROC", "Kappa", "Within-one-grade", "MAE"
    ],
}

# Columns to wrap for display
WRAP_COLS = ["title", "key_findings", "limitations", "relevance"]

# Column order for the final compact table (readable A4 landscape)
DISPLAY_COLS = [
    "authors", "year", "geography", "scale", "building_type",
    "data_sources", "methods", "targets", "validation", "metrics",
    "key_findings", "limitations", "relevance", "doi_url"
]

# DOCX layout (A4 landscape) widths in inches — tune if needed
DOCX_COL_WIDTHS_IN = [
    1.6,  # authors
    0.6,  # year
    1.0,  # geography
    0.9,  # scale
    1.0,  # building_type
    1.3,  # data_sources
    1.2,  # methods
    1.2,  # targets
    1.1,  # validation
    1.2,  # metrics
    2.2,  # key_findings
    1.8,  # limitations
    1.8,  # relevance
    1.6,  # doi_url
]

assert len(DOCX_COL_WIDTHS_IN) == len(DISPLAY_COLS)

# ───────────────────────── HELPERS ─────────────────────────
def ensure_dirs():
    os.makedirs(BASE_OUT, exist_ok=True)


def make_template_csv(path: str):
    """Write a starter CSV with a few example rows and the right headers."""
    template_rows = [
        {
            "study_id": "LON-2019-01",
            "authors": "Smith et al.",
            "year": 2019,
            "title": "Estimating EPC grades from Sentinel‑2 indices and EPC labels",
            "venue": "Energy & Buildings",
            "doi_url": "https://doi.org/xx.xxxx/xxxx",
            "geography": "London, UK",
            "scale": "city",
            "building_type": "domestic",
            "data_sources": "EPC|Sentinel-2|Socioecon",
            "methods": "RF|GWR",
            "targets": "EPC(A–G)",
            "validation": "spatial‑CV",
            "metrics": "Macro-F1|Kappa|Within-one-grade",
            "key_findings": "Spectral built‑up & greenness indices were strong predictors; spatial CV reduced optimism vs k‑fold.",
            "limitations": "Seasonality in imagery; EPC labels noisy.",
            "relevance": "Validates Sentinel‑2 indices + spatial CV approach for our pipeline.",
            "objective_link": 1,
            "code_available": "N",
            "dataset_available": "N",
        },
        {
            "study_id": "BFS-2021-02",
            "authors": "Garcia & Lee",
            "year": 2021,
            "title": "Street‑view façades + LiDAR for heat‑loss risk mapping",
            "venue": "Remote Sensing of Environment",
            "doi_url": "https://doi.org/yy.yyyy/yyyy",
            "geography": "Belfast, UK",
            "scale": "neighbourhood",
            "building_type": "mixed",
            "data_sources": "Street View|LiDAR|Weather|EPC",
            "methods": "CNN|RF|SHAP",
            "targets": "Heat loss|Retrofit need",
            "validation": "holdout",
            "metrics": "AUROC|Accuracy|MAE",
            "key_findings": "Façade texture + roof height explained retrofit priority; SHAP helped interpret local drivers.",
            "limitations": "Street‑view coverage bias; LiDAR year mismatch.",
            "relevance": "Supports integrating street‑view + LiDAR features.",
            "objective_link": 1,
            "code_available": "Y (https://github.com/author/repo)",
            "dataset_available": "Partial",
        },
    ]
    df = pd.DataFrame(template_rows, columns=COLUMNS)
    df.to_csv(path, index=False)


def normalize_basic(s: str) -> str:
    if pd.isna(s):
        return ""
    s = unidecode(str(s)).strip()
    return s


def map_to_vocab(value: str, mapping: Dict[str, List[str]], default: str) -> str:
    v = normalize_basic(value).lower()
    for canon, aliases in mapping.items():
        if v == canon:
            return canon
        if v in [a.lower() for a in aliases]:
            return canon
    return default


def normalize_row(row: pd.Series) -> pd.Series:
    # Scale & building_type controlled maps
    row["scale"] = map_to_vocab(row.get("scale", ""), CONTROLLED_VOCAB["scale"], default="city")
    row["building_type"] = map_to_vocab(row.get("building_type", ""), CONTROLLED_VOCAB["building_type"], default="na")

    # Pipe‑separated sets — keep only allowed tokens, preserve original order
    def norm_tokens(val: str, allowed: List[str]) -> str:
        if pd.isna(val) or str(val).strip() == "":
            return ""
        items = [normalize_basic(t) for t in str(val).split("|")]
        canon = []
        allowed_lower = {a.lower(): a for a in allowed}
        for it in items:
            key = it.lower()
            # exact or case‑insensitive match
            if key in allowed_lower:
                canon.append(allowed_lower[key])
            else:
                # lenient aliases
                key2 = key.replace(" ", "").replace("-", "")
                for a in allowed:
                    if key2 == a.lower().replace(" ", "").replace("-", ""):
                        canon.append(a)
                        break
        # dedupe while keeping order
        seen = set()
        deduped = []
        for t in canon:
            if t not in seen:
                seen.add(t)
                deduped.append(t)
        return "|".join(deduped)

    for col in ["data_sources", "methods", "targets", "metrics"]:
        row[col] = norm_tokens(row.get(col, ""), TOKENS[col])

    # Tidy text fields
    for col in WRAP_COLS + ["authors", "geography", "venue", "validation", "doi_url", "title"]:
        row[col] = normalize_basic(row.get(col, ""))

    # Year as int
    try:
        row["year"] = int(str(row.get("year", "")).strip().split(".")[0])
    except Exception:
        row["year"] = ""

    # objective_link as int or blank
    try:
        row["objective_link"] = int(row.get("objective_link", 1))
    except Exception:
        row["objective_link"] = ""

    return row


def load_and_normalize(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str).fillna("")
    # enforce all columns
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = ""
    # normalize row‑wise
    df = df[COLUMNS].apply(normalize_row, axis=1)
    # sort helpful default: by year desc, then authors
    with pd.option_context('mode.chained_assignment', None):
        df["year_num"] = pd.to_numeric(df["year"], errors="coerce")
    df.sort_values(["year_num", "authors"], ascending=[False, True], inplace=True)
    df.drop(columns=["year_num"], inplace=True)
    return df.reset_index(drop=True)


def wrap_text(s: str, width: int) -> str:
    if not s:
        return s
    # keep pipes/newlines intact where used to separate tokens
    if "|" in s and len(s) <= width * 2:
        return s.replace("|", " | ")
    return "\n".join(textwrap.fill(s, width=width).splitlines())


def df_for_display(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    for c in WRAP_COLS:
        d[c] = d[c].apply(lambda x: wrap_text(x, 90))
    # also wrap some compact cols lightly
    for c in ["data_sources", "methods", "targets", "metrics"]:
        d[c] = d[c].apply(lambda x: wrap_text(x, 40))
    for c in ["geography", "validation", "building_type", "scale"]:
        d[c] = d[c].apply(lambda x: wrap_text(x, 18))
    d["year"] = d["year"].astype(str)
    return d[DISPLAY_COLS]


# ───────────────────────── EXPORTS ─────────────────────────

def export_markdown(df: pd.DataFrame, out_path: str):
    md = tabulate(df, headers="keys", tablefmt="pipe", showindex=False)
    header = (
        f"<!-- Auto‑generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} -->\n"
        f"### Literature Insights — Master Table (condensed)\n\n"
        f"_Note:_ Cells are wrapped for readability. Tokens inside cells use `|` as separators.\n\n"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(header + md + "\n")
    print(f"[OK] Markdown table → {out_path}")


def set_cell_margins(cell, **kwargs):
    # kwargs: top, start, bottom, end in twips
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for k, v in kwargs.items():
        node = OxmlElement(f"w:{k}")
        node.set(qn('w:w'), str(v))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)


def export_docx(df_display: pd.DataFrame, out_path: str):
    if Document is None:
        print("[SKIP] DOCX export — python-docx missing.")
        return

    doc = Document()
    # A4 landscape & margins
    section = doc.sections[0]
    section.orientation = 1  # 0=portrait, 1=landscape
    section.page_height, section.page_width = section.page_width, section.page_height
    section.left_margin = Inches(0.4)
    section.right_margin = Inches(0.4)
    section.top_margin = Inches(0.4)
    section.bottom_margin = Inches(0.4)

    # Title
    p = doc.add_paragraph("Literature Insights — Master Table (condensed)")
    p.style = doc.styles['Heading 2']
    p.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT

    # Table
    rows, cols = df_display.shape
    table = doc.add_table(rows=rows + 1, cols=cols)
    table.style = 'Table Grid'

    # Header row
    for j, col in enumerate(df_display.columns):
        hdr = table.cell(0, j)
        hdr.text = col.replace("_", " ")
        run = hdr.paragraphs[0].runs[0]
        run.font.bold = True
        run.font.size = Pt(10)
        set_cell_margins(hdr, top=60, start=80, bottom=60, end=80)
        hdr.vertical_alignment = 1
        hdr.width = Inches(DOCX_COL_WIDTHS_IN[j])

    # Body
    for i in range(rows):
        for j in range(cols):
            cell = table.cell(i + 1, j)
            txt = str(df_display.iat[i, j])
            # tighten overly long cells a bit
            wrap_w = 110 if df_display.columns[j] in ["key_findings", "limitations", "relevance"] else 60
            txt_wrapped = wrap_text(txt, wrap_w)
            cell.text = txt_wrapped
            set_cell_margins(cell, top=60, start=80, bottom=60, end=80)
            for run in cell.paragraphs[0].runs:
                run.font.size = Pt(9)

    doc.save(out_path)
    print(f"[OK] DOCX table → {out_path}")


def export_latex(df: pd.DataFrame, out_path: str):
    # Light‑weight LaTeX longtable for Overleaf; you can style further if needed.
    # Note: We escape only basic characters — adjust as necessary for your stack.
    def esc(s: str) -> str:
        return (str(s)
                .replace('&', r'\&')
                .replace('%', r'\%')
                .replace('#', r'\#')
                .replace('_', r'\_')
                .replace('~', r'\textasciitilde ')
                .replace('^', r'\textasciicircum '))
    cols = df.columns.tolist()
    spec = "|" + "|".join(["p{0.12\\textwidth}" for _ in cols]) + "|"
    header = [esc(c) for c in cols]
    lines = ["\\begin{longtable}{" + spec + "}", "\\hline", " \\textbf{" + "} & \\textbf{".join(header) + "} \\ \\ ", "\\hline", "\\endfirsthead",
             "\\hline", " \\textbf{" + "} & \\textbf{".join(header) + "} \\ \\ ", "\\hline", "\\endhead"]
    for _, row in df.iterrows():
        vals = [esc(row[c]).replace("\n", " \\newline ") for c in cols]
        lines.append(" " + " & ".join(vals) + r" \\ ")
        lines.append("\\hline")
    lines.append("\\end{longtable}")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[OK] LaTeX longtable → {out_path}")


# ───────────────────────── SUMMARIES ─────────────────────────

def tally_tokens(series: pd.Series) -> Counter:
    c = Counter()
    for s in series.dropna().astype(str):
        for t in [t.strip() for t in s.split("|") if t.strip()]:
            c[t] += 1
    return c


def export_summaries(df: pd.DataFrame):
    out_txt = os.path.join(BASE_OUT, "literature_insights_summaries.txt")

    counts = {
        "Data sources": tally_tokens(df["data_sources"]),
        "Methods": tally_tokens(df["methods"]),
        "Targets": tally_tokens(df["targets"]),
        "Metrics": tally_tokens(df["metrics"]),
        "Validation": Counter(df["validation"].dropna().astype(str))
    }

    lines = [f"Summaries generated {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]

    for name, counter in counts.items():
        lines.append(f"## {name}")
        for k, v in counter.most_common():
            lines.append(f"- {k}: {v}")
        lines.append("")

    with open(out_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[OK] Summaries → {out_txt}")


# ───────────────────────── MAIN ─────────────────────────

def main():
    ensure_dirs()

    if not os.path.exists(SRC_CSV):
        make_template_csv(SRC_CSV)
        print("[SETUP] Created template CSV. Populate it, then re‑run this script.")
        print(f"         → {SRC_CSV}")
        return

    df = load_and_normalize(SRC_CSV)

    # Condensed display table
    disp = df_for_display(df)

    # Exports
    export_markdown(disp, OUT_MD)
    export_docx(disp, OUT_DOCX)
    if EXPORT_LATEX:
        export_latex(disp, OUT_LATEX)

    export_summaries(df)

    print("\n[Done] Literature insights tables regenerated.")
    print(f"Rows: {len(df)} | Out: {BASE_OUT}")


if __name__ == "__main__":
    main()
