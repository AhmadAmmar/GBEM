"""Roofs, floors, party walls, thermal bridging and window area against RdSAP 2012 version 9.93 (Lit/standards/
RdSAP2012_9.93.pdf: Tables S3, S4, S8B, S9, S10, S11, S12, S13 and section S5.5) and RdSAP 10 where stated.
Expected values are table cells or hand calculations written out below."""
import math
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "epc"))
import rdsap_elements as re_  # noqa: E402

EW = "England and Wales: "


@pytest.mark.parametrize("desc,age,u", [
    ("Pitched, 100 mm loft insulation", EW + "1930-1949", 0.40),          # S9, 100 mm
    ("Pitched, 270 mm loft insulation", EW + "1930-1949", 0.16),          # S9, 270 mm
    ("Pitched, 12 mm loft insulation", EW + "1930-1949", 1.5),            # S9, 12 mm
    ("Pitched, 400+ mm loft insulation", EW + "1930-1949", 0.11),         # S9, >= 400 mm
    ("Pitched, no insulation (assumed)", EW + "1900-1929", 2.3),          # S10 note (a)
    ("Pitched, limited insulation (assumed)", EW + "1967-1975", 1.5),     # S10 joists, E
    ("Pitched, insulated (assumed)", EW + "1983-1990", 0.40),             # S10 joists, G
    ("Pitched, insulated (assumed)", EW + "1996-2002", 0.26),             # S10 joists, I
    ("Flat, insulated (assumed)", EW + "2003-2006", 0.25),                # S10 flat, J
    ("Roof room(s), insulated (assumed)", EW + "1976-1982", 0.80),        # S10 room-in-roof, F
    ("Pitched, insulated at rafters", EW + "1900-1929", 0.68),            # S10 rafters B 2.3; insulated, thickness unknown: 50 mm
    ("Pitched, insulated (assumed)", EW + "1900-1929", 0.40),             # band B is 2.3 (none) but the text says insulated: 100 mm
    ("Flat, limited insulation (assumed)", EW + "1930-1949", 1.5),        # band C is 2.3 but the text says limited: 12 mm
    ("Pitched, limited insulation (assumed)", EW + "1976-1982", 0.68),    # S10 joists, F
    ("(another dwelling above)", EW + "1900-1929", 0.0),
    ("(other premises above)", EW + "1900-1929", 0.0),                    # 5.2.5: commercial above = dwelling above
    ("Pitched, insulated (assumed)", "Northern Ireland: 2007-2013", 0.16),  # S10 joists, K
])
def test_roof(desc, age, u):
    assert re_.u_roof(pd.Series([desc]), pd.Series([age]), "NI" if "Northern" in age else "EW").iloc[0] == pytest.approx(u)


def test_iso13370_solid_by_hand():
    # A 45 m2, exposed perimeter 19 m, w 0.22 m, uninsulated: B = 90/19 = 4.737; dt = 0.22 + 1.5 x 0.21 = 0.535 < B
    B, dt = 90 / 19, 0.22 + 1.5 * (0.17 + 0.04)
    hand = round(2 * 1.5 * math.log(math.pi * B / dt + 1) / (math.pi * B + dt), 2)
    assert hand == 0.65
    assert re_.iso13370([45], [19], [0.22], [0.0], [False])[0] == hand


def test_iso13370_suspended_by_hand():
    B, dg = 90 / 19, 0.22 + 1.5 * (0.17 + 0.04)
    ug = 2 * 1.5 * math.log(math.pi * B / dg + 1) / (math.pi * B + dg)
    ux = 2 * 0.3 * 1.5 / B + 1450 * 0.003 * 5 * 0.05 / B
    hand = round(1 / (2 * 0.17 + 0.2 + 1 / (ug + ux)), 2)
    assert re_.iso13370([45], [19], [0.22], [0.0], [True])[0] == hand


def test_floor_rules():
    desc = pd.Series(["(another dwelling below)", "(other premises below)", "To unheated space, no insulation (assumed)",
                      "To external air, insulated", "Solid, no insulation (assumed)"])
    age = pd.Series([EW + "1930-1949"] * 5)
    u = re_.u_floor(desc, age, "EW", np.full(5, 45.0), np.full(5, 19.0), pd.Series(["Solid brick, as built"] * 5))
    assert list(u.iloc[:4]) == [0.0, 0.7, 1.20, 0.50]                     # none; S5.7; S12 as built A-G; S12 insulated
    assert u.iloc[4] == re_.iso13370([45], [19], [0.22], [0.0], [False])[0]   # S3 solid brick C: 220 mm


def test_floor_insulation_by_band():
    # S11, England and Wales: band K 100 mm -> Rf = 0.1/0.035
    u = re_.u_floor(pd.Series(["Solid, insulated (assumed)"]), pd.Series([EW + "2007-2011"]), "EW", [45.0], [19.0], pd.Series(["Cavity wall"]))
    assert u.iloc[0] == re_.iso13370([45], [19], [0.30], [0.1 / 0.035], [False])[0]


@pytest.mark.parametrize("age,nation,y", [(EW + "1996-2002", "EW", 0.15), (EW + "2003-2006", "EW", 0.11), (EW + "2007-2011", "EW", 0.08),
                                          ("Northern Ireland: 2000-2006", "NI", 0.15), ("Northern Ireland: 2007-2013", "NI", 0.08)])
def test_bridging_table_s13(age, nation, y):
    assert re_.bridging_y(pd.Series([age]), nation)[0] == y


def test_window_area_table_s4():
    # house, band D: 0.1294 x 90 + 5.515; flat, band A-C: 0.0801 x 60 + 5.580
    w = re_.window_area([90, 60], [False, True], pd.Series([EW + "1950-1966", EW + "1900-1929"]), "EW")
    assert w == pytest.approx([0.1294 * 90 + 5.515, 0.0801 * 60 + 5.580])


def test_party_wall_table_s8b():
    assert list(re_.u_party([False, True])) == [0.25, 0.0]
