"""Where does the model work and where does it fail? Out-of-fold error by urban form, dwelling type, storeys and age,
and the full ladder of spatial scales from dwelling to local authority.

    python error_by_form.py --area belfast|london [--tag <model run tag>] [--sets eo eo_morph eo_morph_floor all]

Uses the spatial out-of-fold predictions of models/baseline.py (every certificate predicted by a model that did not see
its 2 km block), so every number here is an error on places the model was not trained on.

1. Strata: error of the SAP regressor within each
     morph_type    urban-form type of the certificate's 250 m cell (analysis/morph_types.py; k-means of building
                   cover, height, footprint size, shared walls, addresses per footprint, compactness, street width, H/W,
                   setback, frontage, distance to a main road)
     built_form    detached, semi-detached, terraced, ... (certificate)
     property_type house, flat, bungalow, maisonette, park home (certificate)
     floor_pos     house, ground, middle or top flat (certificate)
     storeys       storeys of the building: footprint data where given, else LiDAR 90th percentile height / 3 m (as in
                   baseline.floor_features); classes 1, 2, 3, 4-5, 6+ and "no height"
     height_source where the storeys come from: footprint attribute, LiDAR, or none
     age_band      construction age band (certificate)
   Per stratum: certificates, MAE, mean bias (predicted - actual), RMSE, R2 and Spearman within the stratum, band
   accuracy (band from the predicted SAP), and the MAE of the mean-only predictor (the stratum's own mean SAP), so a
   stratum where the model is no better than its own average is visible. Strata with fewer than 30 certificates are
   dropped.
   The certificate attributes are used only to group errors; they are not inputs of the eo / eo_morph models.
2. Scale ladder: actual and predicted SAP averaged within dwelling (certificate), building (footprint), street,
   250 m cell, neighbourhood (Belfast ward, London LSOA), district (Belfast DEA / London MSOA where present) and local
   authority, for units with at least 5 certificates (buildings: 2). Same metrics as analysis/scale_eval.py.
3. Storey check: LiDAR storeys (90th percentile height / 3 m as in the models, and / 2.8 m as in epc/physics.py)
   against the footprint storey attribute, and every estimate against the highest certified floor of the building + 1
   (a lower bound). The certificate's flat storey count is not used: it counts the storeys of the flat, not the building.
Outputs in data/<area>/model/results/: error_by_form_<tag>.csv, scale_ladder_<tag>.csv, storey_check_<tag>.csv, and
figures in data/<area>/model/figures/: error_by_form_<tag>.png
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
from scipy import stats
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "models"))
from safeio import keep
import baseline as B

DATA = B.DATA
TAG = {"london": "2024_s50k", "belfast": "2024"}
MIN_N = 30


def metrics(a, p):
    """Error of predictions p against actual SAP a, with the stratum-mean predictor for reference."""
    a, p = np.asarray(a, float), np.asarray(p, float)
    e = p - a
    ss = ((a - a.mean()) ** 2).sum()
    return {"n": len(a), "sap_mean": a.mean(), "mae": np.abs(e).mean(), "bias": e.mean(), "rmse": np.sqrt((e ** 2).mean()),
            "r2": 1 - (e ** 2).sum() / ss if ss > 0 else np.nan,
            "spearman": stats.spearmanr(a, p)[0] if len(a) > 2 else np.nan,
            "band_accuracy": (B.sap_to_band(a) == B.sap_to_band(p)).mean(),
            "mae_stratum_mean": np.abs(a - a.mean()).mean()}


def storey_class(s):
    """Storey classes for reporting."""
    return pd.cut(s, [0, 1.5, 2.5, 3.5, 5.5, 999], labels=["1", "2", "3", "4-5", "6+"]).astype("string").fillna("no height")


def load(area, tag):
    """Out-of-fold predictions joined to the grouping attributes, urban-form type and building heights."""
    oof = pd.read_parquet(DATA / area / f"model/results/oof_{tag}.parquet")
    oof["id_cert"] = oof["id_cert"].astype(str)
    e = pd.read_parquet(DATA / area / "analysis/cert_enriched.parquet")
    e = e.rename(columns={"cert_id": "id_cert"}).drop(columns=["x", "y", "year", "fp_id"], errors="ignore")
    e["id_cert"] = e["id_cert"].astype(str)
    d = oof.merge(e, on="id_cert", how="left")
    years = sorted(d["year"].dropna().astype(int).unique())
    cols = ["id_cert", "morph_num_floors", "lidar_height_p90_m", "epc_floor_level"]
    h = pd.concat([pd.read_parquet(DATA / area / f"model/dataset_{y}.parquet", columns=None) for y in years])
    h = h[[c for c in cols if c in h.columns]].drop_duplicates("id_cert")
    h["id_cert"] = h["id_cert"].astype(str)
    d = d.merge(h, on="id_cert", how="left")
    fpn = pd.to_numeric(d.get("morph_num_floors"), errors="coerce")
    lid = (pd.to_numeric(d.get("lidar_height_p90_m"), errors="coerce") / 3).round().clip(lower=1)
    d["storeys_fp"], d["storeys_lidar"] = fpn, lid
    d["storeys_n"] = fpn.fillna(lid)
    d["storeys"] = storey_class(d["storeys_n"])
    d["height_source"] = np.select([fpn.notna(), lid.notna()], ["footprint attribute", "LiDAR"], "none")
    cell = np.floor(d["x"] / 250).astype("Int64").astype(str) + "_" + np.floor(d["y"] / 250).astype("Int64").astype(str)
    t = pd.read_parquet(DATA / area / "analysis/morph_types_cells.parquet", columns=["cell", "type"])
    d["morph_type"] = cell.map(dict(zip(t["cell"], t["type"]))).fillna("cell with < 10 certificates")
    return d


def strata(d, sets):
    """Error per stratum for each feature set."""
    rows = []
    for fs in sets:
        p = f"sap_lgbm_{fs}"
        for by in ["morph_type", "built_form", "property_type", "floor_pos", "storeys", "height_source", "age_band"]:
            if by not in d:
                continue
            for g, q in d[[by, "actual_sap", p]].dropna().groupby(by):
                if len(q) >= MIN_N:
                    rows.append({"featureset": fs, "by": by, "stratum": g, **metrics(q["actual_sap"], q[p])})
        rows.append({"featureset": fs, "by": "all", "stratum": "all", **metrics(d["actual_sap"], d[p])})
    return pd.DataFrame(rows)


def ladder(d, sets):
    """Error of unit means from dwelling to local authority."""
    units = [("certificate", None, 1), ("building", "fp_id", 2), ("street", "street", 5), ("250 m cell", "cell", 5),
             ("neighbourhood", "nbhd", 5), ("district", "district", 5), ("sector", "sector", 5), ("local authority", "la", 5)]
    if "fp_id" not in d and "id_fp" in d:
        d["fp_id"] = d["id_fp"]
    rows = []
    for fs in sets:
        p = f"sap_lgbm_{fs}"
        for name, col, minn in units:
            if col is None:
                g = pd.DataFrame({"a": d["actual_sap"], "p": d[p], "n": 1})
            elif col in d and d[col].notna().any():
                g = d.groupby(col).agg(a=("actual_sap", "mean"), p=(p, "mean"), n=("actual_sap", "size"))
                g = g[g["n"] >= minn]
            else:
                continue
            g = g.dropna()
            if len(g) < 8:
                continue
            m = metrics(g["a"], g["p"])
            rows.append({"featureset": fs, "scale": name, "units": len(g), "certificates_per_unit": g["n"].median(),
                         **{k: m[k] for k in ("mae", "bias", "r2", "spearman", "band_accuracy")}})
    return pd.DataFrame(rows)


def storey_check(d):
    """How well the storey estimates agree with each other and with the floors recorded on certificates.

    The certificate's flat storey count is the number of storeys a flat itself occupies (1, or 2 for a maisonette),
    not the height of the building, so it cannot be used. Two checks that can:
      vs footprint   LiDAR estimates against the footprint storey attribute, where both exist
      vs top floor   the highest floor number certified in the building + 1 is a lower bound on its storeys
                     (buildings with flats on at least 2 floors); share of buildings where the estimate is at least
                     that, and the mean shortfall
    """
    h = pd.to_numeric(d.get("lidar_height_p90_m"), errors="coerce")
    est = {"footprint attribute": d["storeys_fp"], "LiDAR p90 / 3.0 m": d["storeys_lidar"],
           "LiDAR p90 / 2.8 m": (h / 2.8).round().clip(lower=1)}
    fl = pd.to_numeric(d.get("epc_floor_level", pd.Series(index=d.index, dtype=float)).astype("string").str.extract(r"^(\d+)")[0],
                       errors="coerce")
    fp = d["fp_id"] if "fp_id" in d else d["id_fp"]
    top = pd.DataFrame({"fp": fp, "fl": fl}).dropna().groupby("fp")["fl"].agg(["max", "nunique"])
    top = top[top["nunique"] >= 2]["max"] + 1
    rows = []
    for name, s in est.items():
        if name != "footprint attribute":
            q = pd.DataFrame({"est": s, "ref": d["storeys_fp"]}).dropna()
            if len(q) >= 20:
                e = q["est"] - q["ref"]
                rows.append({"estimate": name, "reference": "footprint attribute", "n": len(q), "exact": (e == 0).mean(),
                             "within_one": (e.abs() <= 1).mean(), "mean_error": e.mean(), "mae": e.abs().mean(),
                             "spearman": stats.spearmanr(q["est"], q["ref"])[0]})
        b = pd.DataFrame({"fp": fp, "est": s}).dropna().groupby("fp")["est"].median()
        q = pd.concat([b.rename("est"), top.rename("ref")], axis=1).dropna()
        if len(q) >= 20:
            e = q["est"] - q["ref"]
            rows.append({"estimate": name, "reference": "highest certified floor + 1 (lower bound)", "n": len(q),
                         "exact": (e == 0).mean(), "within_one": (e.abs() <= 1).mean(), "mean_error": e.mean(),
                         "mae": e.abs().mean(), "spearman": stats.spearmanr(q["est"], q["ref"])[0],
                         "share_at_least_bound": (e >= 0).mean()})
    return pd.DataFrame(rows)


def figure(s, path, fs):
    """MAE per stratum (bars) against the stratum-mean MAE (ticks), one panel per grouping."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    bys = ["morph_type", "built_form", "storeys", "floor_pos", "age_band", "height_source"]
    s = s[(s["featureset"] == fs) & s["by"].isin(bys)]
    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    for ax, by in zip(axes.ravel(), bys):
        q = s[s["by"] == by].sort_values("mae")
        if q.empty:
            ax.axis("off"); continue
        y = np.arange(len(q))
        ax.barh(y, q["mae"], color="#4c78a8", label="model MAE")
        ax.scatter(q["mae_stratum_mean"], y, marker="|", s=200, color="#e45756", label="MAE of stratum mean")
        ax.set_yticks(y, [str(t)[:34] + f"  (n={n})" for t, n in zip(q["stratum"], q["n"])], fontsize=7)
        ax.set_title(by.replace("_", " "), fontsize=10); ax.set_xlabel("SAP MAE (points)")
    axes[0, 0].legend(fontsize=7, loc="lower right")
    fig.suptitle(f"Spatial out-of-fold SAP error by stratum, feature set {fs}")
    fig.tight_layout(); fig.savefig(keep(path), dpi=150); plt.close(fig)


def main():
    """Strata, scale ladder and storey check for one area."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--tag")
    ap.add_argument("--sets", nargs="+", default=["eo", "eo_morph", "eo_morph_floor", "all"])
    a = ap.parse_args()
    tag = a.tag or TAG[a.area]
    d = load(a.area, tag)
    sets = [s for s in a.sets if f"sap_lgbm_{s}" in d]
    res = DATA / a.area / "model/results"
    s = strata(d, sets); s.round(4).to_csv(keep(res / f"error_by_form_{tag}.csv"), index=False)
    l = ladder(d, sets); l.round(4).to_csv(keep(res / f"scale_ladder_{tag}.csv"), index=False)
    c = storey_check(d); c.round(4).to_csv(keep(res / f"storey_check_{tag}.csv"), index=False)
    figs = DATA / a.area / "model/figures"; figs.mkdir(parents=True, exist_ok=True)
    figure(s, figs / f"error_by_form_{tag}.png", "eo_morph")
    pd.set_option("display.width", 200)
    print(s[s["featureset"] == "eo_morph"].drop(columns="featureset").round(2).to_string(index=False, max_colwidth=36))
    print(l[l["featureset"].isin(["eo_morph", "eo_morph_floor"])].round(2).to_string(index=False))
    print(c.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
