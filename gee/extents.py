"""Export extents for gbem_composites.js, from the local study-area boundaries.

    python extents.py

Each boundary is buffered ('core' and 'context' distances), projected to the area's grid and snapped outwards to
3 km, the least common multiple of the export resolutions (10, 30, 100, 500 and 1000 m), so that all rasters of an
area nest exactly. Paste the printed lines into AREAS in gbem_composites.js.
"""
import math, pathlib
import geopandas as gpd

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"
AREAS = {   # boundary, grid, core buffer (m), context buffer (m)
    "london": (DATA / "london/SHP/london.shp", 27700, 1000, 10000),               # Greater London Authority boundary
    "belfast": (DATA / "belfast/belfast-dissolved/belfast-dissolved.shp", 29902, 8000, 15000),   # Belfast City Council area
}
SNAP = 3000


def snap(b, m=SNAP):
    return [math.floor(b[0] / m) * m, math.floor(b[1] / m) * m, math.ceil(b[2] / m) * m, math.ceil(b[3] / m) * m]


if __name__ == "__main__":
    for name, (path, epsg, core, ctx) in AREAS.items():
        b = gpd.read_file(path).to_crs(epsg).total_bounds
        c = snap([b[0] - core, b[1] - core, b[2] + core, b[3] + core])
        x = snap([b[0] - ctx, b[1] - ctx, b[2] + ctx, b[3] + ctx])
        print(f"  {name}: {{crs: 'EPSG:{epsg}', core: {c}, context: {x}}}")
