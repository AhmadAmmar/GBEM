"""GBEM Atlas: one dashboard for all study areas (Greater London, Greater Belfast) with maps (grid, neighbourhoods,
streets, 3D buildings), hotspots, rankings, trends, retrofit needs, model results and comparison.

    python atlas.py [--areas london belfast] [--public]

Reads per area (data/<area>/):
  analysis/units_{cell,nbhd,sector,street,la}.parquet, geometry_{nbhd,street}.parquet, trends.csv, repeat_change.csv,
  stock_current.parquet, recs_summary.csv  (code/analysis/stock.py)
  model/results/baseline_<tag>.csv, importance_<tag>.csv, oof_<tag>.parquet  (code/models/baseline.py)
  epc/certificates_linked.parquet, footprints.parquet, morphology.parquet, lidar_fp.parquet  (3D buildings)
Writes maps/dashboard/gbem_atlas.html (property-level buildings layer: local only, never committed or published) or,
with --public, maps/dashboard/gbem_atlas_public.html: aggregates only (no buildings layer; grid cells, streets and
neighbourhoods with at least 10 certificates), which can be shared.
Template: atlas_template.html. Binary columns are gzip-compressed inside the page and decompressed by the browser.
"""
import argparse, base64, datetime, gzip, json, pathlib, sys
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from pyproj import Transformer
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

CODE = pathlib.Path(__file__).resolve().parents[1]
DATA = CODE.parent / "data"
EPSG = {"london": 27700, "belfast": 29902}
NAMES = {"london": "Greater London", "belfast": "Greater Belfast"}
NBHD = {"london": "LSOA 2021", "belfast": "Ward 2012"}
MODEL_TAG = {"london": "2024_s50k", "belfast": "2024"}
GRID = 250
BANDS = list("ABCDEFG")
ELEMENTS = ["walls", "roof", "windows", "floor", "mainheat", "controls", "hotwater", "lighting"]
ELEMENT_LABEL = {"walls": "Walls", "roof": "Roof", "windows": "Windows", "floor": "Floor", "mainheat": "Main heating",
                 "controls": "Heating controls", "hotwater": "Hot water", "lighting": "Lighting"}
# map metrics of the stock layers: key, label, colour scale, direction (+1: higher is better, -1: worse, 0: neutral)
METRICS = [("sap_mean", "Mean SAP score", "sap", 1), ("share_AC", "Share rated A–C", "seq", 1),
           ("share_DG", "Share rated D–G", "seq", -1), ("share_FG", "Share rated F–G (poorest)", "seq", -1),
           ("potential_gap", "Mean SAP gain possible (potential − current)", "seq", -1),
           ("co2_m2", "CO₂ per m² (median, kg/yr)", "seq", -1), ("fuel_heat_pump", "Heat pump share", "seq", 1),
           ("pv", "Solar PV share", "seq", 1), ("fuel_gas", "Mains gas share", "seq", 0),
           ("fuel_electricity", "Electric (non heat pump) share", "seq", 0), ("fuel_oil", "Oil share", "seq", -1)] + \
          [(f"poor_{e}", f"Poor {ELEMENT_LABEL[e].lower()} share", "seq", -1) for e in ELEMENTS] + \
          [("n", "Certificates (current stock)", "seq", 0),
           ("pred_sap_all", "Predicted mean SAP, all dwellings (model)", "sap", 1),
           ("pred_FG_all", "Predicted F–G share, all dwellings (model)", "seq", -1),
           ("cert_gap", "Certified minus all-dwellings predicted SAP (certificate bias)", "divv", 0),
           ("gas_kwh", "Gas per meter 2024 (kWh, measured, DESNZ)", "seq", -1),
           ("elec_kwh", "Electricity per meter 2024 (kWh, measured, DESNZ)", "seq", -1),
           ("gas_change", "Change in gas per meter 2015→2024 (%, measured)", "divv", -1),
           ("share_ready", "Heat-pump ready (heat-loss parameter < 2 W/m²K)", "seq", 1),
           ("share_fabric_first", "Fabric first before a heat pump (≥ 3 W/m²K)", "seq", -1),
           ("heat_pump_share", "Homes heated by a heat pump", "seq", 1),
           ("density_mwh_km2", "Space-heating demand density (MWh/km², physics estimate)", "seq", 0),
           ("overheating_index", "Summer overheating exposure (index 0–1, exploratory)", "seq", -1),
           ("kwp_median_houses", "Rooftop solar potential per house (kWp, LiDAR)", "seq", 1),
           ("share_fuel_poor", "Households in fuel poverty (official, 2024 data)", "seq", -1),
           ("outside_aoa", "Homes outside the model's area of applicability", "seq", -1)]
GI = [("gi_sap", "Hotspots of SAP: clusters of high (blue) / low (red) scores, Gi* z", "div", 1),
      ("gi_FG", "Hotspots of F–G homes: clusters (red) / absence (blue), Gi* z", "div", -1)]
TOP_NEED = ("top_need", "Most common weak element", "cat", 0)


class Blob:
    """Typed arrays packed into one buffer (4-byte aligned); gzip + base64 for the page."""
    def __init__(self):
        self.parts, self.size = [], 0

    def add(self, a, t):
        a = np.ascontiguousarray(np.asarray(a, dtype={"f4": "float32", "u4": "uint32", "u1": "uint8", "i2": "int16"}[t]))
        pad = (-self.size) % 4
        if pad:
            self.parts.append(b"\0" * pad); self.size += pad
        ref = {"o": self.size, "n": int(a.size), "t": t}
        self.parts.append(a.tobytes()); self.size += a.nbytes
        return ref

    def b64(self):
        return base64.b64encode(gzip.compress(b"".join(self.parts), 6)).decode()


def rings(geoms, center, parts=True):
    """Exterior rings (polygons) or paths (lines) as flat coordinates relative to the area centre; returns feature
    index per ring, ring start offsets and the coordinates."""
    fid, starts, xy = [], [], []
    n = 0
    for i, g in enumerate(geoms):
        if g is None or g.is_empty:
            continue
        subs = shapely.get_parts(shapely.get_parts(g))           # collections and multi-parts -> single parts
        for s in subs:
            if s.geom_type not in ("Polygon", "LineString", "LinearRing"):
                continue
            c = np.asarray(s.exterior.coords if s.geom_type == "Polygon" else s.coords)[:, :2]
            if len(c) < 2:
                continue
            fid.append(i); starts.append(n); xy.append(c - center); n += len(c)
    starts.append(n)
    return np.array(fid), np.array(starts), (np.concatenate(xy) if xy else np.zeros((0, 2)))


def table(df, blob, cols):
    """numeric columns -> float32 refs; text columns -> JSON lists"""
    out = {}
    for c in cols:
        if c not in df:
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            out[c] = blob.add(df[c].to_numpy("float64"), "f4")
        else:
            out[c] = {"s": df[c].astype(str).where(df[c].notna(), "").tolist()}
    return out


def top_need(u):
    cols = [f"poor_{e}" for e in ELEMENTS if e not in ("floor", "lighting") and f"poor_{e}" in u]
    m = u[cols].to_numpy("float64")
    idx = np.nanargmax(np.where(np.isnan(m), -1, m), axis=1)
    best = np.nanmax(np.where(np.isnan(m), -1, m), axis=1)
    lab = np.array([c[5:] for c in cols])[idx]
    return np.where(best >= 0.25, lab, "none")


def buildings(area, center, blob):
    """3D buildings: footprints of the certificates with out-of-fold predictions, one feature per footprint."""
    res = DATA / area / "model/results"
    oof = pd.read_parquet(res / f"oof_{MODEL_TAG[area]}.parquet")
    oof["id_cert"] = oof["id_cert"].astype(str)
    link = pd.read_parquet(DATA / area / "epc/certificates_linked.parquet", columns=["cert_id", "fp_id", "PROPERTY_TYPE"])
    link["cert_id"] = link["cert_id"].astype(str)
    d = oof.merge(link.drop_duplicates("cert_id").rename(columns={"cert_id": "id_cert"}), on="id_cert", how="inner")
    d = d[d["fp_id"].notna()]
    code = {b: i for i, b in enumerate(BANDS)}
    d["a"] = d["actual"].map(code)
    runs = [c[5:] for c in oof.columns if c.startswith("pred_lgbm_")]
    agg = {"n": ("id_cert", "size"), "a": ("a", "mean"), "sap": ("actual_sap", "mean"),
           "ptype": ("PROPERTY_TYPE", lambda s: s.mode().iat[0] if s.notna().any() else "")}
    for r in runs:
        d[f"p_{r}"] = d[f"pred_{r}"].map(code)
        agg[f"p_{r}"] = (f"p_{r}", "mean")
        agg[f"s_{r}"] = (f"sap_{r}", "mean")
    g = d.groupby("fp_id").agg(**agg)
    fp = gpd.read_parquet(DATA / area / "epc/footprints.parquet", columns=["fp_id", "geometry"])
    fp = fp[fp["fp_id"].isin(g.index)].set_index("fp_id")
    morph = pd.read_parquet(DATA / area / "epc/morphology.parquet", columns=["fp_id", "height_m", "num_floors"]).set_index("fp_id")
    lid = pd.read_parquet(DATA / area / "epc/lidar_fp.parquet", columns=["fp_id", "lidar_height_med_m", "lidar_valid_share",
                                                                        "lidar_roof_slope_med_deg"]).set_index("fp_id")
    g = g.join(fp, how="inner").join(morph, how="left").join(lid, how="left")
    h = g["lidar_height_med_m"].where(g["lidar_valid_share"] >= 0.5)
    src = np.where(h.notna(), 1, np.where(g["height_m"].notna(), 2, np.where(g["num_floors"].notna(), 3, 0)))
    g["height"] = h.fillna(g["height_m"]).fillna(g["num_floors"] * 3).fillna(5).clip(2, 250)
    g["hsrc"] = src
    geo = gpd.GeoSeries(g["geometry"].values, crs=EPSG[area]).simplify(0.5).to_crs(4326)
    fid, starts, xy = rings(geo.values, center)
    cols = {"n": blob.add(g["n"], "f4"), "a": blob.add(g["a"], "f4"), "sap": blob.add(g["sap"], "f4"),
            "height": blob.add(g["height"], "f4"), "hsrc": blob.add(g["hsrc"], "u1"),
            "slope": blob.add(g["lidar_roof_slope_med_deg"], "f4"), "ptype": {"s": g["ptype"].astype(str).tolist()}}
    for r in runs:
        cols[f"p_{r}"] = blob.add(g[f"p_{r}"], "f4"); cols[f"s_{r}"] = blob.add(g[f"s_{r}"], "f4")
    return {"n": len(g), "runs": runs, "cols": cols, "fid": blob.add(fid, "u4"), "starts": blob.add(starts, "u4"),
            "xy": blob.add(xy.ravel(), "f4")}


def stock_cells(area):
    """whole-stock predictions per cell (models/stock_predict.py), newest year"""
    f = sorted((DATA / area / "model/stock").glob("stock_units_*.csv"))
    if not f:
        return None
    u = pd.read_csv(f[-1]).query("unit == 'cell'").rename(columns={"id": "cell"})
    u["cert_gap"] = u["pred_sap_certified"] - u["pred_sap_all"]
    return u.set_index("cell")[["pred_sap_all", "pred_FG_all", "cert_gap", "dwellings"]]


def extra_units(area, unit):
    """per-unit results of the analysis scripts (heat pumps, heat density, overheating, solar, fuel poverty, trust)"""
    A = DATA / area / "analysis"
    parts = []
    def add(p, key, cols, rename=None):
        if p.exists():
            t = pd.read_parquet(p).rename(columns=rename or {})
            parts.append(t.set_index(key)[[c for c in cols if c in t]])
    add(A / f"hp_readiness_units_{unit}.parquet", unit, ["share_ready", "share_fabric_first", "heat_pump_share"])
    if unit == "cell":
        add(A / "heat_density_cells.parquet", "cell", ["density_mwh_km2"])
        add(A / "overheating_units_cell.parquet", "cell", ["overheating_index"])
        aoa = DATA / "model_transfer/aoa_2024.csv"
        pts = DATA / "model_transfer/aoa_2024_points.parquet"
        if aoa.exists() and pts.exists():
            thr = pd.read_csv(aoa).query("experiment == @'within ' + @area + ' (spatial CV)'")["threshold"]
            p = pd.read_parquet(pts).query("experiment == @'within ' + @area")
            cur = pd.read_parquet(A / "cert_enriched.parquet", columns=["cert_id", "cell"]).rename(columns={"cert_id": "id_cert"})
            p = p.merge(cur, on="id_cert", how="inner")
            if len(thr):
                parts.append(p.assign(o=p["di"] > thr.iat[0]).groupby("cell")["o"].mean().rename("outside_aoa").to_frame())
    if unit == "nbhd":
        add(A / "solar_units_nbhd.parquet", "nbhd", ["kwp_median_houses"])
        fp = DATA / area / "fuel_poverty/fuel_poverty_lsoa_london.parquet"
        add(fp, "nbhd", ["share_fuel_poor"], {"lsoa": "nbhd"})
    return pd.concat(parts, axis=1) if parts else None


def energy_lsoa(area):
    """measured domestic gas and electricity per meter by LSOA (geo/get_desnz_energy.py): 2024 and change since 2015"""
    p = DATA / area / "energy_desnz/lsoa_energy_london.parquet"
    if not p.exists():
        return None, None
    e = pd.read_parquet(p)
    piv = e.pivot_table(index="lsoa", columns=["fuel", "year"], values="mean_kwh")
    out = pd.DataFrame({"gas_kwh": piv.get(("gas", 2024)), "elec_kwh": piv.get(("electricity", 2024))})
    if ("gas", 2015) in piv:
        out["gas_change"] = 100 * (piv[("gas", 2024)] / piv[("gas", 2015)] - 1)
    trend = e.groupby(["fuel", "year"]).agg(meters=("meters", "sum"), total_kwh=("total_kwh", "sum"), median_lsoa_mean_kwh=("mean_kwh", "median")).reset_index()
    trend["mean_kwh"] = trend["total_kwh"] / trend["meters"]
    return out, trend


def stock_total(area):
    f = sorted((DATA / area / "model/stock").glob("stock_pred_*.parquet"))
    if not f:
        return None
    r = pd.read_parquet(f[-1])
    w, c = r["n_uprn"], r["certified"]
    return {"year": int(f[-1].stem.rsplit("_", 1)[1]), "buildings": len(r), "dwellings": float(w.sum()),
            "certified_buildings": int(c.sum()), "sap_all": float(np.average(r["pred_sap"], weights=w)),
            "sap_certified": float(np.average(r.loc[c, "pred_sap"], weights=w[c])),
            "fg_all": float(np.average(r["p_FG"], weights=w)), "fg_certified": float(np.average(r.loc[c, "p_FG"], weights=w[c]))}


def read_csv(p):
    return json.loads(pd.read_csv(p).round(4).to_json(orient="records")) if p.exists() else []


def area_pack(area, public, domains):
    a_dir = DATA / area / "analysis"
    blob = Blob()
    cur = pd.read_parquet(a_dir / "stock_current.parquet", columns=["x", "y", "band", "sap", "property_type", "floor_pos", "cell",
                                                                   "nbhd_name", "street", "potential_gap", "fuel", "pv"] + [f"poor_{e}" for e in ELEMENTS])
    lon, lat = Transformer.from_crs(EPSG[area], 4326, always_xy=True).transform(cur["x"].to_numpy(), cur["y"].to_numpy())
    center = np.array([float(np.median(lon)), float(np.median(lat))])
    bounds = [float(np.percentile(lon, 0.5)), float(np.percentile(lat, 0.5)), float(np.percentile(lon, 99.5)), float(np.percentile(lat, 99.5))]
    mcols = [m[0] for m in METRICS] + [g[0] for g in GI]
    minn = 10 if public else 5
    layers = {}
    # grid cells
    u = pd.read_parquet(a_dir / "units_cell.parquet")
    u = u[u["n"] >= minn].reset_index(drop=True)
    u["top_need"] = top_need(u)
    sc = stock_cells(area)
    if sc is not None:
        u = u.join(sc, on="cell")
    xc = extra_units(area, "cell")
    if xc is not None:
        u = u.join(xc, on="cell")
    # a readable place name per cell: its most common street and neighbourhood
    mode = lambda s: s.mode().iat[0] if s.notna().any() else ""
    place = cur.groupby("cell").agg(st=("street", mode), nb=("nbhd_name", mode))
    place = (place["st"].str.split(" | ", regex=False).str[0].fillna("") + ", " + place["nb"].fillna("")).str.strip(", ")
    u["place"] = u["cell"].map(place).fillna("")
    tr = Transformer.from_crs(EPSG[area], 4326, always_xy=True)
    top = u.loc[u["n"].idxmax()]
    focus = list(tr.transform(top["cx"], top["cy"]))
    h = GRID / 2
    cells = [shapely.Polygon([tr.transform(x + dx, y + dy) for dx, dy in ((-h, -h), (h, -h), (h, h), (-h, h))])
             for x, y in zip(u["cx"], u["cy"])]
    fid, starts, xy = rings(cells, center)
    layers["cell"] = {"label": f"Grid {GRID} m", "n": len(u), "cols": table(u, blob, mcols + ["cell", "place", "top_need"]),
                      "fid": blob.add(fid, "u4"), "starts": blob.add(starts, "u4"), "xy": blob.add(xy.ravel(), "f4")}
    # neighbourhoods
    u = pd.read_parquet(a_dir / "units_nbhd.parquet")
    u = u[u["n"] >= minn]
    geo = gpd.read_parquet(a_dir / "geometry_nbhd.parquet").drop_duplicates("nbhd").set_index("nbhd")
    u = u[u["nbhd"].isin(geo.index)].reset_index(drop=True)
    u["top_need"] = top_need(u)
    en, energy_trend = energy_lsoa(area)
    if en is not None:
        u = u.join(en, on="nbhd")
    xn = extra_units(area, "nbhd")
    if xn is not None:
        u = u.join(xn, on="nbhd")
    gs = gpd.GeoSeries(geo.loc[u["nbhd"], "geometry"].values, crs=4326).simplify(0.00004)
    fid, starts, xy = rings(gs.values, center)
    layers["nbhd"] = {"label": NBHD[area], "n": len(u), "cols": table(u, blob, mcols[:-2] + ["nbhd", "nbhd_name", "rank_sap", "top_need"]),
                      "fid": blob.add(fid, "u4"), "starts": blob.add(starts, "u4"), "xy": blob.add(xy.ravel(), "f4")}
    # streets
    u = pd.read_parquet(a_dir / "units_street.parquet")
    u = u[u["n"] >= minn]
    geo = gpd.read_parquet(a_dir / "geometry_street.parquet").drop_duplicates("street").set_index("street")
    u = u[u["street"].isin(geo.index)].reset_index(drop=True)
    u["top_need"] = top_need(u)
    # draw each street only where its homes are: the road line within 80 m of the convex hull of its address points
    pts = cur[cur["street"].isin(u["street"])].groupby("street").apply(
        lambda g: shapely.convex_hull(shapely.multipoints(np.column_stack([g["x"], g["y"]]))).buffer(80), include_groups=False)
    lines = gpd.GeoSeries(geo.loc[u["street"], "geometry"].values, crs=4326).to_crs(EPSG[area])
    clipped = shapely.intersection(lines.values, pts.reindex(u["street"]).values)
    lines = gpd.GeoSeries(clipped, crs=EPSG[area]).to_crs(4326)
    fid, starts, xy = rings(lines.values, center)
    layers["street"] = {"label": "Streets", "n": len(u), "cols": table(u, blob, mcols[:-2] + ["street", "rank_sap", "top_need"]),
                        "fid": blob.add(fid, "u4"), "starts": blob.add(starts, "u4"), "xy": blob.add(xy.ravel(), "f4"), "path": True}
    # urban form types (analysis/morph_types.py)
    tp = a_dir / "morph_types_cells.parquet"
    if tp.exists():
        t = pd.read_parquet(tp)
        t = t[t["n"] >= max(minn, 10)].reset_index(drop=True)
        sq = [shapely.Polygon([tr.transform(x + dx, y + dy) for dx, dy in ((-h, -h), (h, -h), (h, h), (-h, h))]) for x, y in zip(t["cx"], t["cy"])]
        fid, starts, xy = rings(sq, center)
        t["type_id"] = t["type_id"].astype(float)
        layers["types"] = {"label": "Urban form types", "n": len(t), "cols": table(t, blob, ["n", "sap", "type_id", "type", "cell"]),
                           "fid": blob.add(fid, "u4"), "starts": blob.add(starts, "u4"), "xy": blob.add(xy.ravel(), "f4")}
    if not public:
        layers["bldg"] = {"label": "Buildings (3D, model)", **buildings(area, center, blob)}
    # rankings tables (no geometry): sectors and boroughs too
    rank = {}
    for unit, label in (("nbhd", NBHD[area]), ("sector", "Postcode sector"), ("street", "Street"), ("la", "Borough")):
        p = a_dir / f"units_{unit}.parquet"
        if not p.exists():
            continue
        r = pd.read_parquet(p)
        r = r[r["n"] >= minn]
        name = "nbhd_name" if unit == "nbhd" else unit
        txt = r.assign(name=r[name]).drop(columns=[c for c in ("cx", "cy", "gi_sap", "gi_FG") if c in r]).round(4).to_json(orient="records")
        rank[unit] = {"label": label, "n": len(r), "json": blob.add(np.frombuffer(txt.encode("utf-8"), np.uint8), "u1")}   # compressed with the arrays
    # trends, change, retrofit
    tr_ = pd.read_csv(a_dir / "trends.csv")
    tr_ = tr_[(tr_["year"] >= 2008) & (tr_["n"] >= 50)]
    rc = pd.read_csv(a_dir / "repeat_change.csv")
    ret = []
    cur["group"] = np.where(cur["property_type"].isin(["Flat", "Maisonette"]), cur["property_type"] + " · " + cur["floor_pos"].fillna("unknown"), cur["property_type"])
    for k, g in cur.groupby("group"):
        if len(g) < 50:
            continue
        ret.append({"group": k, "n": len(g), "potential_gap": g["potential_gap"].mean(), "share_FG": g["band"].isin(["F", "G"]).mean(),
                    "sap": g["sap"].mean(), **{e: g[f"poor_{e}"].mean() for e in ELEMENTS}})
    stock = {"n": len(cur), "sap_mean": cur["sap"].mean(), "bands": cur["band"].value_counts(normalize=True).reindex(BANDS).fillna(0).tolist(),
             "potential_gap": cur["potential_gap"].mean(), "pv": cur["pv"].mean(),
             "fuels": cur["fuel"].value_counts(normalize=True).round(4).to_dict(),
             "poor": {e: cur[f"poor_{e}"].mean() for e in ELEMENTS}}
    recs = pd.read_csv(a_dir / "recs_summary.csv").head(20).to_dict(orient="records") if (a_dir / "recs_summary.csv").exists() else []
    res = DATA / area / "model/results"
    # main run plus separate runs of single feature sets (baseline.py --tag <tag>_<suffix>), later ones win
    runs = [res / f"baseline_{MODEL_TAG[area]}.csv"] + sorted(res.glob(f"baseline_{MODEL_TAG[area]}_*.csv"))
    metrics = pd.concat([pd.read_csv(p) for p in runs if p.exists()]).drop_duplicates(["featureset", "validation", "model", "target"], keep="last")
    imp = pd.read_csv(res / f"importance_{MODEL_TAG[area]}.csv")
    imp = imp.sort_values("gain", ascending=False).groupby("featureset").head(15)
    clean = lambda o: json.loads(pd.Series([o]).to_json(orient="values"))[0]
    return {"name": NAMES[area], "nbhd": NBHD[area], "center": center.tolist(), "bounds": bounds, "focus": focus, "layers": layers,
            "rank": rank, "trends": json.loads(tr_.round(4).to_json(orient="records")),
            "change": json.loads(rc.round(4).to_json(orient="records")), "retrofit": clean(ret), "stock": clean(stock),
            "recs": recs, "metrics": json.loads(metrics.round(4).to_json(orient="records")),
            "importance": json.loads(imp.round(6).to_json(orient="records")), "model_tag": MODEL_TAG[area],
            "groups": [g for p in [res / f"groups_{MODEL_TAG[area]}.csv"] + sorted(res.glob(f"groups_{MODEL_TAG[area]}_*.csv")) for g in read_csv(p)],
            "retro_models": read_csv(res / f"retrofit_needs_{MODEL_TAG[area]}_eo_morph.csv"),
            "types": read_csv(a_dir / "morph_types_summary.csv"), "shap": read_csv(a_dir / "morph_shap_importance.csv")[:15],
            "shap_dep": read_csv(a_dir / "morph_shap_dependence.csv"), "form_cv": read_csv(a_dir / "morph_cv.csv"),
            "energy": json.loads(energy_trend.round(2).to_json(orient="records")) if energy_trend is not None else [],
            "stock_pred": stock_total(area),
            "blob": blob.b64(), "blob_bytes": blob.size}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--areas", nargs="+", default=["london", "belfast"]); ap.add_argument("--public", action="store_true")
    a = ap.parse_args()
    # common colour domains across areas (2nd-98th percentile of grid cells), so the areas can be compared
    cells = pd.concat([pd.read_parquet(DATA / ar / "analysis/units_cell.parquet") for ar in a.areas])
    cells = cells[cells["n"] >= 5]
    extra = [x for x in [stock_cells(ar) for ar in a.areas] if x is not None]
    extra += [x for x in [energy_lsoa(ar)[0] for ar in a.areas] if x is not None]
    extra += [x for x in [extra_units(ar, un) for ar in a.areas for un in ("cell", "nbhd")] if x is not None]
    pool = pd.concat([cells] + [x.reset_index(drop=True) for x in extra], ignore_index=True)
    domains = {}
    for k, *_ in METRICS + GI:
        if k in pool and pool[k].notna().any():
            lo, hi = np.nanpercentile(pool[k], [2, 98])
            domains[k] = [round(float(lo), 3), round(float(hi), 3)]
    for k in ("cert_gap", "gas_change"):                     # diverging around 0
        if k in domains:
            m = max(abs(domains[k][0]), abs(domains[k][1])); domains[k] = [-m, m]
    domains["sap_mean"] = [20, 92]
    domains["gi_sap"] = domains["gi_FG"] = [-4, 4]
    payload = {"built": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "public": a.public, "grid": GRID,
               "metrics": [{"key": k, "label": l, "kind": kd, "dir": dr, "domain": domains.get(k)} for k, l, kd, dr in METRICS + GI],
               "elements": ELEMENTS, "element_label": ELEMENT_LABEL, "areas": {},
               "transfer": read_csv(DATA / "model_transfer/transfer_2024.csv")}
    for ar in a.areas:
        payload["areas"][ar] = area_pack(ar, a.public, domains)
        print(f"{ar}: {payload['areas'][ar]['blob_bytes'] / 1e6:.1f} MB of arrays; layers "
              + ", ".join(f"{k} {v['n']:,}" for k, v in payload["areas"][ar]["layers"].items()), flush=True)
    html = (pathlib.Path(__file__).with_name("atlas_template.html").read_text(encoding="utf-8")
            .replace("/*__DATA__*/null", json.dumps(payload, separators=(",", ":"), allow_nan=False)))
    out = CODE / "maps" / "dashboard" / ("gbem_atlas_public.html" if a.public else "gbem_atlas.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    keep(out).write_text(html, encoding="utf-8")
    print(f"{out.stat().st_size / 1e6:.1f} MB -> {out}")


if __name__ == "__main__":
    main()
