# Changelog

All notable changes to this project are documented here. Versions follow [Semantic Versioning](https://semver.org/): MAJOR for incompatible changes to scripts' inputs or outputs, MINOR for new analyses or pipeline stages, PATCH for fixes.

## [0.5.0] - 2026-09-30

### Added
- `review/prior_literature.py` harvests the literature of earlier work (reference lists of reports and presentations, BibTeX library, PDF library). It resolves each citation to a DOI through Crossref (and the arXiv API for preprints), flags citations whose DOI belongs to another work or does not exist, and flags retracted articles. Results are cached, so re-runs are reproducible offline.
- Earlier documented searches (`EARLIER_SEARCHES`) are combined with the current search. Each record keeps the searches that found it and, where the current string misses it, the concept block that is not matched.
- Works from earlier literature that no search retrieves become PRISMA "other methods" records and are screened with the same rules. `prior_literature_status.csv` gives the route and decision for every earlier work, and it is also a sheet in `review_tables.xlsx`.
- The PRISMA diagram shows both identification routes. The manuscript macros cover the earlier search, the earlier literature and the decisions made on titles only.

### Changed
- Bibliometric indicators remain based on database records only. Core-set analyses (map, modality maps, country profiles, abstract word cloud) use every included study.

### Fixed
- Retracted articles and errata are excluded as ineligible record types (a retracted article was previously screened as an included study).
- Decisions made without an abstract are flagged (`title_only`) for verification first.

## [0.4.0] - 2026-09-30

### Added
- `review/new_iteration.py` also builds a companion contents document (table of contents, list of figures, list of tables) when the manuscript template provides `tools/make_contents.py`, and copies it to `PDF/` with the time stamp. The manuscript itself stays in journal format.

## [0.3.1] - 2026-09-30

### Fixed
- Keyword-block figure laid out as a 2 x 2 grid, so the fourth panel is no longer cut off.
- Performance figure legend shows the colour of each validation design.
- Evidence-map axis labels wrap at word boundaries without overlapping.
- Thematic map leaves room for cluster labels at the plot edges.
- Focused-studies map: labels of neighbouring points no longer overlap; legend moved clear of the markers.

## [0.3.0] - 2026-09-30

### Added
- `review/new_iteration.py --rebuild <iteration> [--rerun]`: compiles an existing iteration again after its text has been edited.
- Conditional manuscript macros `\IfKappa`, `\IfVerified` and `\IfRecall`, so the text reads correctly both before and after dual screening and the recall check; `\ClusterList` lists however many keyword clusters the network produces.

### Changed
- Search metadata set for the Scopus search of 2026-09-30 (export v2: 3,989 records; recall check 15 of 17 benchmark studies).
- Values that are not yet available are no longer printed as a status word; the surrounding sentence changes instead.
- Annual-output figure: milestone labels placed above the bars on alternating levels; legend above the plot.

### Fixed
- Scopus document types are normalised at ingest (current exports write "Conference paper", older ones "Conference Paper"); previously conference papers in new exports were removed as an ineligible record type.
- Focused-subset candidates without a DOI were appended to the extraction sheet again on every run; they are now matched by title.

## [0.2.0] - 2026-09-30

### Added
- `review/s07_maps_textmining.py`: word clouds of author keywords, abstracts and Conclusions of full texts; minimal maps of affiliation countries, study-area countries by data modality and focused study areas; country profiles by target and method; country collaboration network; national output over time; `review_tables.xlsx` workbook of all tables; top authors.
- `review/requirements.txt`.
- `tools/make_inventory.py` and `docs/INVENTORY.md`: dated inventory of all scripts with purpose and status.

### Changed
- `review/new_iteration.py` commits and tags each new manuscript iteration in the manuscript repository, when one exists.
- Values that are not yet available (inter-rater agreement, recall check) are reported with a status word in place of the value.
- Earlier review figure scripts (`keywords_CA.py`, `prisma_CA.py`, `CAP_prisma.py`, `CAP_prisma_animate.py`) moved to `scripts/visualization/archive/`; superseded by `review/`.
- Description headers added to UPRN cleaning, random-forest SHAP and data-folder utility scripts.

### Removed
- Empty file `scripts/data_processing/uprn_inside_footprint.py`.

## [0.1.0] - 2026-09-30

### Added
- Apache-2.0 licence, NOTICE (copyright Ulster University), citation metadata (`CITATION.cff`) and data policy (`DATA.md`).
- `review/`: analysis pipeline for the systematic review and bibliometric analysis (ingest and de-duplication of Scopus and Web of Science exports, rule-assisted screening with reviewer overrides and inter-rater agreement, bibliometric indicators and figures, focused-subset extraction support, full-text snippet extraction, LaTeX outputs).

### Changed
- Scripts reorganised into `scripts/data_processing`, `scripts/ml`, `scripts/visualization` and `scripts/utils` with snake_case names; hard-coded paths made consistent; Belfast UPRN join key standardised; ML features selected by column name.

### Removed
- Building-level map outputs containing property-level EPC records are no longer tracked (`maps/*.html`).
