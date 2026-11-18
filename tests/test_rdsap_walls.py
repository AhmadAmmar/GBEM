"""Wall U-values against cells read by hand from the RdSAP 10 Specification (9 June 2025), Tables 1, 6 and 8,
kept in Lit/standards/RdSAP10_specification_2025-06-10.pdf (pages 15, 33-36)."""
import pathlib
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "epc"))
import rdsap_walls as rw  # noqa: E402

CASES = [
    # description, age-band text, nation, expected U, table cell
    ("Solid brick, as built, no insulation (assumed)", "England and Wales: 1900-1929", "EW", 1.7, "Table 6 solid brick as built, B (5.7, 200-280 mm)"),
    ("Solid brick, with internal insulation", "England and Wales: 1900-1929", "EW", 0.55, "Table 6 stone/solid brick 50 mm, A-E"),
    ("Solid brick, with external insulation", "England and Wales: before 1900", "EW", 0.55, "Table 6 stone/solid brick 50 mm, A"),
    ("Solid brick, as built, insulated (assumed)", "England and Wales: 1996-2002", "EW", 0.45, "Table 6 solid brick as built, I"),
    ("Cavity wall, as built, no insulation (assumed)", "England and Wales: 1950-1966", "EW", 1.5, "Table 6 cavity as built, D"),
    ("Cavity wall, as built, partial insulation (assumed)", "England and Wales: 1976-1982", "EW", 1.0, "Table 6 cavity as built, F"),
    ("Cavity wall, as built, insulated (assumed)", "England and Wales: 1983-1990", "EW", 0.60, "Table 6 cavity as built, G"),
    ("Cavity wall, filled cavity", "England and Wales: 1930-1949", "EW", 0.7, "Table 6 filled cavity, C"),
    ("Cavity wall, filled cavity and internal insulation", "England and Wales: 1930-1949", "EW", 0.37, "Table 6 filled cavity 50 mm, C"),
    ("Cavity wall, with external insulation", "England and Wales: 1967-1975", "EW", 0.53, "Table 6 unfilled cavity 50 mm, E"),
    ("Timber frame, with additional insulation", "England and Wales: before 1900", "EW", 0.60, "Table 6 timber frame with internal insulation, A"),
    ("System built, with external insulation", "England and Wales: 1967-1975", "EW", 0.55, "Table 6 system build 50 mm, E"),
    ("Granite or whinstone, as built, no insulation (assumed)", "England and Wales: before 1900", "EW", 2.3, "5.6: 3.3 - 0.002 x 500"),
    ("Sandstone or limestone, as built, no insulation (assumed)", "England and Wales: 1900-1929", "EW", 2.0, "5.6: 3.0 - 0.002 x 500"),
    ("Cavity wall, as built, insulated (assumed)", "2019", "EW", 0.28, "Table 6 cavity as built, L (2012-2022)"),
    ("Cavity wall, as built, insulated (assumed)", "Northern Ireland: 1992-1999", "NI", 0.45, "Table 8 cavity as built, H"),
    ("Cavity wall, as built, no insulation (assumed)", "Northern Ireland: 1950-1973", "NI", 1.5, "Table 8 cavity as built, D"),
    ("Solid brick, as built, no insulation (assumed)", "Northern Ireland: before 1919", "NI", 1.7, "Table 8 solid brick as built, A"),
    ("Cavity wall, filled cavity", "Northern Ireland: 1986-1991", "NI", 0.35, "Table 8 filled cavity, G"),
    ("Cavity wall, as built, insulated (assumed)", "Northern Ireland: 2007-2013", "NI", 0.30, "Table 8 cavity as built, K"),
    ("System built, with external insulation", "Northern Ireland: 2014-2022", "NI", 0.21, "Table 8 system build 50 mm, L"),
]


@pytest.mark.parametrize("desc,age,nation,u,cell", CASES, ids=[c[4] for c in CASES])
def test_table_cell(desc, age, nation, u, cell):
    """One wall table cell per case, read by hand from the specification."""
    assert rw.u_wall_rdsap(pd.Series([desc]), pd.Series([age]), nation).iloc[0] == pytest.approx(u)


@pytest.mark.parametrize("age,nation,letter", [("England and Wales: before 1900", "EW", "A"), ("England and Wales: 1900-1929", "EW", "B"),
                                               ("England and Wales: 2012 onwards", "EW", "L"), ("2023", "EW", "M"),
                                               ("Northern Ireland: before 1919", "NI", "A"), ("Northern Ireland: 1919-1929", "NI", "B"),
                                               ("Northern Ireland: 1974-1977", "NI", "E"), ("Northern Ireland: 2000-2006", "NI", "I"),
                                               ("Northern Ireland: 2007-2013", "NI", "K"), ("England and Wales: 1950-1966", "NI", "D")])
def test_age_bands_follow_table_1(age, nation, letter):
    """Age-band letters from the band text, by nation (Table 1)."""
    assert rw.band(pd.Series([age]), nation).iloc[0] == letter


def test_no_wall_type_gives_nan():
    """Descriptions without a recognised wall type give NaN."""
    assert rw.u_wall_rdsap(pd.Series(["Basement wall", "", None]), pd.Series(["2019"] * 3), "EW").isna().all()
