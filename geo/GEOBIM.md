# CityJSON and IFC export

- `export_cityjson.py`: writes area-level building models as CityJSON 2.0 (LoD1.2) with energy attributes.
- `cityjson_to_ifc.py`: converts the CityJSON to georeferenced IFC4 (needs IfcOpenShell and cjio).

    python geo/export_cityjson.py --area belfast --name WOODSTOCK --preview
    python geo/cityjson_to_ifc.py <input.city.json>

The files open in open-source viewers such as ninja (CityJSON) and BlenderBIM / Bonsai (IFC).
