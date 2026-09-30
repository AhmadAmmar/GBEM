# GBEM code inventory

Generated 2026-09-30 by `tools/make_inventory.py`. Dates: last commit that changed the file, and file modification date.

## `./`

| File | Purpose | Last commit | Modified | Status |
|---|---|---|---|---|
| `Untitled.ipynb` | import geopandas as gpd | 2026-09-28 | 2026-09-28 | current |

## `review/`

| File | Purpose | Last commit | Modified | Status |
|---|---|---|---|---|
| `common.py` | Shared dictionaries and helpers (coding rules, normalisation, I/O). | 2026-09-30 | 2026-09-30 | current |
| `config.py` | Paths and search metadata for the review pipeline. | 2026-09-30 | 2026-09-30 | current |
| `local_settings.example.py` | Copy to local_settings.py (git-ignored) and edit for your machine. | 2026-09-30 | 2026-09-30 | current |
| `new_iteration.py` | Create the next time-stamped iteration, run the pipeline, build PDF and Word. | 2026-09-30 | 2026-09-30 | current |
| `run_all.py` | Run the full review pipeline for one iteration folder. | 2026-09-30 | 2026-09-30 | current |
| `s00_ingest.py` | Stage 0 - read Scopus CSV and Web of Science exports, harmonise, de-duplicate. | 2026-09-30 | 2026-09-30 | current |
| `s01_screen.py` | Stage 1 - screening and abstract-level coding. | 2026-09-30 | 2026-09-30 | current |
| `s02_bibliometrics.py` | Stage 2 - bibliometric (science-mapping) analysis of the screened corpus. | 2026-09-30 | 2026-09-30 | current |
| `s03_focused.py` | Stage 3 - focused subset: candidate list + full-text extraction sheet. | 2026-09-30 | 2026-09-30 | current |
| `s04_fulltext.py` | Stage 4 - full-text support for extraction. | 2026-09-30 | 2026-09-30 | current |
| `s05_figures.py` | Stage 5 - PRISMA diagram, schematic and synthesis figures. | 2026-09-30 | 2026-09-30 | current |
| `s06_tex_outputs.py` | Stage 6 - write LaTeX fragments that the manuscript \input{}s. | 2026-09-30 | 2026-09-30 | current |
| `s07_maps_textmining.py` | Stage 7 - supplementary bibliometrics: word clouds, minimal maps, country profiles, collaboration, table workb | not committed | 2026-09-30 | current |

## `scripts/data_processing/`

| File | Purpose | Last commit | Modified | Status |
|---|---|---|---|---|
| `add_lat_lon_belfast_uprn.py` | Add X/Y coordinates to uprn_union_list.csv by matching UPRNs | 2026-09-28 | 2026-09-28 | current |
| `add_lat_lon_ni_epc.py` | Join NI EPC CSV to union UPRN-with-XY CSV using a canonical UPRN key | 2026-09-28 | 2026-09-28 | current |
| `add_lat_lon_ni_epc_updated.py` | Create: NI_Domestic_Master_to_01_2025_with_XY_v2.csv | 2026-09-28 | 2026-09-28 | current |
| `add_uprn_saad_paul.py` | Combine Paul's 'uprn_union_with_xy.csv' with Saad's 'uprn_saad_clean.csv' | 2026-09-28 | 2026-09-28 | current |
| `calculate_correlations.py` | Load the dataset | 2026-09-28 | 2026-09-28 | current |
| `certs_w_latlon.py` | Path to the merged certificates file | 2026-09-28 | 2026-09-28 | current |
| `clean_saad_uprn.py` | Clean the Belfast UPRN point file: detect encoding and coordinate columns, normalise UPRNs, write uprn_saad_cl | 2026-09-28 | 2026-09-30 | current |
| `clean_uprn.py` | Clean the merged Belfast UPRN table with coordinates: normalise UPRNs (digits only, Excel scientific notation  | 2026-09-28 | 2026-09-30 | current |
| `column_names.py` | Quick schema peek: | 2026-09-28 | 2025-09-09 | current |
| `concat_certs.py` | Directory containing the subfolders with certificates.csv files | 2026-09-28 | 2026-09-28 | current |
| `concat_certs_lat_lon.py` | Directory containing the subfolders with certificates.csv files | 2026-09-28 | 2026-09-28 | current |
| `download_osm_buildings.py` | File paths | 2026-09-28 | 2026-09-28 | current |
| `drop_multipoly.py` | Paths | 2026-09-28 | 2026-09-28 | current |
| `epc_binary_classification.py` | Load data | 2026-09-28 | 2026-09-28 | current |
| `epcs_per_year.py` | Counts records per year (and unique UPRNs per year) in the IN-FOOTPRINTS EPC file. | 2026-09-28 | 2025-09-01 | current |
| `epcs_per_year2.py` | Counts records per year (and unique UPRNs per year) in the original NI EPC file, | 2026-09-28 | 2025-09-01 | current |
| `extract_cert_sample.py` | File paths | 2026-09-28 | 2026-09-28 | current |
| `extract_new_pts.py` | === File Paths === | 2026-09-28 | 2026-09-28 | current |
| `extract_samples.py` | File paths | 2026-09-28 | 2026-09-28 | current |
| `extract_samples_v1.py` | === File Paths === | 2026-09-28 | 2026-09-28 | current |
| `extract_unique_values.py` | File path | 2026-09-28 | 2026-09-28 | current |
| `extract_zonal.py` | === File Paths === | 2026-09-28 | 2026-09-28 | current |
| `filter_certs_by_bbox.py` | File paths | 2026-09-28 | 2026-09-28 | current |
| `filter_london_buildings.py` | File paths | 2026-09-28 | 2026-09-28 | current |
| `gee_file.py` | === Input file (with polygon geometry and lat/lon columns) === | 2026-09-28 | 2026-09-28 | current |
| `gee_geojson.py` | === File Paths === | 2026-09-28 | 2026-09-28 | current |
| `geojson_to_shp.py` | Load your GeoJSON | 2026-09-28 | 2026-09-28 | current |
| `indices.py` | File paths | 2026-09-28 | 2026-09-28 | current |
| `indices_v1.py` | === Paths === | 2026-09-28 | 2026-09-28 | current |
| `iwt.py` | IWT Indus System – Interactive Map (Folium + OSM + Natural Earth) | 2026-09-28 | 2025-09-08 | current |
| `iwt_build_curated_sites.py` | Optional helpers | 2026-09-28 | 2025-09-08 | current |
| `iwt_fetch_assets.py` | Step 1 — Fetch & Save All IWT Datasets (no mapping) | 2026-09-28 | 2025-09-08 | current |
| `iwt_map_offline.py` | Step 2 — Offline IWT Map (Folium + local datasets only) | 2026-09-28 | 2025-09-08 | current |
| `iwt_map_offline_auto.py` | iwt_map_offline_auto.py | 2026-09-28 | 2025-09-08 | current |
| `london_certs.py` | File paths | 2026-09-28 | 2026-09-28 | current |
| `match_certificates_with_buildings.py` | File paths | 2026-09-28 | 2026-09-28 | current |
| `match_uprn.py` | Paths to directories and files | 2026-09-28 | 2026-09-28 | current |
| `match_uprn_belfast.py` | pip install pandas | 2026-09-28 | 2025-08-29 | current |
| `mixed_cols.py` | File paths | 2026-09-28 | 2026-09-28 | current |
| `mosaic_rasters.py` | Input raster file paths | 2026-09-28 | 2026-09-28 | current |
| `new_indices.py` | === File paths === | 2026-09-28 | 2026-09-28 | current |
| `pipeline.py` | Prepare 2024 EPC targets for GEE (tz-safe, CRS-safe, merge-free polygon export): | 2026-09-28 | 2025-09-10 | current |
| `plot_correlation.py` | File paths | 2026-09-28 | 2026-09-28 | current |
| `print_belfast_data_stats.py` | EPC ↔ UPRN stats report (Belfast / NI) | 2026-09-28 | 2025-08-30 | current |
| `rated_a.py` | Load the CSV file | 2026-09-28 | 2026-09-28 | current |
| `replace_points_with_polygons.py` | Load files | 2026-09-28 | 2026-09-28 | current |
| `reproject_shapefile.py` | File paths | 2026-09-28 | 2026-09-28 | current |
| `s2_rename.py` | Define the input and output folders | 2026-09-28 | 2026-09-28 | current |
| `s2_rescale.py` | Define input and output folders | 2026-09-28 | 2026-09-28 | current |
| `s2_split.py` | Input and output paths | 2026-09-28 | 2026-09-28 | current |
| `saving_samples.py` | File paths | 2026-09-28 | 2026-09-28 | current |
| `spatial_join_epc_with_buildings.py` | === Paths === | 2026-09-28 | 2026-09-28 | current |
| `split_by_year.py` | Directory containing the files | 2026-09-28 | 2026-09-28 | current |
| `split_shapefile_tiles.py` | Paths | 2026-09-28 | 2026-09-28 | current |
| `stats.py` | File paths | 2026-09-28 | 2026-09-28 | current |
| `stats_new.py` | File paths | 2026-09-28 | 2026-09-28 | current |
| `thermal_corr.py` | File paths | 2026-09-28 | 2026-09-28 | current |
| `unique_id.py` | slim_for_gee.py | 2026-09-28 | 2025-09-10 | current |
| `uprn-compare.py` | Compare Saad UPRN CSV vs Paul's union UPRN-with-XY CSV. | 2026-09-28 | 2026-09-28 | current |
| `uprn_belfast_check.py` | UPRN audit & union for three CSVs, with robust encoding handling. | 2026-09-28 | 2026-09-28 | current |
| `uprn_years.py` | Find UPRNs that occur in multiple years in the NI EPC file. | 2026-09-28 | 2025-09-01 | current |
| `uprn_years_footprints.py` | Check multi-year UPRNs inside Belfast footprints. | 2026-09-28 | 2025-09-01 | current |
| `uprn_years_v2.py` | Count UPRNs that occur in multiple years in the EPC-with-XY v2 file. | 2026-09-28 | 2025-09-01 | current |
| `uprns_inside_footprints.py` | Filter EPC points to those inside/on Belfast building footprints. | 2026-09-28 | 2025-08-31 | current |

## `scripts/ml/`

| File | Purpose | Last commit | Modified | Status |
|---|---|---|---|---|
| `rf_basic.py` | Load dataset | 2026-09-28 | 2026-09-28 | current |
| `rf_binary_shap.py` | Random forest for binary EPC efficiency class with confusion matrix, ROC curve and SHAP feature importance. | 2026-09-28 | 2026-09-30 | current |
| `rf_feature_selection.py` | === Load the GeoJSON === | 2026-09-28 | 2026-09-28 | current |
| `rf_predict_geojson.py` | === Load the GeoJSON === | 2026-09-28 | 2026-09-28 | current |
| `rf_predict_tagged.py` | === Load the GeoJSON === | 2026-09-28 | 2026-09-28 | current |

## `scripts/utils/`

| File | Purpose | Last commit | Modified | Status |
|---|---|---|---|---|
| `check_column_order.py` | Directory containing the subfolders with certificates.csv files | 2026-09-28 | 2026-09-28 | current |
| `check_crs.py` | File path | 2026-09-28 | 2026-09-28 | current |
| `check_geom.py` | Path to the shapefile | 2026-09-28 | 2026-09-28 | current |
| `cols.py` | Path to your shapefile | 2026-09-28 | 2026-09-28 | current |
| `column_names.py` | Path to the merged certificates file with latitude and longitude | 2026-09-28 | 2026-09-28 | current |
| `count_rows_in_files.py` | Paths to the merged certificates files | 2026-09-28 | 2026-09-28 | current |
| `del_cols.py` | Paths to the input and output files | 2026-09-28 | 2026-09-28 | current |
| `dtypes.py` | File paths | 2026-09-28 | 2026-09-28 | current |
| `dtypes_new.py` | File paths | 2026-09-28 | 2026-09-28 | current |
| `export_first_rows.py` | === File Paths === | 2026-09-28 | 2026-09-28 | current |
| `first_last_row.py` | Path to the input and output files | 2026-09-28 | 2026-09-28 | current |
| `header.py` | Path to the merged certificates file | 2026-09-28 | 2026-09-28 | current |
| `inspect_dataset.py` | Utility for inspecting dataset files. | 2025-07-22 | 2025-07-30 | current |
| `min_max.py` | Define the directory containing the files | 2026-09-28 | 2026-09-28 | current |
| `num_of_cols.py` | Directory containing the subfolders with certificates.csv files | 2026-09-28 | 2026-09-28 | current |
| `num_of_fields.py` | Path to the merged certificates file | 2026-09-28 | 2026-09-28 | current |
| `num_of_rows.py` | File path to the filtered buildings file | 2026-09-28 | 2026-09-28 | current |
| `num_rows.py` | Report the number of rows in every data file (CSV, Parquet, GeoJSON, GeoPackage, FlatGeobuf, pickle) in the da | 2026-09-28 | 2026-09-30 | current |
| `rows_cols.py` | Path to your matched EPC GeoJSON | 2026-09-28 | 2026-09-28 | current |
| `rows_in_results.py` | Row counts for key EPC artifacts (CSV/XLS/XLSX/JSON/GEOJSON) with D:\ path overrides. | 2026-09-28 | 2026-09-28 | current |
| `rows_uprn.py` | Directory containing the subfolders with certificates.csv files | 2026-09-28 | 2026-09-28 | current |
| `types_of_files.py` | List the file extensions present in the data folder. | 2026-09-28 | 2026-09-30 | current |
| `unique_vals.py` | Path to the certificates file | 2026-09-28 | 2026-09-28 | current |
| `unique_vals_all.py` | File paths | 2026-09-28 | 2026-09-28 | current |
| `years.py` | Load the filtered CSV | 2026-09-28 | 2026-09-28 | current |

## `scripts/visualization/`

| File | Purpose | Last commit | Modified | Status |
|---|---|---|---|---|
| `animation.py` | rf_epc_tree_walk_right_clean.py | 2026-09-28 | 2025-11-14 | current |
| `app_v4.py` | === Load data === | 2026-09-28 | 2026-09-28 | current |
| `app_v5.py` | === Load data === | 2026-09-28 | 2026-09-28 | current |
| `app_v6.py` | === Load data (entire dataset with predictions) === | 2026-09-28 | 2026-09-28 | current |
| `belfast_2023_CA.py` | EPC 2023 subset (Belfast): | 2026-09-28 | 2026-09-28 | current |
| `belfast_CA.py` | belfast_CA.py — key-first ML pipeline + one-page A4 report for Belfast | 2026-09-28 | 2025-10-10 | current |
| `belfast_files_CA.py` | inventory_belfast.py | 2026-09-28 | 2025-10-12 | current |
| `belfast_per_class_rating_CA.py` | belfast_explore_epc.py — EPC class distribution + join audit (Belfast) | 2026-09-28 | 2025-10-10 | current |
| `belfastsinlondon.py` | --- Step 1: Load boundaries --- | 2026-09-28 | 2025-09-29 | current |
| `CA_flowchart.py` | workflow_flowchart_v2_animated_always_legend.py | 2026-09-28 | 2025-10-29 | current |
| `CAP_methods.py` | workflow_flowchart_v2_vertical_slide_status_bullets_fixed_readable.py | 2026-09-28 | 2025-11-12 | current |
| `cfm_CA.py` | Confusion Matrix (stand-alone, auto-inputs, 2× cell size, bigger numbers, no padding) | 2026-09-28 | 2025-10-10 | current |
| `fast_header_scan.py` | Fast header/schema scan for .csv, .shp, .xls, .xlsx (first row only; no full loads). | 2026-09-28 | 2025-09-26 | current |
| `flowchart_CA.py` | workflow_flowchart_v2_compact_a4.py | 2026-09-28 | 2025-10-06 | current |
| `gantt.py` | Define the project timeline tasks | 2025-07-22 | 2025-07-30 | current |
| `gantt_CA.py` | phd_gantt.py | 2026-09-28 | 2026-09-28 | current |
| `map_v1.py` | ------------------------------------------------------------------- | 2026-09-28 | 2026-09-28 | current |
| `map_v2.py` | ------------------------------------------------------------------- | 2026-09-28 | 2026-09-28 | current |
| `map_v4.py` | ------------------------------------------------------------------- | 2026-09-28 | 2026-09-28 | current |
| `overlay.py` | File paths | 2026-09-28 | 2026-09-28 | current |
| `plot.py` | Load your dataset | 2026-09-28 | 2026-09-28 | current |
| `raster_corr.py` | File paths for the two raster files | 2026-09-28 | 2026-09-28 | current |
| `results_maps_combined_CA.py` | EPC vs RF — Print-Ready Map (v3.2, overlap-proof, cached) | 2026-09-28 | 2026-09-28 | current |
| `shap_CA.py` | Quick SHAP (5% stratified sample) for London EPC — robust to SHAP output shapes. | 2026-09-28 | 2026-09-28 | current |
| `study_area_maps_CA.py` | study_area_maps_show_all_points_final.py | 2026-09-28 | 2026-09-28 | current |
| `table_CA.py` | Literature Insights Table — Confirmation Assessment (v1.0) | 2026-09-28 | 2025-10-07 | current |

## `scripts/visualization/archive/`

| File | Purpose | Last commit | Modified | Status |
|---|---|---|---|---|
| `app.py` | === Load your GeoDataFrame === | 2026-09-28 | 2026-09-28 | archived |
| `app_v2.py` | === Load your dataset === | 2026-09-28 | 2026-09-28 | archived |
| `app_v3.py` | === Load test data with predictions === | 2026-09-28 | 2026-09-28 | archived |
| `CAP_prisma.py` | Literature Review — Compact Slide Workflow (Objective 1) — WIDTH-AUTO | not committed | 2026-09-28 | archived; superseded by review/s05_figures.py (workflow figure) |
| `CAP_prisma_animate.py` | Literature Review Workflow (Objective 1) — Focus Animation | not committed | 2026-09-28 | archived; superseded by review/s05_figures.py (workflow figure) |
| `flowchart.py` | Initialize the flowchart with a title | 2026-09-28 | 2025-07-30 | archived |
| `flowchart_v1.py` | Create a new directed graph | 2026-09-28 | 2025-07-30 | archived |
| `flowchart_v2.py` | Create the Digraph object | 2026-09-28 | 2025-07-30 | archived |
| `flowchart_v3.py` | Create the flowchart object | 2026-09-28 | 2025-07-30 | archived |
| `flowchart_v4.py` | Create a new directed graph | 2026-09-28 | 2025-07-30 | archived |
| `keywords_CA.py` | radiant_keywords_clusters.py  (compact, gapless grid) | not committed | 2026-09-28 | archived; superseded by review/s02_bibliometrics.py (keyword blocks, Fig. 7) |
| `prisma_CA.py` | One-Column Literature/Systematic Review — Ultra-Compact (Objective 1) | not committed | 2026-09-28 | archived; superseded by review/s05_figures.py (PRISMA 2020 diagram) |
| `result_map.py` | London EPC vs RF Predictions — Print-Ready Map (v1.4) — All Points + Auto Point Size | 2026-09-28 | 2026-09-28 | archived |
| `result_map_CA.py` | London EPC vs RF Predictions — Print-Ready Map (v2.4, overlap-proof A4) | 2026-09-28 | 2026-09-28 | archived |
| `results_maps_CA.py` | EPC vs RF — Print-Ready Map (v3.0) | 2026-09-28 | 2026-09-28 | archived |
| `study_area_maps.py` | study_area_maps_v20_equalwidth_locator_visible.py | 2026-09-28 | 2026-09-28 | archived |
| `study_area_maps1.py` | study_area_maps_v21_equalwidth_locator_localfallback.py | 2026-09-28 | 2026-09-28 | archived |
| `study_area_maps2.py` | study_area_maps_v28_inset_always_coastlines.py | 2026-09-28 | 2026-09-28 | archived |
| `study_area_maps3.py` | study_area_maps_final.py | 2026-09-28 | 2026-09-28 | archived |
| `study_area_maps4.py` | study_area_maps_final_projection_inset.py | 2026-09-28 | 2026-09-28 | archived |
| `study_area_maps5.py` | study_area_maps_final_inset_4326.py | 2026-09-28 | 2026-09-28 | archived |

## `tools/`

| File | Purpose | Last commit | Modified | Status |
|---|---|---|---|---|
| `make_inventory.py` | Write a dated inventory of every script in a repository. | not committed | 2026-09-30 | current |
