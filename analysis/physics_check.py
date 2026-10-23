"""Physics check: does a simple heat-loss calculation from EO-derived geometry agree with the certificates?

    python physics_check.py --area belfast|london [--valid-from 2016-10-23]

For every current-stock certificate (analysis/stock.py) whose building has a footprint:
1. Geometry check. Floor area per dwelling from the footprint and LiDAR (epc/physics.py: footprint area x storeys /
   addresses) against the floor area measured by the assessor (TOTAL_FLOOR_AREA): ratio and rank correlation, by
   property type.
2. Dwelling envelope. Houses and bungalows: the building's exposed walls, roof and ground floor (per address if the
   footprint has several). Flats and maisonettes: per dwelling, the building's exposed wall area divided by the
   dwellings in the footprint; roof only for a top-floor dwelling and ground floor only for a ground-floor dwelling,
   each the footprint area divided by the dwellings per storey (floor position from the certificate).
3. U-values (W/m2K), two variants:
   as_described  from the certificate's element descriptions (walls: solid / cavity / timber / system, insulated or
                 filled or not, or the stated average thermal transmittance; roof: loft insulation thickness, flat,
                 pitched, dwelling above; floor: solid / suspended, insulated, dwelling below; glazing type)
   as_built      from the construction age band only (typical as-built values: what is known without a survey)
   The values are rounded typical figures in the spirit of the RdSAP default tables (BRE), not the official tables:
   see U_* below; they are meant for ranking, not for compliance.
4. Heat-loss coefficient HLC (W/K) = sum(U x A) + thermal bridging (y x envelope, y = 0.15 before 2003, 0.08 after)
   + ventilation 0.33 x n x V (air changes n = 1.0 before 1976, 0.7 to 2002, 0.5 after); windows 18% of the floor
   area, taken out of the wall area.
5. Annual space-heating demand Q = HLC x HDD x 24 / 1000 (kWh) with heating degree-days HDD of 2024 from ERA5 at the
   home (base 15.5 C), per m2 of the certificate's floor area.
Compared with the certificate's SAP score and energy consumption (kWh/m2/yr, primary energy: heating, hot water,
lighting): Spearman correlations overall and by property type.
Outputs in data/<area>/analysis/: physics_check.csv (correlations), physics_geometry.csv (floor-area check),
physics_cert.parquet (per certificate: geometry, U-values, HLC, Q)
"""
import argparse, pathlib, re, sys
import numpy as np
import pandas as pd
from scipy import stats
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "epc"))
from safeio import keep                      # existing outputs are archived, never overwritten
import physics as PH

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"
# typical as-built U-values by the first year of the construction age band (W/m2K)
U_WALL_AGE = [(0, 2.1), (1930, 1.6), (1976, 1.0), (1983, 0.6), (1996, 0.45), (2003, 0.35), (2007, 0.30), (2012, 0.26)]
U_ROOF_AGE = [(0, 2.3), (1967, 1.5), (1976, 0.8), (1983, 0.5), (1991, 0.35), (2003, 0.25), (2007, 0.16)]
U_FLOOR_AGE = [(0, 0.7), (1983, 0.6), (1996, 0.45), (2003, 0.25), (2007, 0.22)]
U_WIN_AGE = [(0, 2.8), (2003, 2.0), (2010, 1.6)]


def by_year(table, year):
    y = np.nan_to_num(np.asarray(year, float), nan=1950)
    out = np.full(len(y), table[0][1])
    for start, u in table:
        out = np.where(y >= start, u, out)
    return out


def first_year(age):
    s = pd.Series(age).astype("string").fillna("")
    y = pd.to_numeric(s.str.extract(r"(\d{4})")[0], errors="coerce")
    return y.where(~s.str.contains("before", case=False), y - 30)


def stated_u(desc):
    """'Average thermal transmittance 0.28 W/m-¦K' -> 0.28"""
    v = pd.to_numeric(desc.str.extract(r"transmittance\s*([0-9.]+)", flags=re.I)[0], errors="coerce")
    return v.where(v < 6)


def u_wall(desc, year):
    d = desc.fillna("").str.lower()
    base = by_year(U_WALL_AGE, year)
    u = np.select([d.str.contains("solid") & d.str.contains("insulated") & ~d.str.contains("no insulation"),
                   d.str.contains("solid"),
                   d.str.contains("cavity") & d.str.contains("filled"),
                   d.str.contains("cavity") & d.str.contains("insulated") & ~d.str.contains("no insulation"),
                   d.str.contains("cavity"),
                   d.str.contains("timber") & d.str.contains("insulated") & ~d.str.contains("no insulation"),
                   d.str.contains("timber"), d.str.contains("system built|granite|sandstone|cob|park home")],
                  [0.45, 2.1, 0.7, 0.5, 1.5, 0.4, 1.9, 1.7], base)
    return pd.Series(u, index=desc.index).where(stated_u(desc).isna(), stated_u(desc))


def u_roof(desc, year):
    d = desc.fillna("").str.lower()
    mm = pd.to_numeric(d.str.extract(r"(\d+)\s*\+?\s*mm")[0], errors="coerce")
    loft = 1 / (0.25 + (mm.fillna(0) / 1000) / 0.04)                   # mineral wool, lambda 0.04 W/mK
    u = np.select([d.str.contains("dwelling above|other premises above|another dwelling above"),
                   mm.notna(), d.str.contains("no insulation"), d.str.contains("limited insulation"),
                   d.str.contains("insulated")],
                  [0.0, loft, 2.3, 1.5, 0.25], by_year(U_ROOF_AGE, year))
    return pd.Series(u, index=desc.index).where(stated_u(desc).isna(), stated_u(desc))


def u_floor(desc, year):
    d = desc.fillna("").str.lower()
    u = np.select([d.str.contains("dwelling below|other premises below|another dwelling below"),
                   d.str.contains("insulated") & ~d.str.contains("no insulation"),
                   d.str.contains("suspended"), d.str.contains("solid")],
                  [0.0, 0.25, 0.7, 0.6], by_year(U_FLOOR_AGE, year))
    return pd.Series(u, index=desc.index).where(stated_u(desc).isna(), stated_u(desc))


def u_window(glazed, year):
    g = glazed.fillna("").str.lower()
    u = np.select([g.str.contains("triple"), g.str.contains("during or after|after 2002|secondary") & g.str.contains("double"),
                   g.str.contains("double"), g.str.contains("single")], [1.6, 2.0, 2.8, 4.8], by_year(U_WIN_AGE, year))
    return pd.Series(u, index=glazed.index)


def heat(env, U, year, volume, hdd):
    wall, roof, floor, win = env
    uw, ur, uf, uwin = U
    y = np.nan_to_num(np.asarray(year, float), nan=1950)
    bridge = np.where(y >= 2003, 0.08, 0.15) * (wall + roof + floor + win)
    ach = np.select([y >= 2003, y >= 1976], [0.5, 0.7], 1.0)
    hlc = uw * wall + ur * roof + uf * floor + uwin * win + bridge + 0.33 * ach * volume
    return hlc, hlc * hdd * 24 / 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True)
    a = ap.parse_args()
    out = DATA / a.area / "analysis"
    cur = pd.read_parquet(out / "stock_current.parquet", columns=["cert_id", "fp_id", "sap", "property_type", "floor_pos", "floor_area", "age_band", "year"])
    cert = pd.read_parquet(DATA / a.area / "epc/certificates_linked.parquet",
                           columns=["cert_id", "WALLS_DESCRIPTION", "ROOF_DESCRIPTION", "FLOOR_DESCRIPTION", "GLAZED_TYPE", "ENERGY_CONSUMPTION_CURRENT"])
    cert["cert_id"] = cert["cert_id"].astype(str)
    d = cur.merge(cert.drop_duplicates("cert_id"), on="cert_id", how="left")
    b = PH.building_height(a.area)
    d = d.merge(b, on="fp_id", how="inner")
    # heating degree-days at the home (ERA5, 2024): from the modelling tables where present, else the area median
    hdd = []
    for y in range(2020, 2026):
        p = DATA / a.area / "model" / f"dataset_{y}.parquet"
        if p.exists():
            hdd.append(pd.read_parquet(p, columns=["id_cert", "era5_HDD_annual_pt"]).rename(columns={"id_cert": "cert_id"}))
    hdd = pd.concat(hdd).drop_duplicates("cert_id")
    d = d.merge(hdd, on="cert_id", how="left")
    d["HDD"] = d["era5_HDD_annual_pt"].fillna(d["era5_HDD_annual_pt"].median())
    print(f"{a.area}: {len(d):,} current certificates with a footprint; HDD median {d['HDD'].median():.0f}", flush=True)
    # geometry: building -> dwelling
    n = d["n_uprn"].fillna(1).clip(lower=1)
    g = PH.geometry(d["area_m2"], d["perimeter_m"], d["shared_wall_m"], d["H"], n)
    storeys = g["storeys"]
    per_storey = np.clip(np.round(n / storeys), 1, None)
    flat = d["property_type"].isin(["Flat", "Maisonette"]).to_numpy()
    pos = d["floor_pos"].fillna("unknown").to_numpy()
    d["eo_floor_per_dw_m2"] = g["floor_per_dw_m2"]
    wall = g["wall_ext_m2"] / n
    roof = np.where(flat, np.where(pos == "top", d["area_m2"] / per_storey, 0.0), d["area_m2"] / n)
    floor = np.where(flat, np.where(pos == "ground", d["area_m2"] / per_storey, 0.0), d["area_m2"] / n)
    tfa = d["floor_area"].where(d["floor_area"] > 10)                    # the certificate's floor area, for per-m2 values
    win = 0.18 * tfa.fillna(pd.Series(g["floor_per_dw_m2"], index=d.index))
    wall = np.clip(wall - win, 0, None)
    vol = tfa.fillna(pd.Series(g["floor_per_dw_m2"], index=d.index)) * PH.STOREY_M
    yr = first_year(d["age_band"]).to_numpy()
    res = {}
    for name, U in (("as_described", (u_wall(d["WALLS_DESCRIPTION"], yr), u_roof(d["ROOF_DESCRIPTION"], yr),
                                      u_floor(d["FLOOR_DESCRIPTION"], yr), u_window(d["GLAZED_TYPE"], yr))),
                    ("as_built", tuple(pd.Series(by_year(t, yr), index=d.index) for t in (U_WALL_AGE, U_ROOF_AGE, U_FLOOR_AGE, U_WIN_AGE)))):
        hlc, q = heat((wall, roof, floor, win), U, yr, vol, d["HDD"].to_numpy())
        d[f"hlc_{name}"] = hlc
        d[f"q_{name}_kwh_m2"] = q / tfa
        if name == "as_described":
            for k, u in zip(("wall", "roof", "floor", "window"), U):
                d[f"u_{k}"] = u
    d["energy_m2"] = pd.to_numeric(d["ENERGY_CONSUMPTION_CURRENT"], errors="coerce")
    # 1. geometry check
    geo = []
    for k, s in [("all", d)] + list(d.groupby("property_type")):
        s = s[s["floor_area"].notna() & np.isfinite(s["eo_floor_per_dw_m2"])]
        if len(s) < 50:
            continue
        r = s["eo_floor_per_dw_m2"] / s["floor_area"]
        geo.append({"group": k, "n": len(s), "spearman_eo_vs_certificate_floor_area": stats.spearmanr(s["eo_floor_per_dw_m2"], s["floor_area"])[0],
                    "median_ratio_eo_to_certificate": r.median(), "share_within_25pct": float(((r > 0.75) & (r < 1.25)).mean())})
    geo = pd.DataFrame(geo)
    geo.round(3).to_csv(keep(out / "physics_geometry.csv"), index=False)
    print(geo.round(3).to_string(index=False))
    # 2-5. heat demand vs certificate
    rows = []
    for k, s in [("all", d)] + list(d.groupby("property_type")):
        for v in ("as_described", "as_built"):
            q = s[f"q_{v}_kwh_m2"]
            ok = q.notna() & np.isfinite(q) & s["sap"].notna()
            if ok.sum() < 50:
                continue
            ok2 = ok & s["energy_m2"].notna()
            rows.append({"group": k, "u_values": v, "n": int(ok.sum()), "q_median_kwh_m2": q[ok].median(),
                         "spearman_q_vs_sap": stats.spearmanr(q[ok], s.loc[ok, "sap"])[0],
                         "spearman_q_vs_energy_m2": stats.spearmanr(q[ok2], s.loc[ok2, "energy_m2"])[0] if ok2.sum() > 50 else np.nan})
    chk = pd.DataFrame(rows)
    chk.round(3).to_csv(keep(out / "physics_check.csv"), index=False)
    print(chk.round(3).to_string(index=False))
    keepcols = ["cert_id", "fp_id", "property_type", "floor_pos", "sap", "energy_m2", "floor_area", "eo_floor_per_dw_m2", "H", "H_source",
                "u_wall", "u_roof", "u_floor", "u_window", "hlc_as_described", "hlc_as_built", "q_as_described_kwh_m2", "q_as_built_kwh_m2", "HDD"]
    d[keepcols].to_parquet(keep(out / "physics_cert.parquet"), index=False)
    print("written", out)


if __name__ == "__main__":
    main()
