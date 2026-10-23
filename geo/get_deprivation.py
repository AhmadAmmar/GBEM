"""Area deprivation for both study areas (open data):
  London   English Indices of Deprivation 2025 (MHCLG), LSOA 2021: File 7, all ranks, scores, deciles and population
           denominators (Open Government Licence v3.0)
  Belfast  Northern Ireland Multiple Deprivation Measure 2017 (NISRA), Small Area (SA2011) results, with the SA2011
           boundaries (NISRA, Open Government Licence)

    python get_deprivation.py

Raw files are kept unchanged in data/<area>/deprivation/raw/ (SOURCE.txt, SHA256SUMS.txt); an existing download is
never replaced. Outputs:
  data/london/deprivation/imd2025_lsoa_london.parquet   lsoa, imd_score, imd_rank, imd_decile and, for each domain,
                                                        score / rank / decile (income, employment, education, health,
                                                        crime, barriers, living environment and its indoors and
                                                        outdoors sub-domains where present); ranks: 1 = most deprived
                                                        of 33,755 English LSOAs
  data/belfast/deprivation/nimdm2017_sa.gpkg            SA2011 polygons with MDM and domain ranks (1 = most deprived
                                                        of 4,537 NI Small Areas) and deciles computed from the ranks
The two measures differ in year, indicators and units (LSOA vs Small Area): compare within each area (ranks / deciles),
not their values across areas.
"""
import datetime, hashlib, pathlib, re, sys, urllib.request, zipfile
import pandas as pd
import geopandas as gpd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

PHD = pathlib.Path(__file__).resolve().parents[2]
SRC = {
    "london": {"File_7_IoD2025_All_Ranks_Scores_Deciles_Population_Denominators.csv":
               "https://assets.publishing.service.gov.uk/media/691ded56d140bbbaa59a2a7d/File_7_IoD2025_All_Ranks_Scores_Deciles_Population_Denominators.csv"},
    "belfast": {"NIMDM17_SA - for publication.xls": "https://www.nisra.gov.uk/files/nisra/publications/NIMDM17_SA%20-%20for%20publication.xls",
                "SA2011_Esri_Shapefile_0.zip": "https://www.nisra.gov.uk/files/nisra/publications/SA2011_Esri_Shapefile_0.zip"}}
CREDIT = {"london": "Ministry of Housing, Communities and Local Government, English Indices of Deprivation 2025. "
                    "Open Government Licence v3.0.",
          "belfast": "NISRA, Northern Ireland Multiple Deprivation Measure 2017 (Small Area results) and Small Area "
                     "boundaries 2011. Open Government Licence v3.0."}


def download(area):
    raw = PHD / "data" / area / "deprivation/raw"; raw.mkdir(parents=True, exist_ok=True)
    for name, url in SRC[area].items():
        dest = raw / name
        if dest.exists():
            print("already downloaded:", name); continue
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research data download)"})
        with urllib.request.urlopen(req, timeout=600) as r:
            data = r.read()
        tmp = dest.with_suffix(dest.suffix + ".part"); tmp.write_bytes(data); tmp.rename(dest)
        print("downloaded:", name, round(len(data) / 1e6, 1), "MB")
    (raw / "SOURCE.txt").write_text(CREDIT[area] + "\n" + "".join(f"{n}: {u}\n" for n, u in SRC[area].items())
                                    + f"Downloaded {datetime.date.today()}\n", encoding="utf-8")
    (raw / "SHA256SUMS.txt").write_text("".join(f"{hashlib.sha256((raw / n).read_bytes()).hexdigest()}  {n}\n" for n in SRC[area]), encoding="utf-8")
    return raw


def snake(c):
    c = re.sub(r"\(.*?\)", "", c).lower()
    c = c.replace("index of multiple deprivation", "imd").replace("living environment", "living_env")
    c = c.replace("income deprivation affecting children index", "idaci").replace("income deprivation affecting older people index", "idaopi")
    c = c.replace("education, skills and training", "education").replace("health deprivation and disability", "health")
    c = c.replace("barriers to housing and services", "barriers").replace("sub-domain", "").replace("domain", "")
    c = re.sub(r"[^a-z0-9]+", "_", c).strip("_")
    c = c.replace("_where_1_is_most_deprived", "").replace("_where_1_is_most_deprived_10", "")
    return c


def london():
    raw = download("london")
    d = pd.read_csv(raw / next(iter(SRC["london"])))
    code = next(c for c in d.columns if re.search(r"LSOA code", c, re.I))
    lsoas = set(gpd.read_file(PHD / "data/london/boundaries_ons/lsoa21_bgc_v5_london.gpkg")["LSOA21CD"])
    d = d[d[code].isin(lsoas)]
    keepcols = [c for c in d.columns if re.search(r"(Score|Rank|Decile)", c)]
    out = d[[code] + keepcols].rename(columns={code: "lsoa"})
    out.columns = ["lsoa"] + [snake(c) for c in keepcols]
    dest = PHD / "data/london/deprivation/imd2025_lsoa_london.parquet"
    out.to_parquet(keep(dest), index=False)
    print(f"London: {len(out):,} LSOAs, {out.shape[1] - 1} columns, e.g. {list(out.columns[1:8])} -> {dest}")


def belfast():
    raw = download("belfast")
    x = pd.read_excel(raw / "NIMDM17_SA - for publication.xls", sheet_name=None)
    sheet = max(x, key=lambda s: len(x[s]))                       # the results sheet: one row per Small Area
    t = x[sheet]
    hdr = next(i for i in range(min(10, len(t))) if t.iloc[i].astype(str).str.contains("SA2011", case=False).any()) if not any("SA2011" in str(c) for c in t.columns) else None
    if hdr is not None:
        t = pd.read_excel(raw / "NIMDM17_SA - for publication.xls", sheet_name=sheet, header=hdr + 1)
    t.columns = [str(c).strip() for c in t.columns]
    sa = next(c for c in t.columns if re.fullmatch(r"SA2011", c, re.I) or re.search(r"SA2011", c, re.I))
    ranks = [c for c in t.columns if re.search(r"rank", c, re.I)]
    out = t[[sa] + ranks].rename(columns={sa: "SA2011"})
    out.columns = ["SA2011"] + [snake(c) for c in ranks]
    n = len(out)
    for c in out.columns[1:]:
        out[c.replace("rank", "decile")] = (pd.to_numeric(out[c], errors="coerce") - 1) // (n / 10) + 1
    z = raw / "SA2011_Esri_Shapefile_0.zip"
    shp = [m for m in zipfile.ZipFile(z).namelist() if m.lower().endswith(".shp")][0]
    g = gpd.read_file(f"zip://{z.as_posix()}!{shp}")
    gcode = next(c for c in g.columns if re.search(r"SA2011|SA_CODE", c, re.I))
    g = g[[gcode, "geometry"]].rename(columns={gcode: "SA2011"}).merge(out, on="SA2011", how="left")
    dest = PHD / "data/belfast/deprivation/nimdm2017_sa.gpkg"
    if dest.exists():
        keep(dest)
    g.to_file(dest, driver="GPKG")
    print(f"Belfast: {len(g):,} Small Areas ({g[out.columns[1]].notna().sum():,} with MDM), columns {list(out.columns)} -> {dest}")


if __name__ == "__main__":
    london(); belfast()
