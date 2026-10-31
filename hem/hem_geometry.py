"""Surface accounting for a HEM input file, in one tested place.

HEM marks internal partitions and party surfaces alike as BuildingElementAdjacentConditionedSpace, so the type alone cannot
separate them: internal partitions are inside the dwelling and are not part of its airtightness envelope.
"""


def surface_areas(hem):
    """Areas in m2: exposed (heat-loss) surfaces, party surfaces, entrance doors and internal partitions."""
    out = dict(exposed=0.0, party=0.0, door=0.0, internal=0.0)
    for zone in hem["Zone"].values():
        for name, el in zone["BuildingElement"].items():
            area = el.get("area") or el.get("height", 0) * el.get("width", 0)
            if "Adjacent" not in el["type"]:
                out["exposed"] += area
            elif "party" in name.lower():
                out["party"] += area
            elif "entr" in name.lower():
                out["door"] += area
            else:
                out["internal"] += area
    return out


def envelope_area(hem):
    """Airtightness envelope: everything between the dwelling and outside or a neighbour, excluding internal partitions."""
    a = surface_areas(hem)
    return a["exposed"] + a["party"] + a["door"]


def floor_area(hem):
    return sum(z["area"] for z in hem["Zone"].values())


def volume(hem):
    return sum(z["volume"] for z in hem["Zone"].values())
