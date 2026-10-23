"""Housing stock analysis from the certificates: trends, change, retrofit needs, and area / street / grid summaries
with rankings and hotspots.

    python stock.py --area belfast|london [--valid-from 2016-10-23] [--grid 250] [--no-recs]

Input: data/<area>/epc/certificates_linked.parquet (all certificates, any year), footprints and LiDAR, OSM roads
(data/osm/geofabrik_*), boundaries (London LSOA 2021, code/geo/get_boundaries.py; NI wards 2012, OSNI), and for London
the recommendations of the England and Wales register (domestic-csv.zip; NI certificates have none in the file).

Derived per certificate (cert_enriched.parquet):
  sap, band, potential_sap, potential_gap (potential - current SAP), co2_m2 (kg CO2 per m2 per year)
  fuel: gas | electricity | heat pump | community | oil | solid | LPG | other  (heat pump from the heating description)
  pv (photovoltaic supply > 0), solar_water
  poor_<element>: element rated Poor or Very Poor (walls, roof, windows, floor, mainheat, controls, hot water, lighting)
  floor_pos: house | ground | middle | top | unknown  (flats and maisonettes, from the floor level and top-storey flag)
  units: sector (postcode sector), district, la (borough; London), nbhd (LSOA 2021 London, ward 2012 Belfast),
         street (nearest named OSM road within 60 m, keyed by name and postcode district), cell (grid id)
Outputs in data/<area>/analysis/:
  cert_enriched.parquet           every certificate with the fields above
  stock_current.parquet           the current stock: latest certificate per property among valid certificates
                                  (inspected on or after --valid-from: certificates are valid for 10 years)
  trends.csv                      per inspection year: count, mean SAP, band shares, CO2, fuels, heat pumps, PV,
                                  poor elements (all certificates of that year; not the whole stock)
  repeat_change.csv               properties with more than one certificate: SAP change between consecutive
                                  certificates, by period of the later certificate
  units_<unit>.parquet            per unit (nbhd, sector, street, la, cell): count, mean / median SAP, shares A-C,
                                  D-G, F-G, mean potential gap, CO2, poor element shares, fuels, PV; rank by mean SAP
                                  (1 = best) and, for cells, Getis-Ord Gi* z-scores of mean SAP and of the F-G share
  geometry_<unit>.parquet         unit geometries (WGS84) for maps: nbhd polygons, street lines, cell squares
  recommendations.parquet         (London) recommended measures of the current stock: cert_id, improvement, cost
  recs_summary.csv                (London) share of the current stock with each measure recommended
All outputs are archived before being replaced (safeio.keep).
"""
import argparse, io, pathlib, re, sys, zipfile
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

PHD = pathlib.Path(__file__).resolve().parents[2]
DATA = PHD / "data"
EPSG = {"london": 27700, "belfast": 29902}
OSM = {"london": DATA / "osm/geofabrik_greater-london_2026-10-20/greater-london-261020-free.shp.zip",
       "belfast": DATA / "osm/geofabrik_ireland_2026-10-20/ireland-and-northern-ireland-261020-free.shp.zip"}
REGISTER_EW = pathlib.Path(r"C:\Users\Owner\Downloads\domestic-csv.zip")
ELEMENTS = {"walls": "WALLS_ENERGY_EFF", "roof": "ROOF_ENERGY_EFF", "windows": "WINDOWS_ENERGY_EFF",
            "floor": "FLOOR_ENERGY_EFF", "mainheat": "MAINHEAT_ENERGY_EFF", "controls": "MAINHEATC_ENERGY_EFF",
            "hotwater": "HOT_WATER_ENERGY_EFF", "lighting": "LIGHTING_ENERGY_EFF"}
FUELS = ["gas", "electricity", "heat pump", "community", "oil", "solid", "LPG", "other"]
ROAD_CLASSES = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
                "service", "pedestrian", "road", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}
COLS = ["cert_id", "UPRN", "x", "y", "fp_id", "year", "inspection_date", "sap_score", "CURRENT_ENERGY_RATING",
        "POTENTIAL_ENERGY_EFFICIENCY", "CO2_EMISS_CURR_PER_FLOOR_AREA", "MAIN_FUEL", "MAINHEAT_DESCRIPTION",
        "PHOTO_SUPPLY", "SOLAR_WATER_HEATING_FLAG", "PROPERTY_TYPE", "BUILT_FORM", "FLOOR_LEVEL", "FLAT_TOP_STOREY",
        "TOTAL_FLOOR_AREA", "CONSTRUCTION_AGE_BAND", "TENURE", "POSTCODE", "LOCAL_AUTHORITY_LABEL", "is_latest"] + list(ELEMENTS.values())


def fuel_class(fuel, heat):
    f, h = fuel.fillna("").str.lower(), heat.fillna("").str.lower()
    # "mains gas (not community)" is the usual wording: only a positive "community" counts as community heating
    community = f.str.replace("not community", "", regex=False).str.contains("community") | h.str.contains("community scheme|community heating")
    out = np.select([h.str.contains("heat pump"), community,
                     f.str.contains("lpg|bottled|bulk"), f.str.contains("gas"), f.str.contains("electric"),
                     f.str.contains("oil"), f.str.contains("coal|anthracite|wood|smokeless|solid|dual fuel|biomass|peat")],
                    ["heat pump", "community", "LPG", "gas", "electricity", "oil", "solid"], "other")
    return pd.Series(out, index=fuel.index).where(f.ne("") | h.ne(""))


def floor_position(ptype, level, top):
    p = ptype.fillna("").str.lower()
    lv = level.fillna("").astype(str).str.strip().str.lower()
    t = top.fillna("").astype(str).str.upper()
    flat = p.isin(["flat", "maisonette"])
    num = pd.to_numeric(lv.str.extract(r"^-?(\d+)")[0], errors="coerce")
    ground = lv.str.contains("ground|basement") | lv.isin(["0", "00", "-1", "-01"]) | (num == 0)
    toplv = t.eq("Y") | lv.str.contains("top")
    middle = lv.str.contains("mid") | (num > 0)
    out = np.select([~flat, flat & toplv, flat & ground, flat & middle], ["house", "top", "ground", "middle"], "unknown")
    return pd.Series(out, index=ptype.index).where(p.ne(""))


def poor(s):
    v = s.fillna("").astype(str).str.strip().str.lower()
    return pd.Series(np.select([v.isin(["poor", "very poor"]), v.isin(["average", "good", "very good"])], [1.0, 0.0], np.nan), index=s.index)


def load(area):
    import pyarrow.parquet as pq
    have = pq.ParquetFile(DATA / area / "epc/certificates_linked.parquet").schema.names
    c = pd.read_parquet(DATA / area / "epc/certificates_linked.parquet", columns=[k for k in COLS if k in have])
    c = c[c["x"].notna()].copy()
    c["cert_id"] = c["cert_id"].astype(str)
    d = pd.DataFrame({"cert_id": c["cert_id"], "uprn": c["UPRN"].astype(str), "fp_id": c["fp_id"], "x": c["x"], "y": c["y"],
                      "year": c["year"].astype(int), "date": pd.to_datetime(c["inspection_date"], errors="coerce")})
    d["sap"] = pd.to_numeric(c["sap_score"], errors="coerce").astype("float64")
    d["band"] = c["CURRENT_ENERGY_RATING"].astype(str).str.upper().where(lambda s: s.isin(list("ABCDEFG")))
    d["potential_sap"] = pd.to_numeric(c["POTENTIAL_ENERGY_EFFICIENCY"], errors="coerce").astype("float64")
    d["potential_gap"] = (d["potential_sap"] - d["sap"]).clip(lower=0)
    d["co2_m2"] = pd.to_numeric(c["CO2_EMISS_CURR_PER_FLOOR_AREA"], errors="coerce").astype("float64")
    d["fuel"] = fuel_class(c["MAIN_FUEL"], c["MAINHEAT_DESCRIPTION"])
    d["pv"] = (pd.to_numeric(c["PHOTO_SUPPLY"], errors="coerce") > 0).astype(float).where(c["PHOTO_SUPPLY"].notna())
    d["solar_water"] = c["SOLAR_WATER_HEATING_FLAG"].astype(str).str.upper().map({"Y": 1.0, "N": 0.0})
    for k, col in ELEMENTS.items():
        d[f"poor_{k}"] = poor(c[col]) if col in c else np.nan
    d["property_type"] = c["PROPERTY_TYPE"]
    d["built_form"] = c["BUILT_FORM"]
    d["age_band"] = c["CONSTRUCTION_AGE_BAND"].astype(str).str.replace(r"^(England and Wales|Northern Ireland):\s*", "", regex=True)
    d["floor_area"] = pd.to_numeric(c["TOTAL_FLOOR_AREA"], errors="coerce").astype("float64")
    d["tenure"] = c["TENURE"]
    d["floor_pos"] = floor_position(c["PROPERTY_TYPE"], c["FLOOR_LEVEL"], c["FLAT_TOP_STOREY"])
    pc = c["POSTCODE"].astype(str).str.upper().str.replace(r"\s+", " ", regex=True).str.strip()
    d["sector"] = pc.str.extract(r"^([A-Z]{1,2}\d[A-Z\d]? \d)")[0]
    d["district"] = pc.str.extract(r"^([A-Z]{1,2}\d[A-Z\d]?)")[0]
    d["la"] = c["LOCAL_AUTHORITY_LABEL"] if "LOCAL_AUTHORITY_LABEL" in c else np.nan
    return d.reset_index(drop=True)


def add_nbhd(area, d):
    pts = gpd.GeoDataFrame(d[["cert_id"]], geometry=gpd.points_from_xy(d["x"], d["y"]), crs=EPSG[area])
    if area == "london":
        b = gpd.read_file(DATA / "london/boundaries_ons/lsoa21_bgc_v5_london.gpkg").to_crs(EPSG[area])
        b = b.rename(columns={"LSOA21CD": "nbhd", "LSOA21NM": "nbhd_name"})
    else:
        z = DATA / "belfast/boundaries_osni/osni_open_data_largescale_boundaries_wards_2012.zip"
        shp = [n for n in zipfile.ZipFile(z).namelist() if n.lower().endswith(".shp")][0]
        b = gpd.read_file(f"zip://{z.as_posix()}!{shp}").to_crs(EPSG[area])
        code = next(c for c in b.columns if re.search(r"code|cd$", c, re.I))
        name = next(c for c in b.columns if re.search(r"name|nm$", c, re.I))
        b = b.rename(columns={code: "nbhd", name: "nbhd_name"})
    j = gpd.sjoin(pts, b[["nbhd", "nbhd_name", "geometry"]], how="left", predicate="within").drop_duplicates("cert_id")
    d["nbhd"] = j["nbhd"].to_numpy(); d["nbhd_name"] = j["nbhd_name"].to_numpy()
    return b[["nbhd", "nbhd_name", "geometry"]]


def add_streets(area, d):
    """Nearest named OSM road within 60 m of the address point; street = road name + postcode district."""
    x0, y0, x1, y1 = d["x"].min() - 500, d["y"].min() - 500, d["x"].max() + 500, d["y"].max() + 500
    bb = gpd.GeoSeries([shapely.box(x0, y0, x1, y1)], crs=EPSG[area]).to_crs(4326).total_bounds
    z = OSM[area]
    r = gpd.read_file(f"zip://{z.as_posix()}!gis_osm_roads_free_1.shp", bbox=tuple(bb), columns=["osm_id", "name", "fclass"])
    r = r[r["name"].notna() & r["fclass"].isin(ROAD_CLASSES)].to_crs(EPSG[area]).reset_index(drop=True)
    tree = shapely.STRtree(r.geometry.values)
    pts = shapely.points(d["x"].to_numpy(), d["y"].to_numpy())
    (ip, ir), dist = tree.query_nearest(pts, max_distance=60, return_distance=True, all_matches=False)
    name = np.full(len(d), None, dtype=object); seg = np.full(len(d), -1)
    name[ip] = r["name"].to_numpy()[ir]; seg[ip] = ir
    d["street"] = pd.Series(name).str.strip() + " | " + d["district"].fillna("?")
    d.loc[pd.Series(name).isna().to_numpy(), "street"] = np.nan
    d["street_dist_m"] = np.nan; d.loc[ip, "street_dist_m"] = dist
    # street geometry: the road segments that are nearest to at least one certificate of that street
    s = pd.DataFrame({"street": d["street"], "seg": seg}).query("seg >= 0").drop_duplicates()
    geo = s.groupby("street")["seg"].apply(lambda ix: shapely.union_all(r.geometry.values[ix.to_numpy()]))
    return gpd.GeoDataFrame({"street": geo.index}, geometry=list(geo.values), crs=EPSG[area])


def grouped(df, key):
    """summarise() for every group, vectorised enough for 2.5 million rows."""
    g = df.groupby(key, sort=False)
    b = df["band"]
    out = pd.DataFrame({"n": g.size(), "sap_mean": g["sap"].mean(), "sap_median": g["sap"].median(),
                        "share_AC": b.isin(list("ABC")).groupby(df[key]).mean(),
                        "share_DG": b.isin(list("DEFG")).groupby(df[key]).mean(),
                        "share_FG": b.isin(list("FG")).groupby(df[key]).mean(),
                        "potential_gap": g["potential_gap"].mean(), "co2_m2": g["co2_m2"].median(), "pv": g["pv"].mean(),
                        "floor_area": g["floor_area"].median()})
    for k in ELEMENTS:
        out[f"poor_{k}"] = g[f"poor_{k}"].mean()
    for k in FUELS:
        out[f"fuel_{k.replace(' ', '_')}"] = df["fuel"].eq(k).groupby(df[key]).mean()
    return out


def gi_star(cells, value, size):
    """Getis-Ord Gi* z-score per grid cell, neighbours = the 8 surrounding cells and the cell itself."""
    import warnings
    from libpysal.weights import DistanceBand, fill_diagonal
    from esda.getisord import G_Local
    xy = np.column_stack([cells["cx"], cells["cy"]])
    v = cells[value].to_numpy("float64")
    ok = np.isfinite(v)
    z = np.full(len(v), np.nan)
    if ok.sum() > 10:
        with warnings.catch_warnings():              # isolated cells (no neighbour within 1.5 cells) get no z-score
            warnings.simplefilter("ignore")
            w = fill_diagonal(DistanceBand(xy[ok], threshold=size * 1.5, binary=True, silence_warnings=True), 1)
            zs = G_Local(v[ok], w, star=None, transform="B", permutations=0).Zs
        isolated = np.array([len(w.neighbors[i]) <= 1 for i in w.id_order])
        z[np.flatnonzero(ok)] = np.where(isolated, np.nan, zs)
    return z


def recommendations(ids):
    """England and Wales recommendations of these certificates, streamed from the register zip."""
    import pyarrow.csv as pc
    import pyarrow as pa
    ids = pa.array(sorted(ids))
    parts = []
    with zipfile.ZipFile(REGISTER_EW) as z:
        for n in sorted(m for m in z.namelist() if "recommend" in m.lower()):
            with z.open(n) as f:
                r = pc.open_csv(f, read_options=pc.ReadOptions(block_size=1 << 26),
                                convert_options=pc.ConvertOptions(column_types={c: pa.string() for c in
                                    ["certificate_number", "improvement_item", "improvement_id", "improvement_summary_text",
                                     "improvement_descr_text", "indicative_cost"]}))
                for batch in r:
                    t = pa.Table.from_batches([batch])
                    m = pa.compute.is_in(t["certificate_number"], value_set=ids)
                    t = t.filter(m)
                    if t.num_rows:
                        parts.append(t.select(["certificate_number", "improvement_id", "improvement_summary_text", "indicative_cost"]).to_pandas())
            print("  recommendations:", n, sum(len(p) for p in parts), flush=True)
    r = pd.concat(parts, ignore_index=True).rename(columns={"certificate_number": "cert_id"})
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--valid-from", default="2016-10-23")
    ap.add_argument("--grid", type=int, default=250); ap.add_argument("--no-recs", action="store_true")
    a = ap.parse_args()
    out = DATA / a.area / "analysis"; out.mkdir(parents=True, exist_ok=True)
    d = load(a.area)
    print(f"{a.area}: {len(d):,} certificates with a location", flush=True)
    nb = add_nbhd(a.area, d)
    streets = add_streets(a.area, d)
    d["cell"] = (np.floor(d["x"] / a.grid).astype(int)).astype(str) + "_" + (np.floor(d["y"] / a.grid).astype(int)).astype(str)
    print(f"  neighbourhood found {d['nbhd'].notna().mean():.1%}, street {d['street'].notna().mean():.1%}, "
          f"sector {d['sector'].notna().mean():.1%}", flush=True)
    d.to_parquet(keep(out / "cert_enriched.parquet"), index=False)

    # trends by inspection year (certificates of that year, not the whole stock)
    t = grouped(d.assign(yr=d["year"]), "yr").sort_index()
    t.index.name = "year"
    t.round(4).to_csv(keep(out / "trends.csv"))

    # change between consecutive certificates of the same property
    r = d[d["sap"].notna() & d["date"].notna()].sort_values(["uprn", "date"])
    r = r[r["uprn"].ne("nan") & r["uprn"].ne("None")]
    prev = r.groupby("uprn")[["sap", "date", "fuel", "pv"]].shift()
    ch = pd.DataFrame({"uprn": r["uprn"], "year": r["year"], "sap_change": r["sap"] - prev["sap"],
                       "years_between": (r["date"] - prev["date"]).dt.days / 365.25,
                       "to_heat_pump": (r["fuel"].eq("heat pump") & prev["fuel"].ne("heat pump") & prev["fuel"].notna()).astype(float),
                       "new_pv": ((r["pv"] == 1) & (prev["pv"] == 0)).astype(float)})
    ch = ch[ch["sap_change"].notna() & (ch["years_between"] > 0.25)]
    ch["period"] = pd.cut(ch["year"], [2007, 2012, 2016, 2020, 2023, 2027], labels=["2008-12", "2013-16", "2017-20", "2021-23", "2024-26"])
    rc = ch.groupby("period", observed=True).agg(pairs=("sap_change", "size"), sap_change_mean=("sap_change", "mean"),
                                                 sap_change_median=("sap_change", "median"),
                                                 sap_change_per_year=("sap_change", lambda s: (s / ch.loc[s.index, "years_between"]).median()),
                                                 share_improved=("sap_change", lambda s: (s > 0).mean()),
                                                 to_heat_pump=("to_heat_pump", "mean"), new_pv=("new_pv", "mean"))
    rc.round(4).to_csv(keep(out / "repeat_change.csv"))

    # current stock: latest valid certificate per property
    cur = d[d["date"] >= pd.Timestamp(a.valid_from)].sort_values("date").drop_duplicates("uprn", keep="last")
    cur.to_parquet(keep(out / "stock_current.parquet"), index=False)
    print(f"  current stock (valid certificates since {a.valid_from}): {len(cur):,} properties", flush=True)

    units = {"nbhd": "nbhd", "sector": "sector", "street": "street", "cell": "cell"}
    if a.area == "london":
        units["la"] = "la"
    for unit, key in units.items():
        u = grouped(cur[cur[key].notna()], key)
        u = u[u["n"] >= 5].copy()
        u["rank_sap"] = u["sap_mean"].rank(ascending=False, method="min").astype(int)
        if unit == "cell":
            ij = u.index.to_series().str.split("_", expand=True).astype(int)
            u["cx"], u["cy"] = (ij[0] + 0.5) * a.grid, (ij[1] + 0.5) * a.grid
            u["gi_sap"] = gi_star(u, "sap_mean", a.grid)
            u["gi_FG"] = gi_star(u, "share_FG", a.grid)
        if unit == "nbhd":
            u = u.join(nb.drop_duplicates("nbhd").set_index("nbhd")["nbhd_name"])
        u.index.name = unit
        u.round(4).reset_index().to_parquet(keep(out / f"units_{unit}.parquet"), index=False)
        print(f"  {unit}: {len(u):,} units with at least 5 properties", flush=True)

    # geometries for maps (WGS84)
    nb.to_crs(4326).to_parquet(keep(out / "geometry_nbhd.parquet"))
    streets.assign(geometry=streets.geometry.simplify(2)).to_crs(4326).to_parquet(keep(out / "geometry_street.parquet"))

    if a.area == "london" and not a.no_recs and REGISTER_EW.exists():
        rec = recommendations(set(cur["cert_id"]))
        rec.to_parquet(keep(out / "recommendations.parquet"), index=False)
        s = (rec.drop_duplicates(["cert_id", "improvement_summary_text"])
             .groupby("improvement_summary_text")["cert_id"].size().sort_values(ascending=False) / len(cur))
        s.rename("share_of_current_stock").round(4).to_csv(keep(out / "recs_summary.csv"))
        print(f"  recommendations: {len(rec):,} for {rec['cert_id'].nunique():,} properties", flush=True)
    print("written", out)


if __name__ == "__main__":
    main()
