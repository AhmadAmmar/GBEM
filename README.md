# GBEM Atlas (public)

Interactive atlas of domestic energy performance in Greater London and Greater Belfast: grid cells, neighbourhoods
(LSOA 2021 in London, wards in Belfast), streets and urban form types, with rankings, trends, retrofit needs and model
results.

Open it at https://ahmadammar.github.io/GBEM/

- Built with `viz/atlas.py --public` from the main branch of this repository.
- Aggregates only: every grid cell, neighbourhood and street shown has at least 10 certificates. There is no
  building-level layer and no address data; in Belfast, streets are drawn as whole OpenStreetMap lines.
- For research and communication. It is not a source of information about individual homes.

## Credits

Developed by Ahmad Ammar as part of a PhD project in the School of Geography and Environmental Sciences, Ulster
University, supervised by Dr Saad Bhatti, Dr Paul McKenzie and Dr Muhammad Irfan. Funded by a Vice-Chancellor's
Research Scholarship (VCRS), Ulster University. © Ulster University.

Cite as: Ammar, A., Bhatti, S., McKenzie, P. and Irfan, M. (2026) *GBEM Atlas: energy performance of the housing stock
in Greater London and Greater Belfast*. Ulster University. https://ahmadammar.github.io/GBEM/

## Data

- England and Wales: Energy Performance Certificates (MHCLG), OS Open UPRN, LSOA 2021 boundaries (ONS), English
  Indices of Deprivation (MHCLG), sub-national energy consumption (DESNZ). Contains public sector information licensed
  under the Open Government Licence v3.0. Contains OS data © Crown copyright and database right 2025.
- Northern Ireland: Energy Performance Certificates provided by the Department of Finance (NI) under the Environmental
  Information Regulations (DOF/2026-0254). Contains LPS Intellectual Property © Crown copyright and database right 2025
  (address data used only to place certificates). Ward boundaries (OSNI), Census 2021 and NIMDM (NISRA), Open
  Government Licence.
- Streets © OpenStreetMap contributors (ODbL); building footprints © Overture Maps Foundation; LiDAR: Environment
  Agency and OpenDataNI (OGL); Copernicus Sentinel data (ESA); Landsat and MODIS (NASA, USGS); ERA5-Land (Copernicus
  Climate Change Service); VIIRS (NOAA); GHSL (European Commission JRC); ESA WorldCover; satellite embeddings (Google,
  CC BY 4.0). Basemap © Esri, HERE, Garmin, © OpenStreetMap contributors.
