"""Roof, floor, party-wall, thermal-bridging and window-area defaults from the RdSAP specification, read from the
certificate's descriptions and age band. Walls are in rdsap_walls.py.

Source: RdSAP 2012 version 9.93 (BRE, 19 November 2017), under which the descriptions in the register were generated,
checked against the RdSAP 10 Specification (9 June 2025). Both are kept in Lit/standards/. Tables used:
  S3   wall thickness by wall type and age band (floor calculation)
  S4   window area from total floor area, by age band and house or flat
  S8B  party walls: "unable to determine" is 0.25 W/m2K for a house or bungalow and 0 for a flat or maisonette
  S9   roof U-value from loft insulation thickness (same values as RdSAP 10 Table 16, column 1)
  S10  assumed roof U-values by roof type and age band ("as built" and "unknown"); band M from RdSAP 10 Table 18
  S5.5 ground floors by BS EN ISO 13370 from area, exposed perimeter, wall thickness and insulation (S11 by age band)
  S5.7 floor above partially heated premises 0.7 W/m2K
  S12  exposed and semi-exposed upper floors
  S13  thermal bridging factor y by age band
The register records results of these rules, not the assessor's inputs, so some inputs are inferred; each is named
where it is made ("judgement").
"""
import re

import numpy as np
import pandas as pd

from rdsap_walls import BANDS, band  # noqa: F401  (band re-exported for callers)

def _bi(b):
    """Age-band letters to column indices 0-12 (A-M); unknown bands give -1."""
    return pd.Series(b).map({c: i for i, c in enumerate(BANDS)}).fillna(-1).astype(int).to_numpy()


# ---------------------------------------------------------------- roofs
S9 = [(0, 2.3), (12, 1.5), (25, 1.0), (50, 0.68), (75, 0.50), (100, 0.40), (125, 0.35), (150, 0.30), (175, 0.25),
      (200, 0.21), (225, 0.19), (250, 0.17), (270, 0.16), (300, 0.14), (350, 0.12), (400, 0.11)]
S10 = {   # bands A..M; A-L from RdSAP 9.93 Table S10, M from RdSAP 10 Table 18
    "joists":   [2.3, 2.3, 2.3, 2.3, 1.5, 0.68, 0.40, 0.30, 0.26, 0.16, 0.16, 0.16, 0.15],
    "rafters":  [2.3, 2.3, 2.3, 2.3, 1.5, 0.68, 0.40, 0.35, 0.35, 0.20, 0.20, 0.18, 0.15],
    "flat":     [2.3, 2.3, 2.3, 2.3, 1.5, 0.68, 0.40, 0.35, 0.35, 0.25, 0.25, 0.18, 0.15],
    "roomroof": [2.3, 2.3, 2.3, 2.3, 1.5, 0.80, 0.50, 0.35, 0.35, 0.30, 0.25, 0.18, 0.15],
    "thatched": [0.35, 0.35, 0.35, 0.35, 0.35, 0.35, 0.35, 0.35, 0.35, 0.30, 0.25, 0.18, 0.15],
}
NO_ROOF_LOSS = r"dwelling above|premises above"     # S5 / 5.2.5: commercial premises above count as a dwelling above


def loft_u(mm):
    """Table S9: the row for the largest listed thickness not above `mm`."""
    t = np.asarray(mm, float)
    keys = np.array([k for k, _ in S9]); vals = np.array([v for _, v in S9])
    return vals[np.clip(np.searchsorted(keys, t, side="right") - 1, 0, len(keys) - 1)]


def _roof_one(t):
    """Description -> (rule, column or thickness)."""
    t = t.lower()
    if re.search(NO_ROOF_LOSS, t):
        return ("none", None)
    kind = "thatched" if "thatch" in t else "roomroof" if "roof room" in t else "flat" if t.startswith("flat") else \
        "rafters" if "rafters" in t else "joists"
    m = re.search(r"(\d+)\s*\+?\s*mm", t)
    if m and kind in ("joists", "roomroof"):
        return ("mm", float(m.group(1)))
    if re.search(r"no insulation|uninsulated", t):
        return ("value", 0.35 if kind == "thatched" else 2.3)        # S10 note (a)
    insulated = re.search(r"insulated", t) is not None
    if "assumed" in t or "unknown" in t or not re.search(r"insulat", t):
        # as built or unknown: the age-band value. Where the text says insulated (or limited) but the band's value is
        # the uninsulated one, the text wins (the band is the main dwelling's, and the roof may be later): S10 note (1),
        # 100 mm (0.40) for 'insulated', 12 mm (1.5) for 'limited'. Judgement, checked against the register's roof rating.
        return ("band_text", (kind, "limited" if "limited" in t else "insulated" if insulated else None))
    if "limited" in t:
        return ("cap", (kind, 1.5))                                   # judgement: observed but limited, at most 12 mm
    if kind == "rafters":
        return ("cap", (kind, 0.68))                                  # insulated at rafters, thickness unknown: 50 mm (S10 notes (1), (c))
    return ("cap", (kind, 0.40))                                      # S10 note (1): known insulated, at most the 100 mm value


def u_roof(desc, age_band, nation):
    """Roof U-value; 0 where another dwelling or premises is above (no roof loss)."""
    s = pd.Series(desc).astype(object).fillna("").astype(str)
    rules = s.map({t: _roof_one(t) for t in s.unique()})
    b = band(age_band, nation)
    if nation == "NI":
        b = b.replace("J", "K")
    bi = _bi(b)
    out = np.full(len(s), np.nan)
    for i, (r, k) in enumerate(zip(rules.to_numpy(), bi)):
        kind, arg = r
        if kind == "none":
            out[i] = 0.0
        elif kind == "mm":
            out[i] = loft_u(arg)
        elif kind == "value":
            out[i] = arg
        elif k >= 0 and kind == "band_text":
            col, word = arg
            v = S10[col][k]
            if word == "insulated" and v >= 1.5 and col != "thatched":
                v = 0.40
            elif word == "limited" and v >= 2.3:
                v = 1.5
            out[i] = v
        elif k >= 0:
            col, cap = arg
            out[i] = min(S10[col][k], cap)
    return pd.Series(out, index=s.index)


def roof_loses_heat(desc):
    """True where the roof description does not say another dwelling or premises is above."""
    return ~pd.Series(desc).astype(object).fillna("").astype(str).str.lower().str.contains(NO_ROOF_LOSS)


# ---------------------------------------------------------------- floors
S3 = {   # wall thickness, mm, bands A..L (M as L); RdSAP 9.93 Table S3, England, Wales and Northern Ireland
    "stone":  [500, 500, 500, 500, 450, 420, 420, 420, 450, 450, 450, 450, 450],
    "solid":  [220, 220, 220, 220, 240, 250, 270, 270, 300, 300, 300, 300, 300],
    "cavity": [250, 250, 250, 250, 250, 260, 270, 270, 300, 300, 300, 300, 300],
    "timber": [150, 150, 150, 250, 270, 270, 270, 270, 300, 300, 300, 300, 300],
    "cob":    [540, 540, 540, 540, 540, 540, 560, 560, 590, 590, 590, 590, 590],
    "system": [250, 250, 250, 250, 250, 300, 300, 300, 300, 300, 300, 300, 300],
}
S11 = {   # all-over floor insulation (mm) when thickness unknown, bands A..L (M as L); Table S11
    "EW": [0, 0, 0, 0, 0, 0, 0, 0, 25, 75, 100, 100, 100],
    "NI": [0, 0, 0, 0, 0, 0, 0, 25, 50, 50, 100, 100, 100],    # J not applicable in NI (treated as K)
}
S11_SUSPENDED = [True, True] + [False] * 11                         # construction when unknown: A, B suspended timber
S12 = {   # exposed / semi-exposed upper floors, bands A..M: as built or unknown, and insulated with unknown thickness
    "as_built":  [1.20] * 7 + [0.51, 0.51, 0.25, 0.22, 0.22, 0.22],
    "insulated": [0.50] * 9 + [0.25, 0.22, 0.22, 0.22],
}
LAMBDA_G, R_SI, R_SE = 1.5, 0.17, 0.04                              # S5.5: clay soil, surface resistances
NO_FLOOR_LOSS = r"dwelling below"


def wall_thickness_m(wall_desc, age_band, nation):
    """Wall thickness (m) from RdSAP Table S3, by wall type read from the description and age band."""
    d = pd.Series(wall_desc).astype(object).fillna("").astype(str).str.lower()
    kind = np.select([d.str.contains("granite|whin|sandstone|limestone|stone"), d.str.contains("solid brick"), d.str.contains(r"\bcob\b"),
                      d.str.contains("timber"), d.str.contains("system built")], ["stone", "solid", "cob", "timber", "system"], "cavity")
    bi = np.clip(_bi(band(age_band, nation)), 0, None)
    return np.array([S3[k][i] for k, i in zip(kind, bi)]) / 1000.0


def iso13370(area, perim, w, r_f, suspended):
    """BS EN ISO 13370 as written in RdSAP 9.93 S5.5 (solid and suspended ground floors)."""
    A = np.asarray(area, float); P = np.clip(np.asarray(perim, float), 0.5, None)
    w = np.asarray(w, float); r_f = np.asarray(r_f, float); sus = np.asarray(suspended, bool)
    B = 2 * A / P
    # solid
    dt = w + LAMBDA_G * (R_SI + r_f + R_SE)
    u_solid = np.where(dt < B, 2 * LAMBDA_G * np.log(np.pi * B / dt + 1) / (np.pi * B + dt), LAMBDA_G / (0.457 * B + dt))
    # suspended: deck resistance 0.2 (+ insulation), h 0.3 m, v 5 m/s, fw 0.05, eps 0.003 m2/m, Uw 1.5
    dg = w + LAMBDA_G * (R_SI + R_SE)
    ug = 2 * LAMBDA_G * np.log(np.pi * B / dg + 1) / (np.pi * B + dg)
    ux = 2 * 0.3 * 1.5 / B + 1450 * 0.003 * 5 * 0.05 / B
    u_susp = 1 / (2 * R_SI + (r_f + 0.2) + 1 / (ug + ux))
    return np.round(np.where(sus, u_susp, u_solid), 2)


def _floor_one(t):
    """Floor case from one description: none (another dwelling below), premises (0.7, S5.7), exposed (Table S12) or ground."""
    t = t.lower()
    if re.search(NO_FLOOR_LOSS, t):
        return "none"
    if "premises below" in t:
        return "premises"
    if "unheated space" in t or "external air" in t:
        return "exposed"
    return "ground"


def u_floor(desc, age_band, nation, area, perim, wall_desc):
    """Floor U-value; 0 where another dwelling is below. Ground floors by ISO 13370 with this dwelling's floor area
    and exposed perimeter."""
    s = pd.Series(desc).astype(object).fillna("").astype(str)
    low = s.str.lower()
    kind = s.map({t: _floor_one(t) for t in s.unique()}).to_numpy()
    b = band(age_band, nation)
    if nation == "NI":
        b = b.replace("J", "K")
    bi = np.clip(_bi(b), 0, None)
    assumed = low.str.contains("assumed|unknown").to_numpy()
    none_ = low.str.contains("no insulation|uninsulated").to_numpy()
    insulated = (low.str.contains("insulated") & ~low.str.contains("no insulation|uninsulated")).to_numpy()
    limited = low.str.contains("limited").to_numpy()
    mm = pd.to_numeric(low.str.extract(r"(\d+)\s*mm")[0], errors="coerce").to_numpy()
    band_mm = np.array([S11[nation][i] for i in bi], float)
    # thickness: stated mm; else 'no insulation' 0; else assumed/unknown the band default; else observed insulation:
    # retro-fitted, the greater of 50 mm and the band default (S11 note 2); 'limited' (observed) judged as 25 mm
    ins_mm = np.where(~np.isnan(mm), mm, np.where(none_, 0, np.where(assumed, band_mm,
                      np.where(limited, np.maximum(25, band_mm), np.where(insulated, np.maximum(50, band_mm), band_mm)))))
    suspended = np.where(low.str.contains("suspended").to_numpy(), True,
                         np.where(low.str.contains("solid").to_numpy(), False, np.array([S11_SUSPENDED[i] for i in bi])))
    r_f = 0.001 * ins_mm / 0.035
    w = wall_thickness_m(wall_desc, age_band, nation)
    u_ground = iso13370(area, perim, w, r_f, suspended)
    u_exp = np.where(insulated & ~assumed, np.array([S12["insulated"][i] for i in bi]), np.array([S12["as_built"][i] for i in bi]))
    u = np.select([kind == "none", kind == "premises", kind == "exposed"], [0.0, 0.7, u_exp], u_ground)
    return pd.Series(u, index=s.index)


def floor_loses_heat(desc):
    """True where the floor description does not say another dwelling is below."""
    return ~pd.Series(desc).astype(object).fillna("").astype(str).str.lower().str.contains(NO_FLOOR_LOSS)


# ---------------------------------------------------------------- party walls, bridging, windows
def u_party(is_flat):
    """Table S8B, party wall type not recorded in the register: 'unable to determine'."""
    return np.where(np.asarray(is_flat, bool), 0.0, 0.25)


S13 = [0.15] * 9 + [0.11, 0.08, 0.08, 0.08]                        # y by band A..M (M as K, L; RdSAP 10 Table 21)


def bridging_y(age_band, nation):
    """Thermal bridging factor y (W/m2K) by age band, RdSAP Table S13; NI band J is treated as K."""
    b = band(age_band, nation)
    if nation == "NI":
        b = b.replace("J", "K")
    return np.array([S13[i] if i >= 0 else 0.15 for i in _bi(b)])


S4 = {   # window area = a x TFA + c, bands A..M (M as J-L); Table S4
    "house": [(0.1220, 6.875)] * 3 + [(0.1294, 5.515), (0.1239, 7.332), (0.1252, 5.520), (0.1356, 5.242), (0.0948, 6.534),
                                     (0.1382, -0.027)] + [(0.1435, -0.403)] * 4,
    "flat":  [(0.0801, 5.580)] * 3 + [(0.0341, 8.562), (0.0717, 6.560), (0.1199, 1.975), (0.0510, 4.554), (0.0813, 3.744),
                                     (0.1148, 0.392)] + [(0.1148, 0.392)] * 4,
}


def window_area(tfa, is_flat, age_band, nation):
    """Window area (m2) = a x TFA + c by age band and house or flat, RdSAP Table S4, not below zero."""
    b = band(age_band, nation)
    if nation == "NI":
        b = b.replace("J", "K")
    bi = np.clip(_bi(b), 0, None)
    flat = np.asarray(is_flat, bool)
    a = np.array([S4["flat" if f else "house"][i][0] for f, i in zip(flat, bi)])
    c = np.array([S4["flat" if f else "house"][i][1] for f, i in zip(flat, bi)])
    return np.clip(a * np.asarray(tfa, float) + c, 0, None)
