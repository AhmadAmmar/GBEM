# Earth Engine composites (Greater London, Greater Belfast)

`gbem_composites.js` (version 2.0.1) builds the satellite and climate composites for the two study areas in Google
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
2. Choose the batch with `CONFIG.areas`, `CONFIG.years` and `CONFIG.products`. Set `dryRun: false`, press **Run**, and
   start the tasks in the **Tasks** tab.
3. Each batch also exports a provenance table: the number of input scenes per area, product, year and window.

The first batch is 2024 for both areas (18 images plus the provenance table). It reproduces the 2024 samples used so
far before more years are added. The 2024 batch is at most about 2.5 GB before compression; the 10 m Sentinel-2
composites make up most of it. Check the free space on Google Drive before running several years.

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
