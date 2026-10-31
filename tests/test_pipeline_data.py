"""Integrity of the stock pipeline's outputs. Skips where the data is not on this machine; prints no individual records."""
import pathlib
import numpy as np
import pandas as pd
import pytest
from sklearn.model_selection import GroupKFold

D = pathlib.Path(__file__).resolve().parents[2] / "data"
AREAS = {"london": ((480000, 580000), (130000, 230000)), "belfast": ((300000, 370000), (340000, 410000))}
params = [a for a in AREAS if (D / a / "epc/certificates_linked.parquet").exists()]


@pytest.fixture(params=params, scope="module")
def area(request):
    return request.param


@pytest.fixture(scope="module")
def certs(area):
    return pd.read_parquet(D / area / "epc/certificates_linked.parquet", columns=["cert_id", "UPRN", "x", "y", "is_latest", "fp_id", "link_method", "link_dist_m"])


def test_certificate_ids_are_unique(certs):
    assert certs.cert_id.is_unique


def test_coordinates_fall_in_the_study_area_grid(area, certs):
    (x0, x1), (y0, y1) = AREAS[area]
    assert certs.x.dropna().between(x0, x1).mean() > .999 and certs.y.dropna().between(y0, y1).mean() > .999


def test_one_latest_certificate_per_property(certs):
    assert certs[certs.is_latest.astype(bool)].dropna(subset=["UPRN"]).UPRN.is_unique


def test_links_respect_the_distance_limit(certs):
    assert certs.link_dist_m.dropna().max() <= 5
    assert certs[certs.link_method == "none"].fp_id.isna().all()


def test_boundary_q_star_recomputes(area):
    s = pd.read_csv(D / area / "analysis/hem_metrics_summary.csv").set_index("measure").value
    e = pd.read_parquet(D / area / "analysis/hem_metrics_cert.parquet", columns=["sap", "fabric_q"])
    assert e[e.sap.between(68, 70)].fabric_q.median() == pytest.approx(s["fabric proxy C/D boundary q* (kWh/m2/yr)"], abs=.06)


def test_indicator_is_physical_and_rises_with_loss(area):
    p = pd.read_parquet(D / area / "analysis/physics_cert.parquet", columns=["u_wall", "u_window", "q_as_described_kwh_m2", "sap", "hlc_as_described"])
    assert p.u_wall.dropna().between(0, 6).all() and p.u_window.dropna().between(0, 6).all() and (p.hlc_as_described.dropna() > 0).all()
    assert p.q_as_described_kwh_m2.corr(p.sap, method="spearman") < -.2      # worse fabric, lower SAP


def test_spatial_folds_never_share_a_block(area):
    ids = pd.read_parquet(D / area / "model/dataset_2024.parquet", columns=["id_cert"]).id_cert.astype(str)
    c = pd.read_parquet(D / area / "epc/certificates_linked.parquet", columns=["cert_id", "x", "y"])
    d = c[c.cert_id.astype(str).isin(ids)].dropna()
    b = np.floor(d.x / 2000).astype(int).astype(str) + "_" + np.floor(d.y / 2000).astype(int).astype(str)
    for tr, te in GroupKFold(5).split(d, groups=b):
        assert not set(b.iloc[tr]) & set(b.iloc[te])


def test_stock_addresses_are_not_lost_on_the_way_to_cells(area):
    p = pd.read_parquet(D / area / "model/stock/hem_stock_pred_2024.parquet", columns=["n_uprn", "p_fabric_c", "p_fossil"])
    c = pd.read_parquet(D / area / "model/stock/hem_stock_cells_2024.parquet", columns=["dwellings"])
    assert p.p_fabric_c.dropna().between(0, 1).all() and p.p_fossil.dropna().between(0, 1).all()
    assert .95 < c.dwellings.sum() / p.n_uprn.sum() <= 1
