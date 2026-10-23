"""Official fuel poverty estimates for small areas in England (DESNZ, sub-regional fuel poverty data 2026, 2024 data;
Open Government Licence v3.0; official statistics in development).

    python get_fuel_poverty.py

Fuel poverty here is the Low Income Low Energy Efficiency (LILEE) metric: a household is fuel poor if it lives in a
home with a fuel poverty energy efficiency rating of band D or below and its disposable income after housing and
energy costs is below the poverty line. The efficiency part makes any comparison with efficiency-based targeting
partly circular; DESNZ advises using the small-area estimates for broad patterns only.
Raw file kept unchanged in data/london/fuel_poverty/raw/ (SOURCE.txt, SHA256SUMS.txt). Output:
data/london/fuel_poverty/fuel_poverty_lsoa_london.parquet (lsoa, households, fuel_poor, share_fuel_poor) for the London
LSOAs found in the tables.
"""
import datetime, hashlib, pathlib, re, sys, urllib.request
import pandas as pd
import geopandas as gpd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

PHD = pathlib.Path(__file__).resolve().parents[2]
OUT = PHD / "data/london/fuel_poverty"
URL = "https://assets.publishing.service.gov.uk/media/6a02febf81a251700a20b42a/fuel-poverty-sub-regional-2026-2024-data-tables.xlsx"


def main():
    raw = OUT / "raw"; raw.mkdir(parents=True, exist_ok=True)
    dest = raw / URL.rsplit("/", 1)[-1]
    if not dest.exists():
        tmp = dest.with_suffix(".part")
        with urllib.request.urlopen(URL, timeout=600) as r:
            tmp.write_bytes(r.read())
        tmp.rename(dest)
        (raw / "SOURCE.txt").write_text("Department for Energy Security and Net Zero, Sub-regional fuel poverty data 2026 (2024 data). "
                                        f"Open Government Licence v3.0.\n{URL}\nDownloaded {datetime.date.today()}\n", encoding="utf-8")
        (raw / "SHA256SUMS.txt").write_text(f"{hashlib.sha256(dest.read_bytes()).hexdigest()}  {dest.name}\n", encoding="utf-8")
    xl = pd.ExcelFile(dest)
    print("sheets:", xl.sheet_names)
    lsoas = set(gpd.read_file(PHD / "data/london/boundaries_ons/lsoa21_bgc_v5_london.gpkg")["LSOA21CD"])
    for sh in xl.sheet_names:
        head = pd.read_excel(xl, sh, header=None, nrows=20)
        row = lambda i: head.iloc[i].astype(str).str.strip().str.lower()
        hr = next((i for i in range(len(head)) if row(i).eq("lsoa code").any() and row(i).eq("number of households").any()), None)
        if hr is None:
            continue
        t = pd.read_excel(xl, sh, header=hr)
        t.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in t.columns]
        code = next(c for c in t.columns if re.search(r"LSOA.*code", c, re.I))
        hh = next(c for c in t.columns if re.search(r"number of households", c, re.I))
        fp = next(c for c in t.columns if re.search(r"number of households in fuel poverty", c, re.I))
        pr = next((c for c in t.columns if re.search(r"proportion", c, re.I)), None)
        t = t[t[code].isin(lsoas)]
        out = pd.DataFrame({"lsoa": t[code], "households": pd.to_numeric(t[hh], errors="coerce"),
                            "fuel_poor": pd.to_numeric(t[fp], errors="coerce")})
        out["share_fuel_poor"] = out["fuel_poor"] / out["households"]
        out.to_parquet(keep(OUT / "fuel_poverty_lsoa_london.parquet"), index=False)
        print(f"sheet '{sh}': {len(out):,} London LSOAs; median share fuel poor {out['share_fuel_poor'].median():.3f}")
        return
    raise SystemExit("no LSOA sheet found")


if __name__ == "__main__":
    main()
