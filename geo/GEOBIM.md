# GeoBIM: the project's estimates as 3D city models (CityJSON) and BIM (IFC)

Two scripts take a district out of the GIS pipeline into the formats of 3D city models and BIM:

| Script | Environment | Output (in `data/<area>/geobim/`) |
|---|---|---|
| `geo/export_cityjson.py` | analysis (`eo`) | `<district>.city.json` (CityJSON 2.0, LoD1.2), `<district>_metadata.json`, `<district>_preview.png` |
| `geo/cityjson_to_ifc.py` | GeoBIM (`C:\Users\Owner\dev\.venv-geobim`: IfcOpenShell, cjio) | `<district>.ifc` (IFC4, georeferenced) |

```
python code/geo/export_cityjson.py --area belfast --name WOODSTOCK --preview
python code/geo/export_cityjson.py --area london --nbhd E01035716 --preview
C:/Users/Owner/dev/.venv-geobim/Scripts/python.exe code/geo/cityjson_to_ifc.py data/belfast/geobim/N08000359_WOODSTOCK.city.json
C:/Users/Owner/tools/val3dity/bin/val3dity.exe data/belfast/geobim/N08000359_WOODSTOCK.city.json
```
A district is a neighbourhood (`--nbhd` code or `--name`; LSOA 2021 in London, wards in Belfast) or a box in the
national grid (`--bbox x0 y0 x1 y1`); without one, the neighbourhood with the most dwellings is taken.

**What is in the model.** Each dwelling building (footprint with at least one address) is a Solid: its footprint
extruded from the ground (Copernicus DEM) to the LiDAR median height (LoD1.2), with ground, roof and wall surfaces. Its
attributes are the predicted SAP score and band, P(F or G), whether it holds a certificate, dwellings, storeys, floor
area, heated volume, envelope, exterior and party walls, roof area, heat-loss form factor, and LiDAR roof slope and
aspect. Names follow CityGML (`function`, `measuredHeight`, `storeysAboveGround`) and the CityGML Energy ADE 1.0
(`energy_floorArea`, `energy_heatedVolume`, ...); model outputs end in `Predicted`. In IFC the same values are the
property set `Pset_GBEM_Energy` of each `IfcBuilding`, and the site is placed in the national grid (`IfcMapConversion`).

**Checks (24 October 2026).** Woodstock (Belfast, 3,054 buildings) and Westminster 013G (London, 1,092): 100% valid
solids in val3dity; IFC4 schema valid (IfcOpenShell); IFC volumes equal to the CityJSON volumes (sample of 25,
difference below 0.001%).

**Data protection.** The files hold building-level estimates: keep them internal (as `data/`), use them for figures and
demonstrations, never publish them. For public use, export aggregates or a synthetic district.

## Tools to open them (open source first; all with a graphical interface)

### 3D city models (CityJSON)
1. **ninja**, the CityJSON web viewer: https://ninja.cityjson.org (open source; the file is read in the browser).
   Drag the `.city.json` in, click a building to see its attributes. The quickest look.
2. **QGIS** with the **CityJSON Loader** plugin (Plugins > Manage and Install Plugins): loads buildings with their
   attributes as layers; style by `energy_epcRatingPredicted` and show them in a 3D map view (View > 3D Map Views),
   extruded by `measuredHeight`. Best for combining with the project's other GIS layers.
3. **Blender** with the **Up3date** add-on: imports CityJSON for renders and figures.
4. **cjio** (command line, installed in `.venv-geobim`): `cjio file.city.json info`, subset, reproject, export to glTF
   or OBJ for web viewers (CesiumJS, three.js).
5. **3DCityDB** (open source, PostgreSQL/PostGIS) with its importer/exporter and web map client: a database for many
   districts or whole cities; supports the CityGML Energy ADE. Heavier to set up; for a digital-twin demonstration.
6. **citygml-tools** (open source, from the 3DCityDB team): converts CityJSON to CityGML, the input of urban building
   energy modelling tools such as **SimStadt** (free for research) and **CitySim**.
7. Validation: **val3dity** (installed: `C:\Users\Owner\tools\val3dity\bin\val3dity.exe`) and the web validator
   https://validator.cityjson.org.

### BIM (IFC)
1. **Bonsai** (formerly BlenderBIM), free and open source, an add-on for Blender (https://bonsaibim.org): opens the
   `.ifc`, shows each building's property sets and the georeferencing; full IFC authoring.
2. **FreeCAD** 1.0 with the BIM workbench (open source, https://www.freecad.org): opens IFC through IfcOpenShell.
3. **IfcOpenShell** (Python, installed in `.venv-geobim`) and **IfcConvert** (IFC to glTF/OBJ/STEP).
4. Free viewers (not open source), for a quick look: Open IFC Viewer, BIMvision.

Suggested order: ninja (two minutes) > QGIS 3D view with the project's layers > Bonsai for the IFC side.
