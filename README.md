# GBEM: Geospatial Building Energy Mapping

Code for estimating and mapping the energy efficiency of buildings from Earth observation and geospatial data, developed as part of a PhD project in the School of Geography and Environmental Sciences, Ulster University.

## Contents

| Folder | Contents |
|---|---|
| `scripts/data_processing` | Data preparation: EPC certificates, UPRN and coordinate linkage, OpenStreetMap buildings, Google Earth Engine extraction, spectral indices, zonal statistics |
| `scripts/ml` | Machine learning experiments for EPC rating and efficiency-class prediction |
| `scripts/visualization` | Figures, maps, PRISMA and workflow diagrams |
| `scripts/utils` | Helper utilities (for example `inspect_dataset.py` for row counts, columns and metadata) |
| `review/` | Analysis pipeline for the systematic review and bibliometric analysis of remote sensing and geospatial methods for building energy efficiency: screening, bibliometric indicators, keyword networks, word clouds, maps of where research is produced and applied, country profiles, tables and figures (see `review/README.md`) |
| `tools/` | Repository utilities (`make_inventory.py`) |
| `docs/` | [INVENTORY.md](docs/INVENTORY.md): every script with its purpose, last-change date and status |

All scripts use snake_case file names. Superseded scripts are kept for the record and marked as such in the inventory.

## Data

No input or derived building-level data are stored in this repository. See [DATA.md](DATA.md) for the data sources and their terms of use.

## Licence and ownership

Copyright © Ulster University. Released under the [Apache License 2.0](LICENSE); see [NOTICE](NOTICE). Third-party data remain subject to their own licences.

## Citation

Please cite this software using the metadata in [CITATION.cff](CITATION.cff) (GitHub: "Cite this repository").
