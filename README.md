# GBEM: Geospatial Building Energy Mapping

Code for estimating and mapping the energy efficiency of buildings from Earth observation and geospatial data, developed as part of a PhD project in the School of Geography and Environmental Sciences, Ulster University.

## Contents

| Folder | Contents |
|---|---|
| `scripts/data_processing` | Data preparation: EPC certificates, UPRN and coordinate linkage, OpenStreetMap buildings, Google Earth Engine extraction, spectral indices, zonal statistics |
| `scripts/ml` | Machine learning experiments for EPC rating and efficiency-class prediction |
| `scripts/visualization` | Figures, maps, PRISMA and workflow diagrams |
| `scripts/utils` | Helper utilities (for example `inspect_dataset.py` for row counts, columns and metadata) |
| `review/` | Analysis pipeline for the systematic review and bibliometric analysis of remote sensing and geospatial methods for building energy efficiency (see `review/README.md`) |

All scripts use snake_case file names.

## Data

No input or derived building-level data are stored in this repository. See [DATA.md](DATA.md) for the data sources and their terms of use.

## Licence and ownership

Copyright © Ulster University. Released under the [Apache License 2.0](LICENSE); see [NOTICE](NOTICE). Third-party data remain subject to their own licences.

## Citation

Please cite this software using the metadata in [CITATION.cff](CITATION.cff) (GitHub: "Cite this repository").
