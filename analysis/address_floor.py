"""Floor of a flat from its address: can the strongest non-satellite input be had without a certificate?

    python address_floor.py --area belfast|london

The floor position of a flat is the largest single gain in the models (models/baseline.py, eo_morph_floor), but it
comes from the certificate. Addresses often state it ("Ground Floor Flat", "Flat 2, First Floor", "Basement Flat",
"Top Floor Flat", "Second Floor"). Address lines of the certificates are parsed for these words; "Flat 12" or "Flat B"
alone are not used (numbering does not follow floors reliably).
Parsed floor: basement / lower ground -> ground; ground -> 0; first ... tenth (or 1st, 2nd, floor 3) -> number;
"top floor" -> top. Position: ground (0), top (top, or number >= storeys - 1 with storeys from LiDAR / footprint data),
middle (other numbers).
Reported for flats and maisonettes of the current stock: share of addresses with a floor, agreement with the
certificate's floor position, and the same for addresses of buildings without a certificate cannot be checked here.
Outputs in data/<area>/analysis/: address_floor.csv (summary), address_floor_cert.parquet (per certificate)
"""
import argparse, pathlib, re, sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

DATA = pathlib.Path(__file__).resolve().parents[2] / "data"
WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10}


def parse_floor(text):
    t = text.fillna("").str.lower()
    out = pd.Series(np.nan, index=t.index)
    num = pd.to_numeric(t.str.extract(r"\b(\d{1,2})(?:st|nd|rd|th)\s+(?:floor|flr)\b")[0], errors="coerce")
    num = num.fillna(pd.to_numeric(t.str.extract(r"\bfloor\s+(\d{1,2})\b")[0], errors="coerce"))
    for w, n in WORDS.items():
        num = num.where(num.notna() | ~t.str.contains(rf"\b{w}\s+(?:floor|flr)\b"), n)
    ground = t.str.contains(r"\b(?:ground|lower ground|basement|garden)\s+(?:floor|flr|flat)\b|\bbasement\b")
    top = t.str.contains(r"\btop\s+(?:floor|flr|flat)\b|\bpenthouse\b")
    out = out.where(~ground, 0).fillna(num)
    return out, top


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True)
    a = ap.parse_args()
    out = DATA / a.area / "analysis"
    cur = pd.read_parquet(out / "stock_current.parquet", columns=["cert_id", "fp_id", "property_type", "floor_pos"])
    cur = cur[cur["property_type"].isin(["Flat", "Maisonette"])]
    c = pd.read_parquet(DATA / a.area / "epc/certificates_linked.parquet", columns=["cert_id", "ADDRESS1", "ADDRESS2", "ADDRESS3"])
    c["cert_id"] = c["cert_id"].astype(str)
    d = cur.merge(c.drop_duplicates("cert_id"), on="cert_id", how="left")
    text = d[["ADDRESS1", "ADDRESS2", "ADDRESS3"]].fillna("").agg(" ".join, axis=1)
    num, top = parse_floor(text)
    phys = pd.read_parquet(DATA / a.area / "epc/physics_fp.parquet", columns=["fp_id", "phys_storeys"])
    d = d.merge(phys, on="fp_id", how="left")
    st = d["phys_storeys"]
    pos = np.select([top, num.eq(0), num.notna() & st.notna() & (num >= st - 1), num.notna()], ["top", "ground", "top", "middle"], "")
    d["addr_floor_num"], d["addr_floor_pos"] = num, np.where(pos == "", None, pos)
    has = d["addr_floor_pos"].notna()
    known = has & d["floor_pos"].isin(["ground", "middle", "top"])
    agree = (d.loc[known, "addr_floor_pos"] == d.loc[known, "floor_pos"])
    conf = pd.crosstab(d.loc[known, "floor_pos"], d.loc[known, "addr_floor_pos"])
    s = {"area": a.area, "flats": len(d), "with_floor_in_address": int(has.sum()), "share_with_floor": has.mean(),
         "checked_against_certificate": int(known.sum()), "agreement": agree.mean() if len(agree) else np.nan,
         "agreement_ground": (agree[d.loc[known, "floor_pos"] == "ground"]).mean(),
         "agreement_middle": (agree[d.loc[known, "floor_pos"] == "middle"]).mean(),
         "agreement_top": (agree[d.loc[known, "floor_pos"] == "top"]).mean()}
    pd.DataFrame([s]).round(4).to_csv(keep(out / "address_floor.csv"), index=False)
    d[["cert_id", "fp_id", "floor_pos", "addr_floor_num", "addr_floor_pos", "phys_storeys"]].to_parquet(keep(out / "address_floor_cert.parquet"), index=False)
    print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in s.items()})
    print("certificate (rows) vs address (columns):\n", conf.to_string())


if __name__ == "__main__":
    main()
