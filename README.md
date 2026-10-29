# GBEM: Geospatial Building Energy Mapping

Code for estimating and mapping the energy efficiency of buildings from Earth observation and geospatial data, developed as part of a PhD project in the School of Geography and Environmental Sciences, Ulster University.

## Contents

| Folder | Contents |
|---|---|
| `scripts/data_processing` | Data preparation: EPC certificates, UPRN and coordinate linkage, OpenStreetMap buildings, Google Earth Engine extraction, spectral indices, zonal statistics |
| `scripts/ml` | Machine learning experiments for EPC rating and efficiency-class prediction |
| `scripts/visualization` | Figure and map scripts |
| `scripts/utils` | Helper utilities (for example `inspect_dataset.py` for row counts, columns and metadata) |
| `review/` | Review and bibliometric analysis pipeline (see `review/README.md`) |
| `tools/` | Repository utilities (`make_inventory.py`) |

All scripts use snake_case file names; each script's docstring describes its inputs, outputs and arguments.

## Data

No input or derived building-level data are stored in this repository. See [DATA.md](DATA.md) for the data sources and their terms of use.

## Atlas

The public GBEM Atlas (Greater London and Greater Belfast; aggregates of at least 10 certificates per unit, no
building-level data) is at https://ahmadammar.github.io/GBEM/. It is built with `viz/atlas.py --public` and served
from the `gh-pages` branch.

## Funding and acknowledgements

This work is part of a PhD project funded by a Vice-Chancellor's Research Scholarship (VCRS) from Ulster University,
supervised by Dr Saad Bhatti and Dr Paul McKenzie (Ulster University) and Dr Muhammad Irfan (external supervisor).

## Licence and ownership

Copyright © Ulster University: intellectual property arising from research degrees belongs to the University under its
Intellectual Property Policy. Released under the [Apache License 2.0](LICENSE); see [NOTICE](NOTICE). Third-party data
remain subject to their own licences.

## Citation

Please cite this software using the metadata in [CITATION.cff](CITATION.cff) (GitHub: "Cite this repository").
