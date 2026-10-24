"""IFC (BIM) version of a CityJSON district from export_cityjson.py: one IfcBuilding per building, its footprint extruded
to its height, georeferenced, with the energy attributes as a property set, for BIM tools (Bonsai / Blender, FreeCAD).

    python cityjson_to_ifc.py <district>.city.json [--out <file>.ifc] [--schema IFC4]

Run with the GeoBIM environment (IfcOpenShell is not installed in the analysis environment):
    C:/Users/Owner/dev/.venv-geobim/Scripts/python.exe code/geo/cityjson_to_ifc.py data/belfast/geobim/<district>.city.json

Structure: IfcProject > IfcSite > IfcBuilding (one per CityJSON Building). Geometry: IfcExtrudedAreaSolid of the ground
outline (IfcArbitraryClosedProfileDef, or ...WithVoids for courtyards) from the ground height to the roof height, in metres,
in local coordinates of the site; the site is placed in the national grid with IfcMapConversion and IfcProjectedCRS
(EPSG:27700 or EPSG:29902). Properties: Pset_BuildingCommon (NumberOfStoreys) and Pset_GBEM_Energy
(every energy_* and gbem_* attribute, plus measuredHeight). The output sits beside the input (building-level estimates:
internal, never committed or published).
"""
import argparse, json, pathlib, re
import numpy as np
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.root, ifcopenshell.api.context, ifcopenshell.api.aggregate, ifcopenshell.api.unit
import ifcopenshell.api.geometry, ifcopenshell.api.pset, ifcopenshell.api.georeference


def outline(ground_rings, v):
    """ground surface rings (stored downward-facing) as counter-clockwise exterior and clockwise holes, in metres"""
    rings = [v[list(reversed(r))][:, :2] for r in ground_rings]
    return rings[0], rings[1:]


def profile(model, ext, holes, origin):
    pts = lambda r: model.createIfcCartesianPointList2D([tuple(map(float, p - origin)) for p in np.vstack([r, r[:1]])])
    curve = lambda r: model.createIfcIndexedPolyCurve(pts(r), None, False)
    if holes:
        return model.createIfcArbitraryProfileDefWithVoids("AREA", None, curve(ext), [curve(h) for h in holes])
    return model.createIfcArbitraryClosedProfileDef("AREA", None, curve(ext))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cityjson"); ap.add_argument("--out"); ap.add_argument("--schema", default="IFC4")
    a = ap.parse_args()
    src = pathlib.Path(a.cityjson)
    cj = json.loads(src.read_text(encoding="utf-8"))
    s, t = np.array(cj["transform"]["scale"]), np.array(cj["transform"]["translate"])
    v = np.array(cj["vertices"]) * s + t
    origin = t.copy()                                                  # local origin of the site = CityJSON translate
    epsg = re.search(r"EPSG/0/(\d+)", cj["metadata"]["referenceSystem"]).group(1)

    model = ifcopenshell.file(schema=a.schema)
    project = ifcopenshell.api.root.create_entity(model, ifc_class="IfcProject", name=cj["metadata"].get("title", "GBEM district"))
    units = [ifcopenshell.api.unit.add_si_unit(model, unit_type=u) for u in ("LENGTHUNIT", "AREAUNIT", "VOLUMEUNIT")]
    ifcopenshell.api.unit.assign_unit(model, units=units)              # metres, square metres, cubic metres (not mm)
    ctx = ifcopenshell.api.context.add_context(model, context_type="Model")
    body = ifcopenshell.api.context.add_context(model, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    ifcopenshell.api.georeference.add_georeferencing(model)
    ifcopenshell.api.georeference.edit_georeferencing(model, projected_crs={"Name": f"EPSG:{epsg}"},
                                                     coordinate_operation={"Eastings": float(origin[0]), "Northings": float(origin[1]),
                                                                           "OrthogonalHeight": float(origin[2])})
    site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name=cj["metadata"].get("identifier", src.stem))
    ifcopenshell.api.aggregate.assign_object(model, relating_object=project, products=[site])
    ifcopenshell.api.geometry.edit_object_placement(model, product=site)

    n = 0
    for oid, o in cj["CityObjects"].items():
        if o.get("type") != "Building" or not o.get("geometry"):
            continue
        g = o["geometry"][0]
        shells = [g["boundaries"]] if g["type"] == "Solid" else g["boundaries"]
        att = o.get("attributes", {})
        b = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuilding", name=att.get("gbem_footprintId", oid))
        ifcopenshell.api.aggregate.assign_object(model, relating_object=site, products=[b])
        items = []
        for sh in shells:
            ground = sh[0][0]                                         # first surface of the shell is the ground
            ext, holes = outline(ground, v)
            z0 = float(v[ground[0][0], 2]); z1 = float(v[sh[0][1][0][0], 2])
            base = ext.min(0)
            prof = profile(model, ext, holes, base)
            pos = model.createIfcAxis2Placement3D(model.createIfcCartesianPoint(
                (float(base[0] - origin[0]), float(base[1] - origin[1]), float(z0 - origin[2]))), None, None)
            items.append(model.createIfcExtrudedAreaSolid(prof, pos, model.createIfcDirection((0.0, 0.0, 1.0)), max(z1 - z0, 0.5)))
        rep = model.createIfcShapeRepresentation(body, "Body", "SweptSolid", items)
        ifcopenshell.api.geometry.assign_representation(model, product=b, representation=rep)
        ifcopenshell.api.geometry.edit_object_placement(model, product=b)
        if "storeysAboveGround" in att:
            common = ifcopenshell.api.pset.add_pset(model, product=b, name="Pset_BuildingCommon")
            ifcopenshell.api.pset.edit_pset(model, pset=common, properties={"NumberOfStoreys": int(att["storeysAboveGround"])})
        energy = ifcopenshell.api.pset.add_pset(model, product=b, name="Pset_GBEM_Energy")
        ifcopenshell.api.pset.edit_pset(model, pset=energy, properties={k: att[k] for k in att
                                                                         if k.startswith(("energy_", "gbem_")) or k == "measuredHeight"})
        n += 1
    out = pathlib.Path(a.out) if a.out else src.with_name(src.name.replace(".city.json", ".ifc"))
    if out.exists():
        out = out.with_name(out.stem + "_new" + out.suffix)           # never overwrite an earlier file
    model.write(str(out))
    print(f"{n:,} buildings -> {out} ({a.schema}, EPSG:{epsg})")


if __name__ == "__main__":
    main()
