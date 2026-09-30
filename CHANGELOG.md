# Changelog

All notable changes to this project are documented here. Versions follow [Semantic Versioning](https://semver.org/): MAJOR for incompatible changes to scripts' inputs or outputs, MINOR for new analyses or pipeline stages, PATCH for fixes.

## [0.2.0] - 2026-09-30

### Added
- `review/s07_maps_textmining.py`: word clouds of author keywords, abstracts and Conclusions of full texts; minimal maps of affiliation countries, study-area countries by data modality and focused study areas; country profiles by target and method; country collaboration network; national output over time; `review_tables.xlsx` workbook of all tables; top authors.
- `review/requirements.txt`.
- `tools/make_inventory.py` and `docs/INVENTORY.md`: dated inventory of all scripts with purpose and status.

### Changed
- `review/new_iteration.py` commits and tags each new manuscript iteration in the manuscript repository, when one exists.
- Values that are not yet available (inter-rater agreement, recall check) are reported as "pending".
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
