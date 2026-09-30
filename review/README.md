# Review analysis pipeline

Turns the database exports into every number, table and figure in the review manuscript, and builds the PDF and Word versions in a new time-stamped iteration folder.

## Setup

- Python 3.11+ with the packages in `requirements.txt` (`pip install -r requirements.txt`); `pdftotext` (Poppler) for full-text support; a LaTeX distribution with `latexmk`; `pandoc` for the Word version.
- Data locations are machine-specific: copy `local_settings.example.py` to `local_settings.py` (git-ignored) or set the `GBEM_*` environment variables described in `config.py`.
- Database exports, the PDF library and the manuscript are **not** part of this repository (publisher and database licences; unpublished work).

## Run it

1. Save the exports (see `Lit/Scopus/2026-09-30_query_v2.txt`, Step 3):
   - Scopus CSV → `Lit/Scopus/2026-09-30_scopus_v2.csv` (or `_part1.csv`, `_part2.csv`, …)
   - Web of Science tab-delimited → `Lit/WoS/2026-09-30_wos_v2_part1.txt`, …
2. Put the hit counts, search date and recall-check result into `SEARCH` in `config.py`.
3. Run:
   ```bash
   cd code/review
   python new_iteration.py --version 0.3
   ```
   This creates `iterations/<date>_<time>_v0.3/`, runs all stages, compiles `Review_v0.3.pdf` and `Review_v0.3.docx` into its `build/`, and copies both to `PDF/` and `DOC/` with the time stamp. Add `--skip-fulltext` for a faster run, or `--no-build` to run the analysis only.

To re-run the analysis inside an existing iteration: `python run_all.py --iteration <iteration folder>`.

## Stages

| Script | Does | Outputs (`analysis/outputs/`) | Feeds |
|---|---|---|---|
| `s00_ingest.py` | Reads Scopus CSV and WoS exports, harmonises fields, removes duplicates (ID, DOI, title + year) | `records.csv`, `duplicates.csv`, `stats_ingest.json` | PRISMA identification |
| `s01_screen.py` | Rule-based first-pass screening; applies reviewer decisions; draws the 20% dual-screening sample; Cohen's kappa; abstract-level coding | `screening_decisions.csv`, `stats_screening.json` | PRISMA screening, Section 4, Table 7, Figs 5 and 10 |
| `s02_bibliometrics.py` | Growth, sources, countries, citations, keyword network, thematic map and evolution, world map | `stats_biblio.json`, CSV tables; `fig04`–`fig08` | Section 3, Table 6, Appendix F |
| `s03_focused.py` | Builds the focused-subset candidate list; merges the full-text extraction sheet | `focused_final.csv`, `focused_candidates_pending.csv`, `stats_focused.json` | Tables 8, 9, D, E; Figs 11–12 |
| `s04_fulltext.py` | Finds library PDFs by DOI or title; extracts Conclusions and sentences on validation, metrics, linkage, time gaps, uncertainty and data availability | `pdf_doi_index.csv`, `fulltext_snippets.csv`, `fulltext_missing.csv` | Support for extraction and appraisal |
| `s05_figures.py` | PRISMA diagram, framework, workflow, timeline, evidence map, performance, validation, roadmap, graphical abstract | `latex/figures/*.png` | Figs 1–3, 9–13, graphical abstract |
| `s07_maps_textmining.py` | Word clouds (author keywords, abstracts, Conclusions of focused full texts); minimal maps of where papers come from (affiliations), where each data modality is applied, and the focused study areas; country profiles by target and method; country collaboration network; national output over time; all tables in one Excel workbook | `review_tables.xlsx`, `top_authors.csv`, `stats_extras.json`; `figS1`–`figS9` | Appendix H (supplementary figures) |
| `s06_tex_outputs.py` | Writes `\newcommand` macros for every number, the generated table bodies and the search string; fetches BibTeX by DOI for new focused studies | `latex/generated/*.tex`, `references.bib` additions | Every number and generated table in the text |

`run_all.py` writes `analysis/outputs/MANIFEST.md`, which records this mapping for each run.

## Human inputs (`analysis/inputs/`, carried forward between iterations)

| File | Who fills it | Used for |
|---|---|---|
| `screening_overrides.csv` | First reviewer: `rid, decision, reason, reviewer, date` for every record checked | Verified decisions replace rule decisions |
| `dual_screening_reviewer2.csv` | Second reviewer: `decision_reviewer2` for the pre-drawn sample | Cohen's kappa |
| `focused_extraction.csv` | Full-text extraction (one row per study; set `include_focused` to Y or N for new candidates marked `?`) | Tables 8, 9, D, E; Figs 11–12 |
| `supplementary_studies.csv` | Studies found by citation searching or expert suggestion (`doi, study, year, route, note`) | PRISMA "other methods"; focused subset |

Allowed decisions: `Included (core)`, `Excluded (T/A)`, `Review (umbrella)`, `Excluded (record type)`.

## Manuscript template

The manuscript template (location set by `TEMPLATE_DIR`; kept outside this repository until the paper is published) is the manuscript with numbers written as macros (for example `\NCore`, `\CAGR`, `\NHeldOut`) and generated table bodies read with `\tabinput{generated/...}`. It is copied into the first pipeline-driven iteration; later iterations carry their own edited copy forward. Numbers update automatically on each run; sentences marked `%% CHECK` in the source interpret the data and must be re-read after each run.
