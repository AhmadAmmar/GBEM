# Earth Engine composites (Greater London, Greater Belfast)

`gbem_composites.js` (version 2.1.0) builds the satellite and climate composites for the two study areas in Google
Earth Engine and exports them to Google Drive as GeoTIFFs. Earth Engine is used only for the steps that need the full
archives: cloud masking and reduction over time. Everything else is done locally in Python from the exported rasters:
- spectral and SAR indices;
- terrain derivatives;
- the surface urban heat island;
- wind speed and direction;
- the values for each building (at the point, in a buffer, or over the footprint).

This keeps Earth Engine compute low. It also means the per-building extraction can be repeated, for example with a
different buffer or between point and footprint values, without running Earth Engine again, and that no
property-level EPC data is uploaded to Earth Engine.

## Products

All time windows of a product are bands of one image per area and year.

| Product | Source | Resolution | Bands (per window) | Stored as |
|---|---|---|---|---|
| `s2` | Sentinel-2 L2A (`COPERNICUS/S2_SR_HARMONIZED`), Cloud Score+ masked (cs_cdf >= 0.60) | 10 m | B2, B3, B4, B5, B6, B7, B8, B8A, B11, B12 median; `n` | int16, reflectance x 10000 |
| `s1` | Sentinel-1 GRD IW, VV+VH, both orbits | 10 m | VV, VH median (dB); angle mean; `n` | int16, dB x 100 |
| `landsat` | Landsat 8 and 9 Collection 2 L2, QA_PIXEL masked | 30 m | `LST` median (deg C); `n` | int16, deg C x 100 |
| `modis` | MOD11A1 (Terra) and MYD11A1 (Aqua), QC masked (produced, error <= 2 K) | 1 km | terra/aqua day/night LST median (deg C); counts | int16, deg C x 100 |
| `era5` | ERA5-Land daily aggregates | 1 km grid (native 0.1 deg) | t2m, d2m, daily max/min, u10, v10, precip_mm, ssrd_MJm2, HDD (15.5 deg C), CDD (22 deg C) | float32 |
| `viirs` | VIIRS DNB monthly (VCMSLCFG), months with cloud-free coverage | 500 m | avg_rad median; `n` | float32 |
| `static` | ESA WorldCover v200 (2021); Copernicus DEM GLO-30 (2024 release); GHSL building height 2018 and built volume 2020 | 10, 30, 100 m | class; elevation; height, volume | int16 / float32 |

The time windows are:
- `annual`: January to December;
- `summer`: June to August;
- `winter`: December of the previous year to February;
- event windows, set in `CONFIG.events`: `heat2022` (10–25 July 2022, including the record heat of 18–19 July) and
  `cold2022` (5–19 December 2022).

Event windows are added to the thermal and climate products of their year.

Missing values are -32768 for the integer products and -9999 for the float products. To get physical values, divide
the stored value by the scale.

## Extents and grids

| Area | Grid | `core` (10 m products) | `context` (coarse products, rural reference) |
|---|---|---|---|
| Greater London | EPSG:27700 | Greater London Authority boundary + 1 km | + 10 km |
| Greater Belfast | EPSG:29902 | Belfast City Council area + 8 km (Lisburn, Castlereagh, Newtownabbey, Holywood, Carrickfergus) | + 15 km |

The extents are snapped to 3 km, so the rasters of all resolutions nest exactly. They are computed by `extents.py`.

## Running

1. Paste `gbem_composites.js` into the Earth Engine Code Editor and press **Run**. With `CONFIG.dryRun = true`, the
   console lists the planned images with an upper bound on their size and the number of input scenes for each window.
   Preview layers are added to the map.
2. Choose the batch with `BATCH` (see the table below). Set `dryRun: false`, press **Run**, and start the tasks in the
   **Tasks** tab.
3. Each batch also exports a provenance table: the number of input scenes per area, product, year and window.

## Batches and versions

| Batch | Years | Products | Drive folder | Images | Size before compression |
|---|---|---|---|---|---|
| `b1` | 2024 | static and yearly | `GBEM_GEE_v2` | 18 | at most 2.5 GB (exported 21 Oct 2026) |
| `b2` | 2020, 2021 | yearly | `GBEM_GEE_v2_b2` | 24 | at most 4.8 GB |
| `b3` | 2022, 2023 | yearly, plus the 2022 heatwave and cold-spell windows | `GBEM_GEE_v2_b3` | 24 | at most 4.9 GB |
| `b4` | 2025 | yearly | `GBEM_GEE_v2_b4` | 12 | at most 2.4 GB |

The 2024 batch came first, to reproduce the 2024 samples used so far before other years were added. Each batch has its
own folder, so one batch can be downloaded and cleared from Drive before the next is run.

The two version numbers mean different things:
- The **method version** (`CONFIG.version`, currently `v2_0_1`) is part of every file name. It changes only when a
  composite is defined differently, so files with the same method version can be combined across years.
- The **script version** in the header (currently 2.1.0) also changes for changes that do not affect the outputs, such
  as the batch presets.

## Data availability by year

Landsat 9 data start in late 2021. Land surface temperature for 2020 and most of 2021 therefore comes from Landsat 8
alone, with about half the scenes of later years. The per-pixel count band `n` records this. All other sources cover
2020–2025 for both areas (`check_sources.py`, 21 Oct 2026). One exception: no Landsat scene covers Greater Belfast in
the December 2022 cold-spell window, so that band is empty.

## Earlier extractions

The earlier Earth Engine extractions sampled the composites at each building in Earth Engine. Their outputs are, for
example, `data/belfast/gee/Belfast_2024_point_samples*.csv` and `data/london/london_samples_indices_2024.csv`. The
variables listed below from those files can all be computed locally from the new exports (the local extraction
step is still to be written):
- DEM terrain;
- ERA5 temperature, precipitation and wind;
- Landsat and MODIS LST and sUHI;
- Sentinel-1 backscatter and ratios;
- the Sentinel-2 indices (NDVI, NDBI, NDWI, NDMI, EVI, SAVI, MSAVI2, BSI, UI, IBI, NDRE, NIRv, albedo);
- VIIRS radiance;
- WorldCover built-up share.

Two of these are not carried over (see the reproduction check below):
- The earlier **UI** was B11/B8, which carries the same information as NDBI. The new UI is (B12−B8)/(B12+B8).
- **IBI** is not derived, because its denominator can be close to zero.

Albedo is pending a sourced Sentinel-2 formula.

## Local processing (Python, `eo` environment)

Every step reads the output of the step before and writes to its own folder. The raw exports are never changed.
`spec.py` holds the grids, products, band names and scale factors for all steps; it checks that the extents equal
those in the Earth Engine script.

| Step | Code | Output |
|---|---|---|
| 1. Ingest | `ingest.py <batch> <zips>` | Extracts the files to `data/<area>/gee_v2/raw/` (zips kept). Checks grid, band names, data type, missing values and plausible ranges at full resolution. Writes `data/gee_v2/manifest.csv` (with checksums) and `data/gee_v2/qa/ingest_<batch>.csv` |
| 2. Preprocess | `preprocess.py --years ...` | `derived/`: terrain (DEM below −5 m masked), WorldCover shares at 100 m, ERA5 wind speed and direction, rural reference temperatures for the surface urban heat island |
| 3. Extract | `extract.py --area --year --buildings --id [--lon --lat \| --points] --tag` | `features/<tag>_<year>.parquet/.csv`, one row per certificate (details below) |
| 4. Reproduction check | `compare_old.py --area --new --old --id` | `features/compare_old_<area>.csv`: agreement with the earlier samples |
| 5. Maps and visual QA | `../qgis/load_gee_layers.py`, `../qgis/s1_maps.py` (inside QGIS) | `data/<area>/gee_v2/<area>_gee_v2_<year>.qgz`, `qa/quicklooks/*.png`, A4 maps in `Maps/gee_v2/` |

What `extract.py` produces for each certificate:
- **Point value:** at the certificate's coordinates.
- **Footprint mean:** over pixels whose centre lies in the building footprint. Identical footprints, such as flats in
  one building, are rasterised once.
- **Neighbourhood mean:** over about 100 m.

How the values are computed:
- Sentinel-2 indices are computed per pixel and then averaged.
- Sentinel-1 is averaged in linear power and then converted to dB.
- MODIS, ERA5, VIIRS, GHSL, land cover and terrain get point values only.
- Landsat gets point and neighbourhood values only.

### Results for 2024 (21 October 2026)

| | Greater London | Greater Belfast |
|---|---|---|
| Certificates / unique footprints | 109,955 / 67,726 | 6,685 / 5,970 |
| Features per certificate | 270 | 270 |
| Footprints without a 10 m pixel centre (footprint value = point value) | 18% | 45% |
| Missing: Landsat LST summer / winter | 0% / 27.6% | 15.8% / 14.4% |
| Missing: MODIS night LST winter | 0.2% | 0.5% |

Annual Landsat LST and winter MODIS night LST are complete in both areas, so they are the dependable thermal
features. Seasonal Landsat values have gaps where no clear scene exists.

### Reproduction of the earlier 2024 samples

The table shows the Spearman correlation of the point values, on the same certificates.

| Variables | Belfast | London |
|---|---|---|
| Sentinel-1 VV, VH, VV−VH | 0.96–0.97 | 0.78 |
| Elevation; VIIRS | 0.99; 0.95 | – |
| NDVI, NDWI, EVI, NIRv, GNDVI | 0.89–0.90 | 0.80–0.85 |
| Sentinel-2 bands | – | 0.70–0.80 |
| NDBI, BSI, Landsat LST | 0.69–0.71 | 0.61; 0.56 |
| ERA5 temperature and wind | 0.88 | – |
| Slope and aspect; MODIS night LST | 0.39–0.54; 0.44 | – |

In both areas, point values match better than footprint or neighbourhood means, so the earlier scripts sampled at
the certificate points. The earlier formulas for NDBI, NDWI and EVI are identical to the new ones.

The earlier scripts are not available, so their composite windows and cloud masking are not known. Differences in
these probably explain the lower agreement for the optical and thermal variables. The lower agreement for slope and
aspect is consistent with a different DEM or resolution.
