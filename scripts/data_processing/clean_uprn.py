# -*- coding: utf-8 -*-
import pandas as pd, re
from pathlib import Path

UNION_IN  = r"D:\OneDrive - Ulster University\PhD\data\belfast\uprn\BELFS_20250829_F\uprn_union_with_xy_v2.csv"
UNION_OUT = Path(UNION_IN).with_name("uprn_union_with_xy_clean.csv")
ENCODINGS = ("utf-8","utf-8-sig","cp1252","latin1")

def sniff(p):
    for e in ENCODINGS:
        try:
            pd.read_csv(p, nrows=1, encoding=e); return e
        except UnicodeDecodeError: continue
    return "latin1"

def canonical(val):
    """digits-only; drop leading zeros; also fixes Excel '1.23E+05' style."""
    if pd.isna(val): return None
    s = str(val).strip()
    # if we ever see scientific notation as text, normalize via float->int safely
    if re.fullmatch(r"[0-9]+(\.[0-9]+)?[eE][+\-]?[0-9]+", s):
        try:
            # Use Decimal to avoid float precision if you want: from decimal import Decimal
            from decimal import Decimal, InvalidOperation
            s = format(Decimal(s), 'f')
        except Exception:
            pass
    s = re.sub(r"\D", "", s)
    if not s: return None
    try:
        return str(int(s))  # strips leading zeros and bogus exponent leftovers
    except ValueError:
        return None

enc = sniff(UNION_IN)
df = pd.read_csv(UNION_IN, dtype=str, low_memory=False, encoding=enc)

# pick columns
xcol = "X_COR" if "X_COR" in df.columns else next((c for c in df.columns if c.upper().startswith("X")), None)
ycol = "Y_COR" if "Y_COR" in df.columns else next((c for c in df.columns if c.upper().startswith("Y")), None)
uprn_col = "UPRN_norm" if "UPRN_norm" in df.columns else next((c for c in df.columns if "uprn" in c.lower()), None)
if not (uprn_col and xcol and ycol):
    raise ValueError("Missing UPRN or X/Y columns in union file.")

# build canonical key and standardize
df["UPRN_key"]  = df[uprn_col].map(canonical)
df = df.dropna(subset=["UPRN_key", xcol, ycol]).copy()
df = df.drop_duplicates(subset=["UPRN_key"], keep="first")

# write back with a clean UPRN_norm = canonical key (for consistency)
cols = ["UPRN_key", xcol, ycol] + ([ "xy_source" ] if "xy_source" in df.columns else [])
out = df[cols].rename(columns={"UPRN_key":"UPRN_norm", xcol:"X_COR", ycol:"Y_COR"})
out.to_csv(UNION_OUT, index=False, encoding="utf-8")

print(f"Wrote clean union: {UNION_OUT}")
print(f"Rows: {len(out):,}  |  unique UPRNs: {out['UPRN_norm'].nunique():,}")
