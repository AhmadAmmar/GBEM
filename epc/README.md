# Certificates, footprints and morphology (objective 2)

These scripts build one documented table per study area, with every domestic Energy Performance Certificate
(EPC) linked to its property (UPRN) and building footprint. They also compute building morphology. The satellite
features (`code/gee/extract.py --certificates`) and the models use these tables.

Run the steps in order, in the conda environment `eo`, from this folder.

| Step | Code | Output in `data/<area>/epc/` |
|---|---|---|
| 1 | `certificates.py` | `certificates.parquet`, `certificates_log.json` |
| 2 | `footprints.py` | `footprints.parquet`, `footprints_log.json` |
| 3 | `link.py` | `certificates_linked.parquet`, `link_log.json` |
| 4 | `morphology.py` | `morphology.parquet`, `morphology_log.json` |
| 4b | `dwellings.py` | `dwellings_fp.parquet` (UPRNs and area per UPRN per footprint), `dwellings_cert.parquet` (position of the property in its block) |
| 5 | `assemble.py` | `data/<area>/model/dataset_<year>.parquet`, `data_dictionary.csv` (feature groups for ablations) |

**No output is ever overwritten.** Before a script writes a file, an existing file of the same name is moved to
`_archive/<run time>/` in the same folder (`code/safeio.py`). Original data (registers, downloads, raw exports) is
only read.

## Sources

| | Greater London | Greater Belfast |
|---|---|---|
| Certificates | England and Wales domestic register, files dated 13 October 2026 (`domestic-csv.zip`, 2008–2026); the 33 London local authorities; coordinates from OS Open UPRN 2025-07 (the January 2025 snapshot can be rebuilt with `--source ew2025`) | Northern Ireland domestic register to January 2025, with Irish Grid coordinates from the UPRN |
| Coordinates | OS Open UPRN location of the certificate's UPRN (in a sample of 45,000, 99.2% within 1 m) | UPRN location (OSNI pointer) |
| Footprints | Overture Maps buildings, release 2026-09-23.1 (OpenStreetMap, plus Microsoft machine-learned footprints) | OSNI building footprints inside Belfast City Council area; Overture outside it |
| Roads | OpenStreetMap, Geofabrik extract 2026-10-20 | OpenStreetMap, Geofabrik extract 2026-10-20 |

**Why Overture and not OpenStreetMap alone.** With OpenStreetMap footprints, 21% of London UPRNs had no building,
rising to 70% in Harrow and 67% in Hillingdon. The missing buildings are typically 64 m away, so the buildings are
absent from the map rather than offset. That would bias the sample towards inner London. With Overture, the
unlinked share is 4.1% (Harrow and Hillingdon about 20%). In Belfast it is 0.6%.

## Rules for the certificates (`certificates.py`)

**Dropped**, and counted in the log:
- a repeated certificate id (identical copies; 1,298 in the Northern Ireland file, none in London);
- the rating is not A–G (17 in London);
- there is no location;
- the inspection date is missing or before 2007 (207 in London);
- for Belfast, the location is outside the Greater Belfast extent.

**Kept, with flags.** These choices are made when the modelling sets are drawn:
- `year`: year of the inspection date, i.e. when the dwelling was assessed. It is used to match imagery years.
- `new_dwelling`: transaction type "new dwelling". New dwellings are rated with full SAP; existing dwellings with
  RdSAP.
- `uprn_source`: how the UPRN was matched. London: Address Matched or Energy Assessor. Belfast: which UPRN list
  supplied the coordinates.
- `n_certs_uprn`, `cert_order` and `is_latest`: repeat certificates of the same property.
- `certs_same_day`: more than one certificate of the property on the same day (possible duplicates).
- `sap_score`: the continuous SAP rating, to model next to the A–G bands.

**For the models:**
- Cross-validation must keep all certificates of a property, and of a building, in the same fold.
- Certificates before 2020 have no imagery year of their own. Northern Ireland certificates before 2020 have no
  UPRN, and therefore no location.

## Counts (21 October 2026)

| | Greater London | Greater Belfast |
|---|---|---|
| Certificates / properties (UPRN) | 4,444,008 / 2,890,924 | 57,567 / 54,591 |
| Years | 2007–2026 (2026 to mid-October) | 2020–January 2025 |
| Footprints | 2,141,314 (956,508 with height) | 417,229 (190,709 OSNI) |
| UPRNs inside a footprint / nearest within 5 m / unlinked | 89.5% / 6.0% / 4.6% | 98.8% / 0.6% / 0.6% |

## Modelling tables (21–22 October 2026)

One table per area and imagery year in `data/<area>/model/`, one row per certificate inspected that year. There are
about 760 columns (834 in 2022, which has the heatwave and cold-spell windows), with feature groups listed in
`data_dictionary.csv`. No certificate id is repeated.

| Year | London | Belfast |
|---|---|---|
| 2020 | 238,566 | 4,362 |
| 2021 | 253,423 | 12,802 |
| 2022 | 271,005 | 13,272 |
| 2023 | 248,615 | 12,851 |
| 2024 | 248,544 | 13,301 |
| 2025 | 241,262 | 963 (register ends January 2025) |

The multi-year thermal features (`thermal_multiyear`) are complete for every certificate. Single-year Landsat winter
LST is missing for up to 30% (London 2024).

## Morphology (`morphology.py`)

For each footprint:
- **Shape:** area, perimeter, compactness, convexity, elongation, orientation, number of vertices.
- **Adjacency:** shared-wall length and share (0.5 m tolerance), number of adjacent buildings, distance to the
  nearest building.
- **Surroundings at 100 m and 250 m:** building coverage, count and mean footprint area.
- **Streets:** distance to the nearest road open to motor vehicles and to the nearest major road; road density
  within 250 m.
- **Building attributes:** height, number of floors and volume (Overture, where given); dwelling type (OSNI,
  Belfast).

**Check against the certificates' built form (Belfast).** The median shared-wall share is 0 for detached houses,
about 0.30 for semi-detached and end-terrace houses, and 0.55 for mid-terraces. "Enclosed" terraces are near 0.
These are probably mapped as one block with their neighbours, so they need a closer look.

## Footprints that cover several dwellings (London)

In London, terrace rows and semi-detached pairs are often mapped as one polygon:
- 31% of houses lie in a footprint with more than two UPRNs;
- Microsoft machine-learned footprints never separate houses.

For those houses, footprint shape and shared walls describe the block, not the dwelling. `dwellings.py` adds
measures that hold for blocks:
- the number of UPRNs in the footprint (median 1 detached, 2 semi-detached, 3–4 terraced);
- the footprint area per UPRN;
- the position of the property along the block (`pos_in_block`). In blocks of three or more UPRNs, end-terraces have a
  median of 0.76 and mid-terraces 0.34.

The proper fix is to divide blocks into plots with HM Land Registry INSPIRE Index Polygons. That needs acceptance of
the Land Registry licence terms.

## Still needed

- **A refresh of the England and Wales register to 2026.** It needs the user's EPC data account; the current
  snapshot ends in January 2025.
- **London heights for the 55% of buildings without one,** from Environment Agency LiDAR or OS MasterMap Building
  Height (Digimap).
