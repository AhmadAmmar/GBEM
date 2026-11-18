"""Default wall U-values from the RdSAP specification, read from the certificate's wall description and age band.

Source: RdSAP 10 Specification (BRE, 9 June 2025), Table 1 (age bands), Table 6 (England), Table 8 (Northern Ireland),
sections 5.6-5.8. For every row and age band A-L used here the values are the same as RdSAP 2012 version 9.93,
Tables S1, S6 and S8, under which most certificates in the register were produced, with two exceptions:
  - Stone and solid brick in bands A-D: RdSAP 10 computes them from wall thickness (5.6, 5.7). The register gives no
    thickness, so the default thicknesses of RdSAP 9.93 Table S3 are used: solid brick 220 mm, giving 1.7 (Table 13,
    200-280 mm), the value both versions tabulate; stone 500 mm, giving 3.3 - 0.002 x 500 = 2.3 for granite or
    whinstone and 3.0 - 0.002 x 500 = 2.0 for sandstone or limestone.
  - Stone and solid brick with insulation in bands A-D: RdSAP 10 applies 5.8 (U = 1 / (1/U0 + R)); RdSAP 9.93 tabulates
    0.55, which is also RdSAP 10's band E value. 0.55 is used.
Band M (2023 onwards) exists only in RdSAP 10. Band J does not exist in Northern Ireland.

Rules, from the specification:
  - "as built" in any form (no insulation, insulated, partial insulation, all "(assumed)") is the as-built row for the
    age band: the assessor entered no evidence of insulation added later, so the age default applies.
  - "with internal / external / additional insulation", thickness unknown: the 50 mm row ("If a wall is known to have
    additional insulation but the insulation thickness is unknown, use the row in the table for 50 mm insulation").
    Timber frame uses its "with internal insulation" row.
  - "filled cavity": the filled-cavity row; with internal or external insulation as well, the filled-cavity 50 mm row.
  - A stated "average thermal transmittance" is used as given (elsewhere, in physics_check.stated_u).
Descriptions that name no wall type (basement wall, park home, "sap05:walls", blank) return NaN, for the caller's
age-band fallback.
"""
import re

import numpy as np
import pandas as pd

BANDS = "ABCDEFGHIJKLM"
# first year of bands B..M (band A is everything earlier); Table 1
EDGES = {
    "EW": [1900, 1930, 1950, 1967, 1976, 1983, 1991, 1996, 2003, 2007, 2012, 2023],
    "NI": [1919, 1930, 1950, 1974, 1978, 1986, 1992, 2000, 2007, 2007, 2014, 2023],   # J not used in NI: 2007 starts K
}
_ = None
TABLE = {
    "EW": {   # Table 6, England (RdSAP 10); bands A..M
        "solid":            [1.7, 1.7, 1.7, 1.7, 1.7, 1.0, 0.60, 0.60, 0.45, 0.35, 0.30, 0.28, 0.26],
        "granite":          [2.3, 2.3, 2.3, 2.3, 1.7, 1.0, 0.60, 0.60, 0.45, 0.35, 0.30, 0.28, 0.26],
        "sandstone":        [2.0, 2.0, 2.0, 2.0, 1.7, 1.0, 0.60, 0.60, 0.45, 0.35, 0.30, 0.28, 0.26],
        "solid_ins":        [0.55, 0.55, 0.55, 0.55, 0.55, 0.45, 0.35, 0.35, 0.30, 0.25, 0.21, 0.21, 0.20],
        "cob":              [0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.60, 0.60, 0.45, 0.35, 0.30, 0.28, 0.26],
        "cob_ins":          [0.40, 0.40, 0.40, 0.40, 0.40, 0.40, 0.35, 0.35, 0.30, 0.25, 0.21, 0.21, 0.20],
        "cavity":           [1.5, 1.5, 1.5, 1.5, 1.5, 1.0, 0.60, 0.60, 0.45, 0.35, 0.30, 0.28, 0.26],
        "cavity_ins":       [0.53, 0.53, 0.53, 0.53, 0.53, 0.45, 0.35, 0.35, 0.30, 0.25, 0.21, 0.21, 0.20],
        "filled":           [0.7, 0.7, 0.7, 0.7, 0.7, 0.40, 0.35, 0.35, 0.45, 0.35, 0.30, 0.28, 0.26],
        "filled_ins":       [0.37, 0.37, 0.37, 0.37, 0.37, 0.27, 0.25, 0.25, 0.25, 0.25, 0.21, 0.21, 0.20],
        "timber":           [2.5, 1.9, 1.9, 1.0, 0.80, 0.45, 0.40, 0.40, 0.40, 0.35, 0.30, 0.28, 0.26],
        "timber_ins":       [0.60, 0.55, 0.55, 0.40, 0.40, 0.40, 0.40, 0.40, 0.40, 0.35, 0.30, 0.28, 0.26],
        "system":           [2.0, 2.0, 2.0, 2.0, 1.7, 1.0, 0.60, 0.60, 0.45, 0.35, 0.30, 0.28, 0.26],
        "system_ins":       [0.60, 0.60, 0.60, 0.60, 0.55, 0.45, 0.35, 0.35, 0.30, 0.25, 0.21, 0.21, 0.20],
    },
    "NI": {   # Table 8, Northern Ireland (RdSAP 10); bands A..M, J not applicable
        "solid":            [1.7, 1.7, 1.7, 1.7, 1.7, 1.0, 0.60, 0.45, 0.45, _, 0.30, 0.28, 0.18],
        "granite":          [2.3, 2.3, 2.3, 2.3, 1.7, 1.0, 0.60, 0.45, 0.45, _, 0.30, 0.28, 0.18],
        "sandstone":        [2.0, 2.0, 2.0, 2.0, 1.7, 1.0, 0.60, 0.45, 0.45, _, 0.30, 0.28, 0.18],
        "solid_ins":        [0.55, 0.55, 0.55, 0.55, 0.55, 0.45, 0.35, 0.30, 0.30, _, 0.21, 0.21, 0.15],
        "cob":              [0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.60, 0.60, 0.45, _, 0.30, 0.28, 0.18],
        "cob_ins":          [0.40, 0.40, 0.40, 0.40, 0.40, 0.40, 0.35, 0.35, 0.30, _, 0.21, 0.21, 0.15],
        "cavity":           [1.5, 1.5, 1.5, 1.5, 1.5, 1.0, 0.60, 0.45, 0.45, _, 0.30, 0.28, 0.18],
        "cavity_ins":       [0.53, 0.53, 0.53, 0.53, 0.53, 0.45, 0.35, 0.35, 0.30, _, 0.21, 0.21, 0.15],
        "filled":           [0.7, 0.7, 0.7, 0.7, 0.7, 0.40, 0.35, 0.45, 0.45, _, 0.30, 0.28, 0.18],
        "filled_ins":       [0.37, 0.37, 0.37, 0.37, 0.37, 0.27, 0.25, 0.25, 0.25, _, 0.25, 0.21, 0.15],
        "timber":           [2.5, 1.9, 1.9, 1.0, 0.80, 0.45, 0.40, 0.40, 0.40, _, 0.30, 0.28, 0.18],
        "timber_ins":       [0.60, 0.55, 0.55, 0.40, 0.40, 0.40, 0.40, 0.40, 0.40, _, 0.30, 0.28, 0.18],
        "system":           [2.0, 2.0, 2.0, 2.0, 1.7, 1.0, 0.60, 0.45, 0.45, _, 0.30, 0.28, 0.18],
        "system_ins":       [0.60, 0.60, 0.60, 0.60, 0.55, 0.45, 0.35, 0.30, 0.30, _, 0.21, 0.21, 0.15],
    },
}
TYPES = [("granite", r"granite|whin"), ("sandstone", r"sandstone|limestone"), ("solid", r"solid brick"),
         ("cob", r"\bcob\b"), ("cavity", r"cavity"), ("timber", r"timber"), ("system", r"system built")]
INSULATED = r"with (?:internal|external|additional) insulation|and (?:internal|external) insulation"


def band(age_band, nation):
    """Age-band text ('England and Wales: 1930-1949', 'Northern Ireland: before 1919', '2019') -> band letter.
    The nation named in the text sets the year boundaries; otherwise `nation` does."""
    s = pd.Series(age_band)
    u = pd.Series(s.astype(object).fillna("").astype(str).unique())       # few distinct texts: work on those
    y = pd.to_numeric(u.str.extract(r"(\d{4})")[0], errors="coerce")
    y = y.where(~u.str.contains("before", case=False), y - 1)            # 'before 1919' -> 1918
    own = np.where(u.str.contains("Northern Ireland", case=False), "NI", np.where(u.str.contains("England|Wales", case=False), "EW", nation))
    letter = [None if np.isnan(yy) else BANDS[int(np.searchsorted(EDGES[n], yy, side="right"))] for yy, n in zip(y.to_numpy(float), own)]
    return s.astype(object).fillna("").astype(str).map(dict(zip(u, letter)))


def row(desc):
    """Wall description -> table row name, or NA when no wall type is named."""
    s = pd.Series(desc).astype(object).fillna("").astype(str)
    return s.map({t: _row_one(t) for t in s.unique()})                 # under 100 distinct texts per area


def _row_one(text):
    """Table row for one wall description: the first matching construction type, then filled cavity or insulated
    variants. None when no type is recognised.
    """
    t = text.lower()
    kind = next((k for k, pat in TYPES if re.search(pat, t)), None)    # first pattern wins
    if kind is None:
        return None
    ins = re.search(INSULATED, t) is not None
    if kind == "cavity" and "filled cavity" in t:
        return "filled_ins" if ins else "filled"
    if not ins:
        return kind
    return {"cavity": "cavity_ins", "granite": "solid_ins", "sandstone": "solid_ins", "solid": "solid_ins"}.get(kind, f"{kind}_ins")


def u_wall_rdsap(desc, age_band, nation):
    """U-value (W/m2K) from the RdSAP table for the dwelling's nation ('EW' or 'NI'); NaN where no row applies."""
    b, r = band(age_band, nation), row(desc)
    if nation == "NI":
        b = b.replace("J", "K")                                         # J does not exist in NI
    names = list(TABLE[nation])
    grid = np.array([[np.nan if v is None else v for v in TABLE[nation][k]] for k in names])
    ri = r.map({k: i for i, k in enumerate(names)}).fillna(-1).astype(int).to_numpy()
    bi = b.map({c: i for i, c in enumerate(BANDS)}).fillna(-1).astype(int).to_numpy()
    ok = (ri >= 0) & (bi >= 0)
    u = np.full(len(r), np.nan)
    u[ok] = grid[ri[ok], bi[ok]]
    return pd.Series(u, index=pd.Series(desc).index)
