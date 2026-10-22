"""Reproduction of the earlier EPC-band random forest (code/scripts/ml/rf_basic.py) on the earlier 2024 samples.

    python reproduce_old.py

The earlier setup, as in rf_basic.py: random forest (100 trees, seed 42), random stratified 70/30 split, satellite
columns only; then the same model on the 10 most important features. Its figures were reported but never verified.

Variants, all on the same samples:
  R1  earlier setup, satellite features
  R2  earlier setup, satellite features + certificate attributes (property type, built form, floor area, age band)
  R3  as R1, but the split keeps all certificates at the same location together (grouped 70/30 by coordinates): a
      random split puts certificates of the same building (flats, repeat certificates) in training and test, which
      inflates the score
  R4  as R1, with a spatially blocked split (1 km squares kept together)
Data: London data/london/london_samples_indices_2024.csv (columns from B2 on are satellite features);
      Belfast data/belfast/gee/Belfast_2024_point_samples_uid_rich_v3.csv joined to its certificates by uid.
Output: data/<area>/model/results/reproduce_old.csv
"""
import pathlib, json
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, GroupShuffleSplit
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, cohen_kappa_score
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

PHD = pathlib.Path(__file__).resolve().parents[2]
DATA = PHD / "data"
BANDS = list("ABCDEFG")
ATTR = ["PROPERTY_TYPE", "BUILT_FORM", "TOTAL_FLOOR_AREA", "CONSTRUCTION_AGE_BAND"]


def metrics(y, p):
    yi, pi = np.array([BANDS.index(v) for v in y]), np.array([BANDS.index(v) for v in p])
    return {"accuracy": accuracy_score(y, p), "balanced_accuracy": balanced_accuracy_score(y, p),
            "macro_f1": f1_score(y, p, average="macro"), "weighted_f1": f1_score(y, p, average="weighted"),
            "within_one_band": float(np.mean(np.abs(yi - pi) <= 1)), "qwk": cohen_kappa_score(yi, pi, weights="quadratic")}


def run(X, y, train, test, label):
    rf = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1).fit(X.iloc[train], y.iloc[train])
    out = [{"variant": label, "features": X.shape[1], **metrics(y.iloc[test], rf.predict(X.iloc[test]))}]
    top = pd.Series(rf.feature_importances_, X.columns).nlargest(10).index
    rf10 = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1).fit(X.iloc[train][top], y.iloc[train])
    out.append({"variant": label + " (top 10)", "features": 10, **metrics(y.iloc[test], rf10.predict(X.iloc[test][top]))})
    return out


def encode(d, cols):
    X = d[cols].copy()
    for c in X.columns:
        if X[c].dtype == object:
            X[c] = X[c].astype("category").cat.codes
    return X


def area(name, d, sat_cols, xy):
    d = d[d["CURRENT_ENERGY_RATING"].isin(BANDS)].dropna(subset=sat_cols).reset_index(drop=True)
    y = d["CURRENT_ENERGY_RATING"]
    Xs = d[sat_cols]
    idx = np.arange(len(d))
    tr, te = train_test_split(idx, test_size=0.3, random_state=42, stratify=y)
    rows = run(Xs, y, tr, te, "R1 earlier setup, satellite")
    if all(c in d for c in ATTR):
        rows += run(pd.concat([Xs, encode(d, ATTR)], axis=1), y, tr, te, "R2 earlier setup, satellite + certificate attributes")
    loc = (d[xy[0]].round(5).astype(str) + "_" + d[xy[1]].round(5).astype(str))
    tr3, te3 = next(GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=42).split(idx, groups=loc))
    rows += run(Xs, y, tr3, te3, "R3 split by location")
    blk = (d[xy[0]] * 100).astype(int).astype(str) + "_" + (d[xy[1]] * 100).astype(int).astype(str)   # ~1 km in WGS84
    tr4, te4 = next(GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=42).split(idx, groups=blk))
    rows += run(Xs, y, tr4, te4, "R4 spatially blocked split (~1 km)")
    R = pd.DataFrame(rows).round(3)
    R.insert(0, "area", name); R.insert(1, "n", len(d))
    out = DATA / name / "model" / "results"; out.mkdir(parents=True, exist_ok=True)
    R.to_csv(keep(out / "reproduce_old.csv"), index=False)
    print(R.to_string(index=False), flush=True)
    return R


def main():
    ld = pd.read_csv(DATA / "london/london_samples_indices_2024.csv", low_memory=False)
    sat = list(ld.columns[ld.columns.get_loc("B2"):])
    area("london", ld, sat, ("LONGITUDE", "LATITUDE"))
    b = pd.read_csv(DATA / "belfast/gee/Belfast_2024_point_samples_uid_rich_v3.csv")
    lab = pd.read_csv(DATA / "belfast/belfast-epc/gee_epc_2024_points_uid_wgs84.csv")
    lab["CURRENT_ENERGY_RATING"] = lab["CURRENT_ENERGY_RATING"].astype(str).str.strip().str.upper()
    bd = b.merge(lab[["uid", "lon", "lat", "CURRENT_ENERGY_RATING", "PROPERTY_TYPE", "BUILT_FORM", "TOTAL_FLOOR_AREA"]], on="uid")
    sat_b = [c for c in b.columns if c not in ("system:index", "uid", ".geo")]
    area("belfast", bd, sat_b, ("lon", "lat"))


if __name__ == "__main__":
    main()
