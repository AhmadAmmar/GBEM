"""Hand-calculated checks of the steady-state physics. Run: python -m pytest code/tests"""
import pathlib, sys
import numpy as np
import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "analysis"), str(ROOT / "epc"), str(ROOT), str(ROOT / "hem")]
pc = pytest.importorskip("physics_check")
Y = np.array([1950.0])


@pytest.mark.parametrize("text,u", [("Cavity wall, as built, no insulation (assumed)", 1.5), ("Cavity wall, filled cavity", 0.7),
                                    ("Solid brick, as built, no insulation (assumed)", 2.1), ("Average thermal transmittance 0.28 W/m-K", 0.28)])
def test_wall_lookup(text, u):
    assert pc.u_wall(pd.Series([text]), Y).iloc[0] == pytest.approx(u)


def test_loft_formula_by_hand():
    assert pc.u_roof(pd.Series(["Pitched, 100 mm loft insulation"]), Y).iloc[0] == pytest.approx(1 / (0.25 + 0.1 / 0.04))


def test_dwelling_above_loses_no_heat():
    assert pc.u_roof(pd.Series(["(another dwelling above)"]), Y).iloc[0] == 0


def test_heat_by_hand():
    hlc, q = pc.heat((10.0, 20.0, 30.0, 5.0), (1.0, 0.5, 0.5, 2.0), np.array([1950.0]), 100.0, 2000.0)
    expected = 10 + 10 + 15 + 10 + 0.15 * 65 + 0.33 * 1.0 * 100
    assert hlc[0] == pytest.approx(expected)
    assert q[0] == pytest.approx(expected * 2000 * 24 / 1000)


@pytest.mark.parametrize("year,y,n", [(1950, 0.15, 1.0), (1990, 0.15, 0.7), (2010, 0.08, 0.5)])
def test_age_rules_for_bridging_and_air(year, y, n):
    hlc, _ = pc.heat((10.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0), np.array([float(year)]), 100.0, 0.0)
    assert hlc[0] == pytest.approx(y * 10 + 0.33 * n * 100)
