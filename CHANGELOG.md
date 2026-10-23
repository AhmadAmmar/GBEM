# Changelog

All notable changes to this project are documented here. Versions follow [Semantic Versioning](https://semver.org/): MAJOR for incompatible changes to scripts' inputs or outputs, MINOR for new analyses or pipeline stages, PATCH for fixes.

## [0.37.0] - 2026-10-23

### Added
- `models/baseline.py`: LightGBM and random forest predict the A–G band and the SAP score.
  - Feature sets:
    - EO only;
    - + morphology, streets and LiDAR;
    - + Census context;
    - + certificate attributes.
  - Validation: spatial 5-fold cross-validation on 2 km blocks, with random 5-fold for comparison.
  - Outputs: metrics, out-of-fold predictions and LightGBM importance.
  - Place and source identifiers (ward code, LiDAR survey) are excluded. Numbers stored as text are read as numbers.
  - `--sample` runs the models on a random sample of certificates.
  - Results for 2024, spatial validation, LightGBM:

    | Area | Feature set | Accuracy | κw | SAP MAE |
    |---|---|---|---|---|
    | Belfast | EO | 0.42 | 0.17 | 9.9 |
    | Belfast | + morphology and LiDAR | 0.48 | 0.33 | 8.7 |
    | Belfast | all | 0.65 | 0.72 | 5.0 |
    | London (50k sample) | EO | 0.49 | 0.24 | 6.3 |
    | London (50k sample) | + morphology and LiDAR | 0.52 | 0.37 | 5.9 |
    | London (50k sample) | all | 0.68 | 0.70 | 4.3 |

  - Random folds overstate accuracy by 2–7 points. Census context adds nothing beyond morphology.
- `viz/dashboard.py` and `viz/dashboard_template.html`: interactive dashboard, one self-contained page per area and
  model run, written to `maps/dashboard/`. It holds property-level data, so it is never committed (`.gitignore` now
  covers `maps/**/*.html`). It replaces the Folium maps of April 2025, whose predictions were in-sample.
  - Two linked maps: actual band, predicted band, error, SAP score, confidence or a building feature.
  - Views: properties, or 250 m to 1 km grid cells (cells with fewer than 5 certificates hidden).
  - Filters: year, band, property type, built form, age band and tenure.
  - Live metrics, confusion matrix, band distribution and accuracy by group.
  - The cross-validated results and the reproduction of the earlier set-up.
  - Built with deck.gl over Esri grey canvas basemaps.
- `epc/lidar_london.py`: London building height and roof form per footprint from the batch b6 export, with the same
  columns as `lidar_ni.py`.
  - 2,113,317 of 2,141,314 footprints have values.
  - Median heights: houses 6.4 m, bungalows 3.7 m, flats 11.6 m (Belfast: 6.5, 4.0 and 8.6 m).
- `hotsat/assess_hotsat.py`: assessment of the three HotSat-1 scenes.
  - The scenes:
    - 13 July 2023: south-west Belfast, night;
    - 8 October 2023: Southampton, night;
    - 25 November 2023: Runcorn/Widnes, afternoon.
  - All three are the uncalibrated "visual" product.
  - Correlation with the SAP score is at most 0.19.
  - Adding HotSat to spatially cross-validated SAP models raises the error at all three sites. Not used as a predictor.

### Fixed
- `epc/lidar_ni.py`: four 2012 River Basin surveys are stored in millimetres (Saintfield, Mossley, Glenavy, Bangor
  extension). Their heights came out about 1000 times too large and their slopes were distorted. Tiles with a median
  above 2000 are now converted to metres, and the converted surveys are listed in `lidar_log.json`.

## [0.36.0] - 2026-10-23

### Added
- `gee/gbem_composites.js` 2.3.0: batch `b6`, London building height and roof form from the Environment Agency LiDAR
  composite (`UK/EA/ENGLAND_1M_TERRAIN/2022`), aggregated from 1 m to 2 m over the London core extent.
  - Normalised surface height (first-return surface minus terrain), with roof slope and aspect.
  - Only building-height pixels (at least 1.5 m) are kept.
  - Bands:
    - `height_dm` and `height_max_dm`: mean and maximum height, in decimetres;
    - `slope_ddeg`: slope, in tenths of a degree;
    - `south_pct` and `flat_pct`: south-facing and flat shares.
  - Large enough that Earth Engine splits it into tiles.
- `gee/spec.py` and `gee/ingest.py`: the static product `lidar_ea_2m`.
  - Tiled exports are recognised (`<name>-<row>-<col>.tif`).
  - Each tile is checked for pixel size and alignment with the area grid.
- `epc/certificates.py`: `--ni-source ni2026` (now the default), the Northern Ireland register to 31 March 2026 from
  Finance NI, read from its zip.
  - UPRNs are normalised and joined to the OSNI address points.
  - The earlier January 2025 master is still available as `ni2025`.
  - The new file contains every certificate of the earlier master unchanged: 73,251 certificates against 57,567.
  - 2025 now has 13,027 certificates (was 963); 2026 has 3,583.
- `models/reproduce_old.py`: reproduction of the earlier random forest set-up on the current tables, in four variants:
  - R1: the earlier random 70/30 split;
  - R2: with certificate attributes added;
  - R3: split by location;
  - R4: about 1 km spatial blocks.

  Neither the reported accuracies (about 75% London, 70% Belfast) nor anything close is reached:
  - R1 accuracy is 0.54 in London and 0.51 in Belfast.
  - With spatial blocking (R4), macro-F1 falls to about 0.17–0.18.

## [0.35.0] - 2026-10-22

### Added
- `epc/lidar_ni.py`: building height and roof form for Greater Belfast from the OpenDataNI LiDAR: the Belfast City 2006
  survey and 17 River Basin surveys, 2007–2014, read directly from their zips.
  - Pairing:
    - Surface and terrain tiles are paired by location, because file names differ between surveys.
    - `.grd` files are ESRI ASCII grids.
    - Point-cloud surfaces (Ballygowan, Carryduff) are gridded by the highest return per cell.
    - Damaged tiles are skipped and logged: 99, mostly truncated Ballyclare 2009 tiles and the empty Dunmurry 2007
      surface tiles.
  - Features per footprint, from the most recent survey covering at least 80% of it:
    - height median and 90th percentile;
    - roof slope;
    - south-facing and flat roof shares;
    - `built_after_survey` when the median height is under 2 m.
  - Results:
    - 303,962 of 417,229 footprints have a value; 80% of Belfast properties.
    - Median heights by property type: bungalows 4.0 m, houses 6.5 m, flats 8.5 m.
    - Median roof slope is about 35°.
  - Lisburn and Newtownabbey are published with terrain models only, so they have no heights.
- `epc/assemble.py`: LiDAR features as the group `lidar`.

## [0.34.0] - 2026-10-22

### Added
- `epc/census_ni.py`: Census 2021 ward context for Greater Belfast certificates (NISRA MS-E06, MS-E11, MS-E13, MS-E15;
  OSNI ward boundaries 2012, all 462 codes match). It gives shares of accommodation type, central heating fuel,
  renewable systems and tenure. The ward sheets list each ward twice (counts, then percentages); the counts are
  used. `epc/assemble.py` adds the shares as the feature group `census_context`. In 2024, the SAP score's rank
  correlation is +0.20 with the mains-gas share and −0.20 with the oil share.
- `epc/get_ni_lidar.py`: downloads the OpenDataNI River Basin LiDAR surveys (DTM and DSM, OGL) that overlap Greater
  Belfast. There are 17 surveys from 2007 to 2014, chosen from the extents index and matched to files by name.
  Edenderry has no file in the package.

### Data (not in the repository)
- `data/belfast/lidar/opendatani_belfast_city_2006/`: Belfast City LiDAR 2006 (0.5 m DTM and DSM, four zones, OGL).
- `data/belfast/census2021_nisra/`: Census 2021 housing tables (MS-E01 to MS-E19) and CT0062 and CT0082.
- `data/belfast/boundaries_osni/`: ward boundaries 2012.
- `data/belfast/sources/2026-10-22/`: Finance NI EIR response DOF/2026-0254. All NI EPC data, 2008 to March 2026, is
  public in a Box folder that has to be downloaded in a browser.

## [0.33.1] - 2026-10-22

### Changed
- `epc/README.md`: counts from the October 2026 register, and the modelling tables. All years 2020–2025 are
  extracted for both areas: London 1,501,415 certificates, Belfast 57,551. Multi-year thermal features are complete
  for every certificate.

## [0.33.0] - 2026-10-21

### Added
- `epc/certificates.py --source ew2026` (default): the England and Wales register of 13 October 2026
  (`domestic-csv.zip`, certificates 2008–2026).
  - The London rows of the 19 yearly files are streamed out of the 98 GB zip without extracting it.
  - Coordinates come from OS Open UPRN by UPRN.
  - The new format has lower-case columns, `certificate_number` instead of `LMK_KEY`, and no coordinates.
  - London: 4,444,008 certificates at 2,890,924 UPRNs, 2007–2026. 196,138 have no location: 187,282 have no UPRN, and
    8,856 have a UPRN not yet in OS Open UPRN 2025-07.
  - `--source ew2025` rebuilds from the January 2025 snapshot.
- Multi-year thermal composites (batch b5, 2020–2025):
  - `gee/preprocess.py --multi` writes their rural references (`--no-static` skips terrain and land cover).
  - `gee/extract.py` adds `landsatmulti_` (point and neighbourhoods) and `modismulti_` (point) LST and sUHI to every
    certificate year.
  - `epc/assemble.py` puts them in the feature group `thermal_multiyear`.

## [0.32.1] - 2026-10-21

### Fixed
- `gee/gbem_composites.js` 2.2.2: the 2.2.1 padding made every thermal window with scenes fail ("Expected a
  homogeneous image collection... Mismatched type for band 'LST'"). The masked placeholder was a plain float, the
  scenes a bounded float. All images are now cast to float before the placeholder is added. Tested on the Earth Engine
  server with a window with scenes (Belfast summer 2024) and an empty one (cold spell 2022). The 2.2.1 test had covered
  only the empty window. Batches b1–b4 were exported with 2.1.0, before the padding, and are not affected; b3fix and b5
  need to be run again.

## [0.32.0] - 2026-10-21

### Added
- `safeio.py`: no output is overwritten. Every pipeline script moves an existing file to `_archive/<run time>/`
  before writing. `gee/ingest.py` never replaces a raw file: identical content (zip CRC) is skipped, and different
  content is written alongside as `<name>__conflict<n>.tif` and reported.
- `epc/dwellings.py`: UPRNs per footprint and area per UPRN (OS Open UPRN for London, the OSNI UPRN list for
  Belfast), and the position of each property along its block. It is needed because London footprints often cover
  whole terrace rows.
- `epc/assemble.py`: a modelling table per area and imagery year, with a data dictionary of feature groups.

### Fixed
- `epc/certificates.py`: repeated certificate ids (1,298 identical copies in the Northern Ireland file) are dropped
  and counted. They would have put the same certificate in training and test data.

## [0.31.1] - 2026-10-21

### Fixed
- `gee/gbem_composites.js` 2.2.1: a time window without any scene made the export fail. The case found was Belfast
  Landsat 2022: no scene in the December 2022 cold-spell window ("Image.multiply: If one image has no bands...").
  Thermal collections are now padded with one fully masked image, so an empty window exports as a missing band with
  count 0. Scene counts in the provenance table are taken before the padding. Windows with scenes are unchanged, so
  the method version stays v2_0_1. Batch `b3fix` reruns only the failed export. The fix was tested on the Earth
  Engine server with the failing window.

## [0.31.0] - 2026-10-21

### Added
- `epc/`, a documented certificate table per study area (objective 2):
  - `certificates.py`: all certificates with a property location, with rules and flags (repeats, new dwellings,
    UPRN match source, same-day duplicates).
    - London: 3,880,812 certificates, 2008–2024. The 25 GB register is streamed through DuckDB.
    - Greater Belfast: 58,865 certificates, 2020–2025.
  - `footprints.py`: footprints from Overture Maps (release 2026-09-23.1). OpenStreetMap alone misses up to 70% of
    the buildings in outer London boroughs. Belfast uses OSNI inside the council area and Overture outside it.
  - `link.py`: UPRN point to footprint (inside, else nearest within 5 m). Unlinked: London 4.1%, Belfast 0.6%.
  - `morphology.py`:
    - shape, shared walls and adjacency;
    - coverage, count and mean area at 100 m and 250 m;
    - street distance and density;
    - height, floors and volume where Overture gives them;
    - the OSNI dwelling type.
  - `README.md`: sources, rules, counts and checks.
- `gee/gbem_composites.js` 2.2.0: batch b5, multi-year thermal composites (Landsat and MODIS, 2020–2025, by
  season), because single-year thermal composites are unstable year to year.

### Changed
- `gee/extract.py` version 2:
  - area-weighted footprint means (2 m sub-grid);
  - neighbourhoods at 50, 100, 250 and 500 m, with standard deviation from 100 m;
  - certificate mode (`--certificates`): each certificate gets the imagery of its inspection year.
- `gee/spec.py` and `gee/ingest.py` know the multi-year products.

## [0.30.0] - 2026-10-21

### Added
- `gee/stability.py`: year-to-year stability of each feature on the same certificates (Spearman correlation per
  pair of years).
- Batch b2 (2020–2021) ingested: 24 files, all checks passed. Preprocessed and extracted for the 2024 certificate set.

### Findings (2024 certificates, imagery of 2020, 2021 and 2024)
- Stable features (worst pair ρ ≥ 0.82): night lights, heating degree days, Sentinel-1 VV and VV−VH, NDVI, NDBI,
  SWIR reflectance.
- Unstable features (ρ 0.07–0.31): Landsat and MODIS land surface temperature and the surface urban heat island.
  Subtracting the rural reference removes the shift in level between years, but not the change in pattern. A
  single-year thermal composite mostly reflects that year's few clear days. A multi-year thermal composite is
  proposed.
- Absolute Landsat temperatures depend on the clear days of the year: the rural summer median in Belfast is
  20.7 °C in 2020 and 31.1 °C in 2021.

## [0.29.0] - 2026-10-21

### Added
- `viz/meeting_pack_gee.py`: builds a meeting pack from the outputs of the `gee/` pipeline, in
  `Outputs/<date>_GEE_data_v2/`. It contains:
  - map panels per area;
  - a chart of agreement with the earlier 2024 samples;
  - a chart of feature coverage;
  - the Sentinel-1 maps;
  - a one-page `dashboard.html` with the headline numbers and tables.

## [0.28.0] - 2026-10-21

### Added
- Local processing of the Earth Engine exports (`gee/`), all sharing `spec.py` (grids, products, band names, scale
  factors; checked against the Earth Engine script):
  - `ingest.py`: extracts the exports to `data/<area>/gee_v2/raw/`. It checks grid, band names, data type, missing
    values and plausible ranges at full resolution. Reading the GeoTIFF overviews would give values that are not in
    the data. It writes a manifest with checksums.
  - `preprocess.py`: terrain from the DEM (water artefacts below −5 m masked), WorldCover shares at 100 m, ERA5 wind
    speed and direction, and rural reference temperatures for the surface urban heat island.
  - `extract.py`: values per certificate:
    - at the certificate point;
    - as the footprint mean (footprints rasterised once, so flats in one building share it);
    - as the mean over about 100 m.

    Sentinel-2 indices are computed per pixel; Sentinel-1 is averaged in linear power. 2024 has been extracted for
    109,955 London and 6,685 Belfast certificates, with 270 features each.
  - `compare_old.py`: agreement with the earlier 2024 samples.
- `qgis/load_gee_layers.py`: a QGIS project per area and year with all products styled (WorldCover in the ESA class
  colours, DEM hillshade) and a quick-look PNG per layer.

### Changed
- The urban index is (B12−B8)/(B12+B8). The earlier UI was B11/B8, which carries the same information as NDBI.
- IBI is not derived: its denominator can be close to zero (earlier values reached ±30,000).
- `qgis/s1_maps.py` reads the Sentinel-1 composite from `data/london/gee_v2/raw/`.

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
