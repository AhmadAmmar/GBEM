# Changelog

All notable changes to this project are documented here. Versions follow [Semantic Versioning](https://semver.org/): MAJOR for incompatible changes to scripts' inputs or outputs, MINOR for new analyses or pipeline stages, PATCH for fixes.

## [0.13.0] - 2026-10-09

### Added
- `review/s08_triage.py` writes `focused_candidates_evidence.csv` and `.xlsx` (one sheet per triage class): for every pending candidate, a provisional abstract-level decision, the reasons, the abstract, and the abstract-level coding (country, data modality, target, method family, validation terms, metric values).

## [0.12.1] - 2026-10-09

### Changed
- The screening flow figure reports the triage of the pending candidates (likely, unclear, unlikely; full texts read) in its last box.

## [0.12.0] - 2026-10-09

### Added
- `review/s08_triage.py` (new pipeline stage): sorts the candidates for the focused subset into likely, unclear and unlikely with keyword rules that test whether the rating is the estimated target, whether estimates are made for individual buildings, and whether a method and a metric are reported. It reads titles and abstracts and, where a PDF is in the literature library, the full text. Outputs: `focused_triage.csv` (with reasons and the sentences that triggered them), `focused_triage_check.csv` (the same rules applied to studies already decided), `fulltext_to_download.csv` and `stats_triage.json`. The stage never changes a reviewer decision.
- `review/fetch_open_access.py`: retrieves open-access full texts of the candidates from the locations listed in OpenAlex (no account or e-mail address is sent), keeps a file only if its first pages match the DOI or title, and logs every attempt. PDFs are stored in the private literature folder, outside the repository.
- Manuscript macros `\NTriageLikely`, `\NTriageUnclear`, `\NTriageUnlikely`, `\NTriageFullText`, `\NTriageCheck...` and `\IfPending`.

## [0.11.0] - 2026-10-08

### Changed
- Screening is by a single reviewer by default: `DUAL_SAMPLE_FRACTION` in `review/config.py` is 0, so no second-reviewer sample is drawn and no inter-rater agreement is computed. Setting it above 0 restores the sample and Cohen's kappa.
- Figures state that reviewer verification is pending until decisions have been entered.

### Added
- `verification_queue.csv`: the work list for the reviewer, with decisions resting on weak evidence first, then included records, then excluded records.
- Manuscript macros `\IfDual` and `\NRuleChanged`.

## [0.10.0] - 2026-10-08

### Added
- `review/new_iteration.py` exports every table of the manuscript as printed (one CSV per table, a workbook with one sheet per table and an index of captions, and a PDF of all tables) when the manuscript template provides `tools/make_tables.py`, and copies the workbook and the PDF to `DOC/` and `PDF/` with the time stamp.

## [0.9.0] - 2026-10-08

### Added
- `review/s05_figures.py` draws the screening decision flow (`figS_screening_rules.png` and `.pdf`): the search components and limits, each screening criterion in the order it is applied with the number of records leaving at that step, the two inclusion routes, verification, and the focused subset. Counts are read from the screening decisions, so the figure follows every run.

## [0.8.0] - 2026-10-08

### Changed
- First-pass screening rules rewritten (`review/s01_screen.py`, dictionaries in `review/common.py`). A record is now included only if every eligibility criterion is met in its title or abstract: built object, energy-efficiency outcome, a named geospatial or remote-sensing data source or method (author keywords also count; index keywords do not) and stock scale. Urban heat island, urban form and land use on their own are treated as setting, not as a geospatial method. Close-range sensing and building models are eligible only when applied to many buildings. Previously a record was included unless an exclusion rule matched, and no built-object criterion was tested.
- Studies that estimate an energy rating are included through a separate route that does not require a geospatial term. `screening_decisions.csv` has two new columns: `route` and `to_verify` (decisions resting on weak evidence, to be checked first).
- Articles that are reviews by their title are set aside as reviews.
- Search metadata set for the widened Scopus search (query v5; 7,746 records; 17 of 17 benchmark studies). "Data paper" is an eligible document type.
- Ambiguous terms tightened: "footprint" requires a building or data context, "airborne" and "satellite" require a sensing context, "transformer" requires a model context.

### Added
- Manuscript macros `\NCoreRouteGeo`, `\NCoreRouteRating`, `\NToVerify` and `\IfRecallAll`.

### Fixed
- HTML entities left by the database in titles, abstracts and keywords are decoded at ingest.
- "Energy consumption" of buildings counts as an outcome term (a benchmark study was excluded without it).

## [0.7.0] - 2026-10-08

### Added
- `SCOPING_EXPORTS` in `review/config.py`: exports of earlier scoping searches whose search string was not preserved. Records in them that the current search does not return are screened as records identified by other methods and stay out of the bibliometric corpus.
- Manuscript macros `\IfScoping`, `\NScopingOther`, `\NCoreScoping` and `\IfPeakLast` (wording when the incomplete last year already has the highest output).

### Changed
- Search metadata set for the single combined Scopus search of 2026-10-08 (title-abstract-keyword component OR title component; 4,615 records). `EARLIER_SEARCHES` is now empty and reserved for searches whose preserved string reproduces their export.
- `new_iteration.py` does not carry an unfilled second-reviewer sample forward: it is redrawn for the new record set.
- PRISMA diagram wording for a single search.

### Fixed
- The 2025 export was previously combined as a documented title search; its string does not reproduce the export, so it is now treated as a scoping export.

## [0.6.0] - 2026-10-01

### Added
- `review/prior_literature.py` also reads the reference lists of reports saved as PDF, and reference lists that have no heading (trailing blocks of references in .docx files).
- `review/new_iteration.py` accepts a build only if LaTeX reports no errors and no undefined citations or references; otherwise it stops with a message and copies nothing.
- Two rating-estimation studies added to the focused seed table (Dai et al., 2025; Sun et al., 2022).

### Changed
- Coding dictionaries: rating targets include "energy efficiency classification", efficiency bands and grades; machine-learning methods include attention and fusion networks, multi-branch and graph neural networks.
- Spatially blocked cross-validation counts as testing on unseen areas.

### Fixed
- Unresolved citations keep their cited text in `prior_literature_status.csv`.

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
