# GBEM

Geospatial Building Energy Mapping

## Scripts

All project scripts are located under the `scripts/` directory:

- `scripts/data_processing` – data manipulation utilities and workflows
- `scripts/ml` – machine learning experiments
- `scripts/visualization` – scripts for generating plots and maps
- `scripts/utils` – small helper utilities
  - Includes `inspect_dataset.py` for reporting row counts, column names, and
    metadata for arbitrary dataset files.
- All scripts follow snake_case file names for clarity.
  - Several scripts were renamed for clarity (e.g. `annual.py` → `split_by_year.py`).
  - Legacy row-count scripts such as `count_rows_in_files.py` remain available for reference.

Each folder contains the Python scripts previously located in the project root.
