"""3D city model of a district with the project's energy estimates: CityJSON 2.0, LoD1.2 buildings (footprint extruded to
the LiDAR height, on the terrain), for GeoBIM, urban energy modelling and digital-twin tools.

    python export_cityjson.py --area belfast [--nbhd <ward or LSOA code> | --name <part of the name> | --bbox x0 y0 x1 y1]
                              [--year 2024] [--max-buildings 5000] [--preview]

Inputs (data/<area>/):
  epc/footprints.parquet             building footprints (national grid: EPSG:27700 London, EPSG:29902 Belfast)
  epc/lidar_fp.parquet               LiDAR height (median and 90th percentile above ground), roof slope and aspect
  epc/physics_fp.parquet             storeys, floor area, volume, exposed and party walls, roof, heat-loss form factor
  epc/dwellings_fp.parquet           addresses (dwellings) per footprint
  model/stock/stock_pred_<year>.parquet  predicted SAP score, band, P(F or G), confidence, certified (models/stock_predict.py)
  analysis/geometry_nbhd.parquet     neighbourhoods (LSOA 2021 London, wards Belfast), to select a district
  gee_v2/raw/*_dem_30m.tif           Copernicus DEM, for the ground height of each building
Default district: the neighbourhood with the most predicted dwellings.

Geometry: one Solid per footprint polygon (MultiSolid for multi-part footprints), LoD 1.2, with semantic surfaces
(GroundSurface, RoofSurface, WallSurface) and outward-facing rings. Height: LiDAR median height (lidar_height_med_m); else
the footprint's own height; else storeys x 3 m; else 6 m (attribute gbem_heightSource says which).

Attributes follow CityGML 2.0 / 3.0 names where they exist (function, measuredHeight, storeysAboveGround) and the names of
the CityGML Energy ADE 1.0 for the energy data, prefixed energy_ (for example energy_floorArea, energy_heatedVolume,
energy_epcRating). Model outputs are marked as predictions (energy_epcRatingPredicted, energy_sapScorePredicted).

Outputs in data/<area>/geobim/ (building-level estimates: internal, never committed or published):
  <district>.city.json               the CityJSON file (validate: val3dity, or https://validator.cityjson.org)
  <district>_metadata.json           district, inputs, model and its spatial cross-validation error, attribute notes
  <district>_preview.png             with --preview: 3D view coloured by predicted band
Predictions carry the model error; they describe areas, not individual homes.
"""
import argparse, datetime, json, pathlib, re, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from shapely.geometry import Polygon, MultiPolygon
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

CODE = pathlib.Path(__file__).resolve().parents[1]
DATA = CODE.parent / "data"
EPSG = {"london": 27700, "belfast": 29902}
BANDS = "ABCDEFG"
BAND_COLOURS = {"A": "#008054", "B": "#19b459", "C": "#8dce46", "D": "#ffd500", "E": "#fcaa65", "F": "#ef8023", "G": "#e9153b"}
SCALE = 0.001                                 # CityJSON vertices stored in millimetres


def district(area, a):
    """footprints of the chosen district, with the district's name"""
    nb = gpd.read_parquet(DATA / area / "analysis/geometry_nbhd.parquet").to_crs(EPSG[area])
    fp = gpd.read_parquet(DATA / area / "epc/footprints.parquet", columns=["fp_id", "geometry", "height_m", "num_floors"])
    fp["fp_id"] = fp["fp_id"].astype(str)
    if a.bbox:
        x0, y0, x1, y1 = a.bbox
        area_geom, label = shapely.box(x0, y0, x1, y1), f"bbox_{int(x0)}_{int(y0)}"
    else:
        if a.nbhd:
            sel = nb[nb["nbhd"].astype(str) == a.nbhd]
        elif a.name:
            sel = nb[nb["nbhd_name"].astype(str).str.contains(a.name, case=False, regex=False)]
        else:                                 # the neighbourhood with the most predicted dwellings
            pred = pd.read_parquet(DATA / area / f"model/stock/stock_pred_{a.year}.parquet", columns=["fp_id", "n_uprn"])
            pts = fp.set_index("fp_id").loc[pred["fp_id"].astype(str)].geometry.representative_point()
            j = gpd.sjoin(gpd.GeoDataFrame({"n": pred["n_uprn"].to_numpy()}, geometry=pts.values, crs=fp.crs), nb[["nbhd", "geometry"]])
            best = j.groupby("nbhd")["n"].sum().idxmax()
            sel = nb[nb["nbhd"] == best]
        if sel.empty:
            sys.exit("no neighbourhood matches; codes and names are in data/<area>/analysis/geometry_nbhd.parquet")
        sel = sel.iloc[:1]
        area_geom = sel.geometry.iloc[0]
        label = f"{sel['nbhd'].iloc[0]}_{re.sub(r'[^A-Za-z0-9]+', '_', str(sel['nbhd_name'].iloc[0])).strip('_')}"
    inside = fp[fp.geometry.representative_point().within(area_geom)]
    return inside, area_geom, label


def ground_heights(area, geoms):
    """terrain height under each footprint from the 30 m Copernicus DEM (0 where unavailable)"""
    dem = next((DATA / area / "gee_v2/raw").glob("*_dem_30m.tif"), None)
    if dem is None:
        return np.zeros(len(geoms))
    import rasterio
    pts = [g.representative_point() for g in geoms]
    with rasterio.open(dem) as r:
        from pyproj import Transformer
        tr = Transformer.from_crs(EPSG[area], r.crs, always_xy=True)
        xy = [tr.transform(p.x, p.y) for p in pts]
        z = np.array([v[0] for v in r.sample(xy)], dtype=float)
        if r.nodata is not None:
            z[z == r.nodata] = np.nan
    return np.nan_to_num(z, nan=0.0)


def clean_polygons(g):
    """valid, oriented polygons (exterior counter-clockwise, holes clockwise) without repeated vertices"""
    g = shapely.make_valid(g) if not g.is_valid else g
    polys = [p for p in (g.geoms if hasattr(g, "geoms") else [g]) if isinstance(p, Polygon) and p.area > 1.0]
    out = []
    for p in polys:
        p = shapely.set_precision(p, SCALE)   # snap to the stored precision, so that rings stay valid when stored
        for q in (p.geoms if isinstance(p, MultiPolygon) else [p]):
            if isinstance(q, Polygon) and q.area > 1.0:
                out.append(shapely.geometry.polygon.orient(q.simplify(0.0), sign=1.0))
    return out


class Vertices:
    """shared, de-duplicated vertex list in integer millimetres"""
    def __init__(self, origin):
        self.origin, self.index, self.list = origin, {}, []

    def add(self, x, y, z):
        key = (int(round((x - self.origin[0]) / SCALE)), int(round((y - self.origin[1]) / SCALE)), int(round((z - self.origin[2]) / SCALE)))
        if key not in self.index:
            self.index[key] = len(self.list)
            self.list.append(list(key))
        return self.index[key]


def solid(poly, z0, z1, V):
    """boundaries and semantic values of an extruded polygon (LoD1 block): ground, roof, then one wall per edge"""
    rings = [list(poly.exterior.coords)[:-1]] + [list(r.coords)[:-1] for r in poly.interiors]
    bottom = [[V.add(x, y, z0) for x, y in r] for r in rings]
    top = [[V.add(x, y, z1) for x, y in r] for r in rings]
    surfaces, values = [], []
    surfaces.append([list(reversed(b)) for b in bottom]); values.append(0)    # ground: normal down
    surfaces.append([list(t) for t in top]); values.append(1)                 # roof: normal up
    for b, t in zip(bottom, top):                                             # walls: normal outwards
        n = len(b)
        for i in range(n):
            j = (i + 1) % n
            surfaces.append([[b[i], b[j], t[j], t[i]]]); values.append(2)
    return [surfaces], [values]


def num(v, nd=2):
    return None if v is None or (isinstance(v, float) and not np.isfinite(v)) or pd.isna(v) else round(float(v), nd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True, choices=list(EPSG)); ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--nbhd"); ap.add_argument("--name"); ap.add_argument("--bbox", nargs=4, type=float)
    ap.add_argument("--max-buildings", type=int, default=5000); ap.add_argument("--preview", action="store_true")
    a = ap.parse_args()
    fp, area_geom, label = district(a.area, a)
    dw_all = pd.read_parquet(DATA / a.area / "epc/dwellings_fp.parquet", columns=["fp_id", "n_uprn"])
    fp = fp[fp["fp_id"].isin(set(dw_all.loc[dw_all["n_uprn"] >= 1, "fp_id"].astype(str)))]   # dwelling buildings
    if len(fp) > a.max_buildings:
        sys.exit(f"{len(fp):,} dwelling buildings in {label}: choose a smaller district or raise --max-buildings")
    ids = set(fp["fp_id"])
    pick = lambda name, cols: (lambda t: t[t["fp_id"].astype(str).isin(ids)].assign(fp_id=lambda d: d["fp_id"].astype(str))
                               .drop_duplicates("fp_id").set_index("fp_id"))(pd.read_parquet(DATA / a.area / name, columns=["fp_id"] + cols))
    lid = pick("epc/lidar_fp.parquet", ["lidar_height_med_m", "lidar_height_p90_m", "lidar_roof_slope_med_deg", "lidar_roof_south_share",
                                        "lidar_roof_flat_share", "lidar_survey_year", "lidar_built_after_survey"])
    phy = pick("epc/physics_fp.parquet", ["phys_storeys", "phys_floor_m2", "phys_volume_m3", "phys_wall_ext_m2", "phys_wall_party_m2",
                                          "phys_roof_m2", "phys_ground_m2", "phys_envelope_m2", "phys_hlff", "phys_sv", "phys_exposed_share"])
    dw = pick("epc/dwellings_fp.parquet", ["n_uprn"])
    pred = pick(f"model/stock/stock_pred_{a.year}.parquet", ["pred_sap", "pred_band", "p_FG", "confidence", "certified"])
    d = fp.set_index("fp_id").join([lid, phy, dw, pred])
    d = d[d["n_uprn"].fillna(0) >= 1]                         # dwelling buildings only (at least one address)
    z0 = ground_heights(a.area, d.geometry.values)
    h, src = d["lidar_height_med_m"].astype(float), pd.Series("lidar_median", index=d.index)
    for alt, name in ((d["height_m"].astype(float), "footprint_source"), (d["num_floors"].astype(float) * 3.0, "storeys_x_3m"),
                      (d["phys_storeys"].astype(float) * 3.0, "storeys_x_3m")):
        miss = ~(h > 2.0)
        h, src = h.where(~miss, alt), src.where(~miss, name)
    miss = ~(h > 2.0)
    h, src = h.where(~miss, 6.0), src.where(~miss, "default_6m")

    bounds = d.total_bounds
    V = Vertices((bounds[0], bounds[1], float(np.floor(z0.min()))))
    objects, skipped = {}, 0
    for (fid, row), zg, hh, hs in zip(d.iterrows(), z0, h, src):
        polys = clean_polygons(row.geometry)
        if not polys:
            skipped += 1; continue
        parts = [solid(p, zg, zg + hh, V) for p in polys]
        sem = {"surfaces": [{"type": "GroundSurface"}, {"type": "RoofSurface"}, {"type": "WallSurface"}]}
        if len(parts) == 1:
            geom = {"type": "Solid", "lod": "1.2", "boundaries": parts[0][0], "semantics": {**sem, "values": parts[0][1]}}
        else:
            geom = {"type": "MultiSolid", "lod": "1.2", "boundaries": [p[0] for p in parts], "semantics": {**sem, "values": [p[1] for p in parts]}}
        att = {
            "function": "residential", "measuredHeight": num(hh), "storeysAboveGround": int(row["phys_storeys"]) if pd.notna(row["phys_storeys"]) else None,
            "gbem_footprintId": fid, "gbem_heightSource": hs, "gbem_groundHeight": num(zg),
            "gbem_numberOfDwellings": int(row["n_uprn"]) if pd.notna(row["n_uprn"]) else None,
            "gbem_heightLidarP90": num(row["lidar_height_p90_m"]), "gbem_lidarSurveyYear": num(row["lidar_survey_year"], 0),
            "energy_epcRatingPredicted": row["pred_band"] if isinstance(row["pred_band"], str) else None,
            "energy_sapScorePredicted": num(row["pred_sap"], 1), "energy_probabilityRatingFG": num(row["p_FG"], 3),
            "energy_predictionConfidence": num(row["confidence"], 3),
            "energy_hasCertificate": bool(row["certified"]) if pd.notna(row["certified"]) else None,
            "energy_floorArea": num(row["phys_floor_m2"], 1), "energy_heatedVolume": num(row["phys_volume_m3"], 1),
            "energy_envelopeArea": num(row["phys_envelope_m2"], 1), "energy_exteriorWallArea": num(row["phys_wall_ext_m2"], 1),
            "energy_partyWallArea": num(row["phys_wall_party_m2"], 1), "energy_roofArea": num(row["phys_roof_m2"], 1),
            "energy_groundFloorArea": num(row["phys_ground_m2"], 1), "energy_heatLossFormFactor": num(row["phys_hlff"], 3),
            "energy_surfaceToVolumeRatio": num(row["phys_sv"], 3), "energy_exposedShare": num(row["phys_exposed_share"], 3),
            "energy_roofSlope": num(row["lidar_roof_slope_med_deg"], 1), "energy_roofSouthShare": num(row["lidar_roof_south_share"], 3),
            "energy_roofFlatShare": num(row["lidar_roof_flat_share"], 3)}
        objects[f"GBEM_{a.area}_{fid}"] = {"type": "Building", "attributes": {k: v for k, v in att.items() if v is not None},
                                           "geometry": [geom]}
    verts = np.array(V.list)
    real = verts * SCALE + np.array(V.origin)
    cj = {"type": "CityJSON", "version": "2.0",
          "transform": {"scale": [SCALE] * 3, "translate": list(map(float, V.origin))},
          "metadata": {"referenceSystem": f"https://www.opengis.net/def/crs/EPSG/0/{EPSG[a.area]}",
                       "geographicalExtent": [*map(float, real.min(0)), *map(float, real.max(0))],
                       "title": f"GBEM LoD1.2 buildings with energy estimates: {label} ({a.area}, {a.year})",
                       "referenceDate": datetime.date.today().isoformat(),
                       "identifier": f"gbem-{a.area}-{label}-{a.year}"},
          "CityObjects": objects, "vertices": V.list}
    out = DATA / a.area / "geobim"; out.mkdir(parents=True, exist_ok=True)
    path = out / f"{label}.city.json"
    keep(path).write_text(json.dumps(cj, separators=(",", ":")), encoding="utf-8")
    meta = {"district": label, "area": a.area, "year": a.year, "buildings": len(objects), "skipped_without_valid_polygon": skipped,
            "crs": f"EPSG:{EPSG[a.area]}", "lod": "1.2 (footprint extruded to the LiDAR median height above the DEM ground)",
            "height_sources": src.value_counts().to_dict(),
            "inputs": ["epc/footprints.parquet", "epc/lidar_fp.parquet", "epc/physics_fp.parquet", "epc/dwellings_fp.parquet",
                       f"model/stock/stock_pred_{a.year}.parquet", "gee_v2/raw/*_dem_30m.tif"],
            "model": "LightGBM, settings of models/baseline.py, feature set eo_morph, trained on the certificates of the year; "
                     "spatial 5-fold cross-validation with 2 km blocks (error: generated/numbers.tex, LonMaeEoMorph / BelMaeEoMorph)",
            "attributes": "CityGML names where they exist; energy_* after the CityGML Energy ADE 1.0; *Predicted are model outputs",
            "use": "internal: building-level estimates describe areas, not individual homes; do not publish"}
    keep(out / f"{label}_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"{label}: {len(objects):,} buildings, {len(V.list):,} vertices -> {path}")
    if a.preview:
        preview(cj, out / f"{label}_preview.png", label)


def preview(cj, png, label):
    """3D view of the roofs and walls, coloured by predicted band"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    s, t = np.array(cj["transform"]["scale"]), np.array(cj["transform"]["translate"])
    v = np.array(cj["vertices"]) * s + t
    v = v - v.min(0)
    polys, colours = [], []
    for o in cj["CityObjects"].values():
        c = BAND_COLOURS.get(o["attributes"].get("energy_epcRatingPredicted"), "#bbbbbb")
        g = o["geometry"][0]
        shells = [g["boundaries"]] if g["type"] == "Solid" else g["boundaries"]
        for sh in shells:
            for surf in sh[0][1:]:                                         # roof and walls (skip the ground)
                polys.append(v[surf[0]]); colours.append(c)
    fig = plt.figure(figsize=(9, 7), dpi=200)
    ax = fig.add_subplot(projection="3d")
    ax.add_collection3d(Poly3DCollection(polys, facecolors=colours, edgecolors="#33333355", linewidths=0.1))
    ext = v.max(0)
    ax.set_xlim(0, ext[0]); ax.set_ylim(0, ext[1]); ax.set_zlim(0, max(ext[2], 1))
    ax.set_box_aspect((ext[0], ext[1], max(ext[2], 1) * 3))
    ax.view_init(elev=35, azim=-60); ax.set_axis_off()
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=BAND_COLOURS[b], label=b) for b in BANDS], title="Predicted band", loc="upper left", fontsize=7, title_fontsize=7)
    ax.set_title(label.replace("_", " "), fontsize=9)
    fig.savefig(keep(png), bbox_inches="tight"); plt.close(fig)
    print("preview ->", png)


if __name__ == "__main__":
    main()
