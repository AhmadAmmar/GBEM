"""Measured domestic energy use per small area (England and Wales): DESNZ sub-national gas and electricity
consumption by LSOA, 2010-2024 (Open Government Licence v3.0).

    python get_desnz_energy.py            download (once) and build the London table

Sources (gov.uk statistics "Lower and Middle Super Output Areas gas / electricity consumption"):
  LSOA_domestic_gas_2010-2024.xlsx, LSOA_domestic_elec_2010-2024.xlsx
The raw files are kept unchanged in data/london/energy_desnz/raw/ with SOURCE.txt and SHA256SUMS.txt; an existing
download is never replaced.
Output: data/london/energy_desnz/lsoa_energy_london.parquet: one row per LSOA, year and fuel (gas, electricity) with
meters, total kWh, mean and median kWh per meter, for the LSOAs of Greater London (boundaries_ons). Gas years are
weather-corrected by DESNZ; years run mid-May to mid-May for gas and calendar years for electricity (see the source).
"""
import datetime, hashlib, pathlib, re, sys, urllib.request
import pandas as pd
import geopandas as gpd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

PHD = pathlib.Path(__file__).resolve().parents[2]
OUT = PHD / "data/london/energy_desnz"
FILES = {"gas": "https://assets.publishing.service.gov.uk/media/694578171a2e540ccd8a5426/LSOA_domestic_gas_2010-2024.xlsx",
         "electricity": "https://assets.publishing.service.gov.uk/media/69427b7bd8156a816c419351/LSOA_domestic_elec_2010-2024.xlsx"}


def download():
    raw = OUT / "raw"; raw.mkdir(parents=True, exist_ok=True)
    for fuel, url in FILES.items():
        dest = raw / url.rsplit("/", 1)[-1]
        if dest.exists():
            print("already downloaded:", dest.name); continue
        tmp = dest.with_suffix(".part")
        with urllib.request.urlopen(url, timeout=600) as r, open(tmp, "wb") as f:
            f.write(r.read())
        tmp.rename(dest)
        print("downloaded:", dest.name, round(dest.stat().st_size / 1e6, 1), "MB")
    (raw / "SOURCE.txt").write_text(
        "Department for Energy Security and Net Zero (DESNZ), sub-national energy consumption statistics:\n"
        "Lower and Middle Super Output Areas gas consumption; Lower and Middle Super Output Areas electricity consumption.\n"
        "Contains public sector information licensed under the Open Government Licence v3.0.\n"
        + "".join(f"{u}\n" for u in FILES.values()) + f"Downloaded {datetime.date.today()}\n", encoding="utf-8")
    (raw / "SHA256SUMS.txt").write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n"
                                                for p in sorted(raw.glob("*.xlsx"))), encoding="utf-8")


def read(fuel, path, lsoas):
    """One sheet per year; the header row is found by its LSOA code column."""
    xl = pd.ExcelFile(path)
    out = []
    for sh in xl.sheet_names:
        m = re.search(r"(20\d\d)", sh)
        if not m:
            continue
        head = pd.read_excel(xl, sh, header=None, nrows=15)
        hr = next(i for i in range(len(head)) if head.iloc[i].astype(str).str.strip().str.lower().eq("lsoa code").any())
        t = pd.read_excel(xl, sh, header=hr)
        t.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in t.columns]      # names contain line breaks
        code = next(c for c in t.columns if c.lower() == "lsoa code")
        pick = lambda pat: next((c for c in t.columns if re.search(pat, c, re.I)), None)
        meters, total, mean, median = pick(r"^number of meters"), pick(r"^total consumption"), pick(r"^mean"), pick(r"^median")
        t = t[t[code].isin(lsoas)]
        out.append(pd.DataFrame({"lsoa": t[code], "year": int(m.group(1)), "fuel": fuel,
                                 "meters": pd.to_numeric(t[meters], errors="coerce") if meters else None,
                                 "total_kwh": pd.to_numeric(t[total], errors="coerce") if total else None,
                                 "mean_kwh": pd.to_numeric(t[mean], errors="coerce") if mean else None,
                                 "median_kwh": pd.to_numeric(t[median], errors="coerce") if median else None}))
        print(f"  {fuel} {sh}: {len(t):,} London LSOAs (code column '{code}')", flush=True)
    return pd.concat(out, ignore_index=True)


def main():
    download()
    lsoas = set(gpd.read_file(PHD / "data/london/boundaries_ons/lsoa21_bgc_v5_london.gpkg")["LSOA21CD"])
    frames = [read(f, OUT / "raw" / u.rsplit("/", 1)[-1], lsoas) for f, u in FILES.items()]
    d = pd.concat(frames, ignore_index=True)
    d.to_parquet(keep(OUT / "lsoa_energy_london.parquet"), index=False)
    s = d.groupby(["fuel", "year"]).agg(lsoas=("lsoa", "nunique"), meters=("meters", "sum"), mean_kwh=("mean_kwh", "median"))
    print(s.to_string())
    print("written", OUT / "lsoa_energy_london.parquet")


if __name__ == "__main__":
    main()
