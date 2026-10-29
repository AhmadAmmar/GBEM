# Earth Engine composites

Exports annual Earth observation composites for the study areas from Google Earth Engine and processes them locally.

- `gbem_composites.js`, `spec.py`, `extents.py`: product definitions, extents and export grids.
- `ingest.py`, `preprocess.py`, `extract.py`, `extract_embed.py`, `fp_stats.py`: local ingest, preprocessing and
  per-building / per-cell extraction.
- `check_sources.py`, `stability.py`, `compare_old.py`: quality checks.

Run the scripts in the `eo` conda environment; each script's docstring gives its arguments.
