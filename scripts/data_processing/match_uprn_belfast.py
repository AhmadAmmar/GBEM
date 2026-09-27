# pip install pandas
import pandas as pd
import re
from pathlib import Path

# ------------------ PATHS ------------------
EPC_CSV = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-epc\NI_Domestic_Master_to 01_2025.csv"
OS_UPRN_CSV = r"D:\OneDrive - Ulster University\PhD\data\uprn\osopenuprn_202507.csv"

OUT_MATCHED = Path(EPC_CSV).with_name("NI_Domestic_Master_to_01_2025_UPRNmatched.csv")
OUT_UNMATCHED_SAMPLE = Path(EPC_CSV).with_name("NI_Domestic_Master_to_01_2025_UPRN_unmatched_sample.csv")

CHUNK_SIZE = 200_000  # adjust if needed
# -------------------------------------------

def find_uprn_col(path, candidates=("uprn", "primary_uprn", "uprn_key")):
    cols = pd.read_csv(path, nrows=0).columns
    # Prefer any column whose name contains 'uprn'
    uprn_like = [c for c in cols if "uprn" in c.lower()]
    if uprn_like:
        return uprn_like[0]
    # Fallback to common explicit names
    for c in candidates:
        if c in cols:
            return c
    raise ValueError(f"Could not find a UPRN column in: {path}\nColumns: {list(cols)}")

def norm_uprn(val):
    """Return digits-only string (preserve leading zeros). None if empty."""
    if pd.isna(val):
        return None
    s = str(val).strip()
    # common artifact: floats like '123456789012.0'
    if s.endswith(".0"):
        s = s[:-2]
    s = re.sub(r"\D", "", s)  # keep digits only
    return s if s else None

# 1) Load OS Open UPRN list → set of normalized strings
uprn_col_os = find_uprn_col(OS_UPRN_CSV)
os_uprn = pd.read_csv(OS_UPRN_CSV, usecols=[uprn_col_os], dtype=str, low_memory=False)
os_uprn["UPRN_norm"] = os_uprn[uprn_col_os].map(norm_uprn)
valid_uprns = set(os_uprn["UPRN_norm"].dropna().unique())
del os_uprn  # free memory

print(f"Loaded {len(valid_uprns):,} unique UPRNs from OS Open UPRN.")

# 2) Stream EPC CSV in chunks, filter by UPRN membership, write out
uprn_col_epc = find_uprn_col(EPC_CSV)

first_write = True
unmatched_samples = []
for chunk in pd.read_csv(EPC_CSV, dtype=str, chunksize=CHUNK_SIZE, low_memory=False):
    # normalize EPC UPRN column
    chunk["UPRN_norm"] = chunk[uprn_col_epc].map(norm_uprn)

    matched = chunk[chunk["UPRN_norm"].isin(valid_uprns)].copy()
    # write matched rows (drop helper col)
    if not matched.empty:
        matched.drop(columns=["UPRN_norm"]).to_csv(
            OUT_MATCHED, index=False, mode="w" if first_write else "a", header=first_write, encoding="utf-8"
        )
        first_write = False

    # collect a small sample of unmatched for QA (up to 5k rows total)
    um = chunk[~chunk["UPRN_norm"].isin(valid_uprns)]
    if len(unmatched_samples) < 5000:
        unmatched_samples.append(um.head(max(0, 5000 - sum(len(x) for x in unmatched_samples))))

# Save a small unmatched sample (optional QA)
if unmatched_samples:
    pd.concat(unmatched_samples, ignore_index=True).drop(columns=["UPRN_norm"]).to_csv(
        OUT_UNMATCHED_SAMPLE, index=False, encoding="utf-8"
    )

# Final stats (quick re-count from the output file header)
try:
    n_matched = sum(1 for _ in open(OUT_MATCHED, "r", encoding="utf-8")) - 1
except FileNotFoundError:
    n_matched = 0

print(f"Matched EPC rows written: {n_matched:,}")
if Path(OUT_UNMATCHED_SAMPLE).exists():
    print(f"Unmatched sample saved: {OUT_UNMATCHED_SAMPLE}")
print(f"Matched output saved:    {OUT_MATCHED}")
