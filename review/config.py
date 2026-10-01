"""Paths and search metadata for the review pipeline.

Data locations are machine-specific and are NOT stored in the repository. They are read from,
in order: environment variables (GBEM_PROJECT_ROOT, GBEM_LIT_DIR, GBEM_REVIEW_DIR, GBEM_TEMPLATE_DIR),
then local_settings.py (copy local_settings.example.py; git-ignored), then the default layout
<project root>/code/review, <project root>/Lit, <project root>/Manuscripts/01_Review.

Edit the SEARCH block after each database run.
"""
import os, pathlib

try:
    import local_settings as _ls   # git-ignored, per machine
except ImportError:
    _ls = None


def _setting(name, default):
    v = os.environ.get("GBEM_" + name) or (getattr(_ls, name, None) if _ls else None)
    return pathlib.Path(v) if v else default


PHD = _setting("PROJECT_ROOT", pathlib.Path(__file__).resolve().parents[2])
LIT = _setting("LIT_DIR", PHD / "Lit")
REVIEW = _setting("REVIEW_DIR", PHD / "Manuscripts" / "01_Review")
TEMPLATE = _setting("TEMPLATE_DIR", REVIEW / "pipeline" / "template")   # manuscript template (kept private until publication)

# ---------------------------------------------------------------------------
# Search metadata (PRISMA-S). Update after running the queries.
# ---------------------------------------------------------------------------
SEARCH = {
    "query_file": LIT / "Scopus" / "2026-09-30_query_v2.txt",
    "search_date": "2026-09-30",            # date the database searches were run
    "field": "TITLE-ABS-KEY",
    "years": (2000, 2026),
    "doc_types": ["Article", "Review", "Conference Paper"],
    # database exports (glob patterns); multi-part exports are concatenated
    "scopus_glob": str(LIT / "Scopus" / "2026-09-30_scopus_v2*.csv"),
    "wos_glob": str(LIT / "WoS" / "2026-09-30_wos_v2*.txt"),
    # hit counts shown by the database interfaces (for the PRISMA box); None = use export size
    "scopus_hits": 3989,                  # Scopus, run 2026-09-30, exported 17:24 (export v2)
    "wos_hits": None,
    "recall_benchmark": {"n": 17, "retrieved": 15},     # Step 2 of the query file; see Lit/Scopus/EXPORT_LOG.md
}

# Supplementary evidence (citation searching / expert suggestion)
OTHER_METHODS_DIRS = [LIT / "New Lit", LIT / "New Lit 1", LIT / "Relevant", LIT / "Review"]

# Earlier documented database searches, combined with the current one (each: label, date, query file, export glob)
EARLIER_SEARCHES = [
    {"label": "Scopus title search", "date": "2025-10-07", "field": "TITLE",
     "query_file": LIT / "Scopus" / "2025-10-07_query_v1.txt", "glob": str(LIT / "Scopus" / "2025-10-07_scopus.csv")},
]

# The authors' previous work: literature cited in assessment reports and presentations, the reference library
# and the PDF library (harvested and verified against Crossref by prior_literature.py)
PRIOR = {
    "documents": [PHD / "DOC", PHD / "PPT"],                  # .docx / .pptx reports and presentations
    "pdf_reports": [PHD / "PDF"],                              # final versions of reports saved as PDF
    "exclude_pdf": ["Certificate", "Outline", "Contents"],
    "exclude": ["Review_Paper", "Review Paper"],               # drafts of this review are not prior work
    "bib": LIT / "LitRev.bib",
    "pdf_dirs": [LIT],
    "out_dir": LIT / "prior_literature",
}

# Human inputs (created as templates on first run; filled in by the review team)
HUMAN = {
    "screening_overrides": "screening_overrides.csv",      # verified decisions (first reviewer)
    "second_screener": "dual_screening_reviewer2.csv",     # independent decisions on the sample
    "focused_extraction": "focused_extraction.csv",        # full-text extraction sheet
    "supplementary_studies": "supplementary_studies.csv",  # studies found by other methods
}

DUAL_SAMPLE_FRACTION = 0.20
RANDOM_SEED = 20260930
MIN_KEYWORD_OCC = 8          # co-occurrence network threshold
PERIODS = [(2000, 2014), (2015, 2019), (2020, 2026)]


def paths(iteration_dir):
    """Folder layout inside one iteration."""
    it = pathlib.Path(iteration_dir)
    p = {
        "it": it,
        "analysis": it / "analysis",
        "inputs": it / "analysis" / "inputs",      # human-edited CSVs live here
        "out": it / "analysis" / "outputs",
        "fig": it / "latex" / "figures",
        "tex_gen": it / "latex" / "generated",     # numbers.tex + table fragments
        "build": it / "build",
    }
    for k in ["inputs", "out", "fig", "tex_gen", "build"]:
        p[k].mkdir(parents=True, exist_ok=True)
    return p
