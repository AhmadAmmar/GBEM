# -*- coding: utf-8 -*-
import pandas as pd, re
from pathlib import Path

SAAD_IN  = r"D:\OneDrive - Ulster University\PhD\data\belfast\uprn\uprn.csv"
SAAD_OUT = Path(SAAD_IN).with_name("uprn_saad_clean.csv")

X_CANDS = ["X_COR","X_COORD","XCOORD","X","EASTING","X_COORDINATE","XCORD","LON","LONGITUDE"]
Y_CANDS = ["Y_COR","Y_COORD","YCOORD","Y","NORTHING","Y_COORDINATE","YCORD","LAT","LATITUDE"]
ENC = ("utf-8","utf-8-sig","cp1252","latin1")
UPRN_MINLEN, UPRN_MAXLEN = 9, 12

def sniff(p):
    for e in ENC:
        try: pd.read_csv(p, nrows=1, encoding=e); return e
        except UnicodeDecodeError: pass
    return "latin1"

def find_col(cols, needles):
    lut = {c.lower(): c for c in cols}
    for n in needles:
        if n.lower() in lut: return lut[n.lower()]
    for c in cols:
        if any(n.lower() in c.lower() for n in needles): return c
    return None

def find_uprn_col(path, enc):
    cols = pd.read_csv(path, nrows=0, encoding=enc).columns
    for c in cols:
        if "uprn" in c.lower(): return c
    raise ValueError(f"No UPRN-like column in {path}")

def clean_uprn(s: str) -> str | None:
    if pd.isna(s): return None
    s = str(s).strip()
    # strip leading apostrophe Excel adds to force Text
    if s.startswith("'"): s = s[1:]
    # if it's like 185565174.000000000, take integer part
    if re.fullmatch(r"\d+\.\d+", s):
        s = s.split(".", 1)[0]
    # strip everything that is not a digit
    s = re.sub(r"\D", "", s)
    return s or None

def canonical_key(digits: str) -> str | None:
    if not digits: return None
    try: return str(int(digits))   # drops leading zeros for joining
    except ValueError: return None

enc = sniff(SAAD_IN)
cols = pd.read_csv(SAAD_IN, nrows=0, encoding=enc).columns
uprn_col = find_uprn_col(SAAD_IN, enc)
x_col = find_col(cols, X_CANDS); y_col = find_col(cols, Y_CANDS)
if not (x_col and y_col):
    raise ValueError("Could not find X/Y columns in Saad CSV.")

df = pd.read_csv(SAAD_IN, dtype=str, low_memory=False, encoding=enc)

df["UPRN_norm"] = df[uprn_col].map(clean_uprn)
df["UPRN_key"]  = df["UPRN_norm"].map(canonical_key)

# keep plausible UPRN lengths and rows with XY
df["len_u"] = df["UPRN_norm"].str.len()
df["X_COR"] = pd.to_numeric(df[x_col], errors="coerce")
df["Y_COR"] = pd.to_numeric(df[y_col], errors="coerce")

clean = (df.dropna(subset=["UPRN_norm","UPRN_key","X_COR","Y_COR"])
           .loc[df["len_u"].between(UPRN_MINLEN, UPRN_MAXLEN), ["UPRN_norm","UPRN_key","X_COR","Y_COR"]]
           .drop_duplicates(subset=["UPRN_key"]))

clean.to_csv(SAAD_OUT, index=False, encoding="utf-8")
print(f"Clean Saad written: {SAAD_OUT} | rows={len(clean):,}")
