# Changelog

All notable changes to this project are documented here. Versions follow [Semantic Versioning](https://semver.org/): MAJOR for incompatible changes to scripts' inputs or outputs, MINOR for new analyses or pipeline stages, PATCH for fixes.

## [0.27.0] - 2026-10-21

### Added
- `gee/gbem_composites.js` 2.1.0: export batches for the remaining years, each with its own Drive folder:
  - `b2`: 2020–2021;
  - `b3`: 2022–2023, with the heatwave and cold-spell windows;
  - `b4`: 2025.

  Each batch is at most 5 GB before compression. The method version in the file names stays `v2_0_1`, because the
  composites are defined as before, so all years can be combined.
- `gee/README.md`: batch table, the meaning of the method and script versions, and data availability by year. Landsat 9
  data start in late 2021, so 2020–2021 surface temperature comes from Landsat 8 alone.

## [0.26.0] - 2026-10-21

### Added
- `qgis/s1_maps.py` (PyQGIS, run inside QGIS 4): derives four Sentinel-1 bands in dB from the Earth Engine composite:
  VV, VH, the VV−VH polarisation ratio (same definition as the earlier `s1_VV_minus_VH_dB`) and the total power
  (span). It styles them as a layer group: a false-colour composite (R VV, G VH, B VV−VH); VV and VH in grey; the
  ratio in viridis; the span in magma, each stretched between the 2nd and 98th percentiles. Observation count and
  incidence angle are added for quality checks. Each style is saved as QML. The script exports A4 maps (PNG, 200 dpi) of
  Greater London and of central London.
- Not derived, with the reason recorded in the script: VH−VV, VV/VH, the normalised difference and the dual-polarisation
  RVI. In the earlier Belfast samples, all four have a rank correlation of ±1.000 with VV−VH, so they add no information.
  VV+VH taken on dB values has no physical meaning.

## [0.25.1] - 2026-10-21

### Added
- `gee/check_sources.py`: checks, through the Earth Engine Python API, that every dataset used by
  `gbem_composites.js` exists and has the bands used. It also reports the number of scenes per study area and time
  window of a year. The 2024 and 2022 checks passed. Exception: no Landsat scene covers Greater Belfast in the December
  2022 cold-spell window, so that band is empty.

### Changed
- `gee/gbem_composites.js` 2.0.1: Copernicus DEM `COPERNICUS/DEM/GLO30` (deprecated) replaced by its successor
  `COPERNICUS/DEM/GLO30_2024_1` (same `DEM` band).

## [0.25.0] - 2026-10-21

### Added
- `gee/gbem_composites.js` (version 2.0.0): Earth Engine composites for Greater London and Greater Belfast. It exports
  multi-band GeoTIFFs to Drive, one per area, product and year, with the time windows (annual, summer, winter, and the
  2022 heatwave and cold-spell events) as bands. The products are:
  - Sentinel-2 L2A with Cloud Score+;
  - Sentinel-1 VV/VH;
  - Landsat 8/9 and MODIS land surface temperature;
  - ERA5-Land climate with heating and cooling degree days;
  - VIIRS night lights;
  - WorldCover, Copernicus DEM and GHSL building height and volume.

  The extents are in the national grids, snapped to 3 km so that all resolutions nest. The script has a dry-run plan
  with size estimates and a provenance table of input scenes. Indices and the per-building extraction move to local
  processing.
- `gee/extents.py` (export extents from the local boundaries) and `gee/README.md`.

## [0.24.0] - 2026-10-21

### Added
- `review/s10_ml_extract.py`: OCR of scanned PDFs (RapidOCR) and sentence-embedding retrieval (all-MiniLM-L6-v2) of evidence sentences per extraction field, with a zero-shot validation-design suggestion combined with the stage 9 rules (validation design agreement with the reviewer: 9 of 14, against 8 of 14 for the rules alone). Runs in `run_all.py` when the packages of `review/requirements-ml.txt` are installed, and is skipped otherwise.
- `review/s11_llm_extract.py` (optional, run on its own): extraction with a language model through the Claude Messages API, using a JSON schema and a verbatim supporting quote per field; every quote is checked against the PDF text, and responses are cached and requests logged.
- `review/requirements-ml.txt` and `docs/ml_extraction_method.md`.
- `review/new_iteration.py` also writes a copy of the Word manuscript with Track Changes switched on (`*_for_review.docx`) for the supervisors.
- `review/s06_tex_outputs.py` writes the agreement of the automatic extraction with the manual extraction as macros (`\NExtrValAgree`, `\NExtrValN`, `\NExtrMetFound`, `\NExtrMetN`).

### Changed
- `review/s09_fulltext_extract.py`: the matching of works to PDFs is a separate function (`works_with_pdfs`), shared with stages 10 and 11; results unchanged.

## [0.23.0] - 2026-10-21

### Added
- `review/s09_fulltext_extract.py` reads metric values from the results tables of each PDF (layout-preserving text: header cells, column alignment, row labels; mean ± deviation keeps the mean), in addition to the sentences. Agreement with the reviewer's extraction rose from 8 to 11 of 13 headline metric values.
- `docs/fulltext_extraction_method.md`: description of the extraction method, its outputs and its agreement with the reviewer.

### Fixed
- Error metrics written as plain numbers; values written before the metric name; MAPE given as a percentage without the sign; sentences citing other work are no longer used for validation, metrics or sample size.

## [0.22.0] - 2026-10-21

### Added
- Full-text extraction as pipeline stage `review/s09_fulltext_extract.py`: reads every PDF of the review page by page and extracts study area, named datasets, sample sizes, target and classes, methods and interpretability, validation design and split ratios, metric values, code and data availability, and uncertainty, each with the page and sentence it came from. Sentences that cite other work are not used for validation, metrics or sample size. Outputs: `fulltext_extraction_auto.csv`, `fulltext_evidence.csv`, `focused_prefill.xlsx` (reviewer's values next to the suggestions) and `stats_fulltext_extract.json`, which reports agreement with the reviewer's extraction. The extraction sheet is never changed by this stage.

## [0.21.0] - 2026-10-21

### Added
- `review/new_iteration.py` checks that every figure and table of the manuscript is referred to in the text; any that are not are printed and listed in `build/checks.txt`.

### Changed
- Workflow figure refers to the merged Results section (Sections 3.1 and 3.2).

## [0.20.0] - 2026-10-14

### Added
- `review/new_iteration.py` builds a two-column print preview of the manuscript in the journal layout when the manuscript template provides `tools/make_print.py`, and copies it to `PDF/` with the time stamp. The submission manuscript keeps its single-column review format.

## [0.19.0] - 2026-10-14

### Changed
- Keyword clusters are formed on association-strength weights (co-occurrences relative to the number expected from the two keyword frequencies, as in VOSviewer). With raw counts the network split into two clusters whose centralities are equal by construction, which made the thematic map uninformative.
- Thematic-map figure: panel (b) below panel (a) at full width, so that no keyword is cut off; cluster labels beside the bubbles; plain axis numbers without an offset.

## [0.18.1] - 2026-10-14

### Changed
- `review/s06_tex_outputs.py` writes the macro `\ModalityRanking`: the data modalities of the core set from the most to the least frequent, with counts and shares, so that the sentence in the text follows the data.

## [0.18.0] - 2026-10-14

### Added
- `review/collect_fulltexts.py` also reads the PDFs in the download folders (`DOWNLOAD_DIRS` in `local_settings.py`): a file whose DOI, or failing that title, belongs to a record of the review is copied to the full-text folder. The originals stay where they are; first-page text is cached.
- `review/fulltext_status.py` gives Zotero the review PDFs it does not hold yet, through Zotero's own connector service on the local machine (as the browser Connector does): Zotero stores the file, recognises the paper and files it in the collection `fulltext_to_download`. Each file is offered once (`zotero_push_log.csv`); nothing happens when Zotero is not running. `zotero_to_attach.csv` lists PDFs that remain to be attached by hand. Option `--no-zotero` turns this off.

## [0.17.0] - 2026-10-14

### Added
- `review/fulltext_status.py`: checklist page of the full texts still to retrieve, with a live status for each work (PDF in the review folder; PDF in Zotero; record in Zotero without a PDF; not in Zotero). Each pass collects new Zotero PDFs and writes `remaining_status.js` and `remaining_status.csv`; with `--watch N` it repeats every N seconds and the open page refreshes its status every 30 seconds. Works whose PDF has reached the review folder are ticked automatically.

### Changed
- `review/collect_fulltexts.py`: the collection step is a function (`collect`) that other tools call; checksums are cached between passes.

## [0.16.0] - 2026-10-12

### Added
- `review/collect_fulltexts.py`: copies the PDF attachments of a Zotero library that belong to records of the review (matched by DOI, or by title where there is no DOI, through a copy of the Zotero database) into the full-text folder, and writes `fulltext_manifest.csv` (DOI, status in the review, origin, SHA-256, date first recorded) and `collect_log.csv`. Files are only copied; nothing is moved, renamed or deleted.
- `ZOTERO_DIR` setting (machine-specific, in `local_settings.py`).
- `review/fetch_open_access.py` can use the Elsevier Article Retrieval API when an API key is configured locally. This path has not been run yet.

## [0.15.0] - 2026-10-09

### Added
- `review/new_iteration.py` collects every figure of the manuscript with its caption in one PDF when the manuscript template provides `tools/make_figures.py`, and copies it to `PDF/` with the time stamp.
- The PRISMA diagram is also saved as PDF.
- `review/s08_triage.py` writes `fulltext_to_download.ris` for import into a reference manager.

## [0.14.0] - 2026-10-09

### Added
- `review/s06_tex_outputs.py` writes `tab_candidates.tex`: the candidates that the triage rules rate as likely, with country, data and method coded from the abstract, for a separate appendix table of studies provisionally included at abstract level. Macros `\IfTier` and `\NTier`.
- `review/fetch_open_access.py` also uses the open-access addresses recorded by Semantic Scholar.

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
