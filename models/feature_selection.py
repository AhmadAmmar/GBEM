"""Which predictors, and how many? Feature selection and dimension reduction compared under spatial cross-validation.

    python feature_selection.py --area belfast|london --year 2024 [--featureset eo_morph] [--sample 50000]

The baseline models (models/baseline.py) give LightGBM all ~700 predictors of a feature set and let the trees choose.
A reviewer will ask whether fewer, or compressed, predictors do as well, and which ones are kept. Every method below is
fitted inside each training fold only (5 folds of 2 km blocks, as in baseline.py), so the test blocks never influence
what is selected: selecting on all data first and then cross-validating is a known source of optimistic results.

Selectors (SAP score; LightGBM with the settings of baseline.py on whatever the selector returns):
  all            every predictor of the feature set (the baseline)
  decorrelate    drop one of every pair of numeric predictors with |Spearman| > 0.95 (keep the one more correlated
                 with SAP); removes the many near-duplicate satellite statistics
  gain_k         the k predictors with the largest LightGBM gain in a model fitted on the training fold (k = 20, 50,
                 100, 200)
  shap_k         the k predictors with the largest mean |SHAP| (LightGBM pred_contrib) on the training fold (k = 50)
  group_best     forward selection of whole predictor groups (Sentinel-2, thermal, morphology, LiDAR, ...) on an inner
                 split of the training blocks, stopping when MAE no longer falls by 0.05
  pca_eo         satellite and climate groups replaced by principal components keeping 95% of their variance
                 (standardised, fitted on the training fold); morphology, streets and LiDAR kept as they are
  pca_all        all numeric predictors replaced by principal components (95% variance)
  morph_only     morphology, streets and LiDAR only (no satellite): what form alone achieves
Reported per selector: SAP MAE, R2, band accuracy from the SAP, number of predictors (mean over folds), fit time, and
the stability of the chosen set across folds (mean pairwise Jaccard index; 1 = the same predictors in every fold).
Outputs in data/<area>/model/results/: feature_selection_<tag>.csv (per selector and fold),
feature_selection_<tag>_summary.csv, feature_selection_<tag>_chosen.csv (how often each predictor was chosen).
"""
import argparse, itertools, pathlib, sys, time
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.decomposition import PCA
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from safeio import keep
import baseline as B

FORM_GROUPS = ["morphology", "streets", "lidar"]


def numeric(X):
    """Numeric columns only (PCA and correlation need numbers)."""
    return [c for c in X.columns if str(X[c].dtype) != "category"]


def fit_lgbm(X, y):
    """LightGBM SAP regressor with the baseline settings."""
    return lgb.LGBMRegressor(**B.LGBM).fit(X, y)


def sel_decorrelate(X, y, thr=0.95):
    """Drop one of each highly correlated numeric pair, keeping the one more correlated with y."""
    num = numeric(X)
    R = X[num].rank().corr().abs()
    ry = X[num].rank().corrwith(pd.Series(y, index=X.index).rank()).abs().fillna(0)
    drop = set()
    up = R.where(np.triu(np.ones(R.shape, bool), 1)).stack()
    for (a, b), r in up[up > thr].sort_values(ascending=False).items():
        if a in drop or b in drop:
            continue
        drop.add(a if ry[a] < ry[b] else b)
    return [c for c in X.columns if c not in drop]


def sel_gain(k):
    """Top-k predictors by LightGBM gain on the training fold."""
    def f(X, y, **_):
        m = fit_lgbm(X, y)
        g = pd.Series(m.booster_.feature_importance("gain"), index=X.columns)
        return list(g.sort_values(ascending=False).index[:k])
    return f


def sel_shap(k):
    """Top-k predictors by mean |SHAP| on the training fold."""
    def f(X, y, **_):
        m = fit_lgbm(X, y)
        s = np.abs(m.predict(X.sample(min(len(X), 5000), random_state=0), pred_contrib=True)[:, :-1]).mean(0)
        return list(pd.Series(s, index=X.columns).sort_values(ascending=False).index[:k])
    return f


def sel_group_best(X, y, groups, blocks, col_group):
    """Forward selection of whole groups on an inner block split of the training fold."""
    gtr, gva = next(GroupKFold(4).split(X, groups=blocks))
    left, chosen, best = sorted(set(col_group[c] for c in X.columns)), [], np.inf
    while left:
        trial = {}
        for g in left:
            cols = [c for c in X.columns if col_group[c] in chosen + [g]]
            m = fit_lgbm(X.iloc[gtr][cols], y[gtr])
            trial[g] = np.abs(m.predict(X.iloc[gva][cols]) - y[gva]).mean()
        g, mae = min(trial.items(), key=lambda t: t[1])
        if mae > best - 0.05:
            break
        chosen.append(g); left.remove(g); best = mae
    return [c for c in X.columns if col_group[c] in chosen]


class PCAStep:
    """PCA (95% variance) on the chosen numeric columns, fitted on the training fold; other columns passed through."""

    def __init__(self, cols):
        """Columns to compress."""
        self.cols = cols

    def fit(self, X):
        """Median-impute, standardise and fit PCA on the training fold."""
        self.med = X[self.cols].median()
        Z = X[self.cols].fillna(self.med)
        self.sc = StandardScaler().fit(Z)
        self.pca = PCA(0.95, svd_solver="full", random_state=0).fit(self.sc.transform(Z))
        return self

    def transform(self, X):
        """Replace the compressed columns by their components."""
        P = self.pca.transform(self.sc.transform(X[self.cols].fillna(self.med)))
        out = X.drop(columns=self.cols).copy()
        for i in range(P.shape[1]):
            out[f"pc{i:03d}"] = P[:, i].astype("float32")
        return out


def jaccard(sets):
    """Mean pairwise Jaccard index of the chosen sets."""
    pairs = [len(a & b) / len(a | b) for a, b in itertools.combinations(sets, 2) if a | b]
    return float(np.mean(pairs)) if pairs else np.nan


def main():
    """Run every selector on the same spatial folds and write the comparison."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--featureset", default="eo_morph"); ap.add_argument("--sample", type=int)
    ap.add_argument("--block-km", type=float, default=2.0)
    a = ap.parse_args()
    d, dd = B.load(a.area, [a.year])
    d = d[pd.to_numeric(d["label_sap"], errors="coerce").notna() & d["x"].notna()].reset_index(drop=True)
    if a.sample and len(d) > a.sample:
        d = d.sample(a.sample, random_state=42).reset_index(drop=True)
    X = B.features(d, dd, B.SETS[a.featureset])
    y = pd.to_numeric(d["label_sap"]).to_numpy(float)
    col_group = dict(zip(dd["column"], dd["group"]))
    blocks = (np.floor(d["x"] / (a.block_km * 1000)).astype(int).astype(str) + "_" +
              np.floor(d["y"] / (a.block_km * 1000)).astype(int).astype(str)).to_numpy()
    folds = list(GroupKFold(5).split(X, groups=blocks))
    eo_num = [c for c in numeric(X) if col_group.get(c) not in FORM_GROUPS]
    sel = {"all": lambda X, y, **_: list(X.columns), "decorrelate": lambda X, y, **_: sel_decorrelate(X, y),
           **{f"gain_{k}": sel_gain(k) for k in (20, 50, 100, 200)}, "shap_50": sel_shap(50),
           "group_best": lambda X, y, blocks, **_: sel_group_best(X, y, None, blocks, col_group),
           "pca_eo": "pca_eo", "pca_all": "pca_all",
           "morph_only": lambda X, y, **_: [c for c in X.columns if col_group.get(c) in FORM_GROUPS]}
    tag = f"{a.year}_{a.featureset}" + (f"_s{a.sample // 1000}k" if a.sample else "")
    print(f"{a.area} {a.year} {a.featureset}: {len(d):,} certificates, {X.shape[1]} predictors", flush=True)
    rows, chosen = [], []
    for name, f in sel.items():
        sets = []
        for k, (tr, te) in enumerate(folds):
            t0 = time.time()
            Xtr, Xte = X.iloc[tr], X.iloc[te]
            if isinstance(f, str):
                step = PCAStep(eo_num if f == "pca_eo" else numeric(X)).fit(Xtr)
                Xtr, Xte = step.transform(Xtr), step.transform(Xte)
                cols = list(Xtr.columns)
            else:
                cols = f(Xtr, y[tr], blocks=blocks[tr])
                sets.append(set(cols)); chosen += [{"selector": name, "fold": k, "predictor": c, "group": col_group.get(c)} for c in cols]
            p = fit_lgbm(Xtr[cols], y[tr]).predict(Xte[cols])
            rows.append({"selector": name, "fold": k, "n_test": len(te), "n_predictors": len(cols),
                         "mae": np.abs(p - y[te]).mean(), "r2": 1 - ((p - y[te]) ** 2).sum() / ((y[te] - y[te].mean()) ** 2).sum(),
                         "band_accuracy": (B.sap_to_band(p) == B.sap_to_band(y[te])).mean(), "seconds": time.time() - t0})
            print(f"{name:12} fold {k}: {len(cols):4} predictors, MAE {rows[-1]['mae']:.2f}", flush=True)
        for r in rows[-5:]:
            r["stability_jaccard"] = jaccard(sets) if sets else np.nan
    res = DATA_RES = B.DATA / a.area / "model/results"
    r = pd.DataFrame(rows)
    r.round(4).to_csv(keep(res / f"feature_selection_{tag}.csv"), index=False)
    s = r.groupby("selector", sort=False).agg(mae=("mae", "mean"), mae_sd=("mae", "std"), r2=("r2", "mean"),
                                             band_accuracy=("band_accuracy", "mean"), n_predictors=("n_predictors", "mean"),
                                             stability=("stability_jaccard", "first"), seconds=("seconds", "sum")).reset_index()
    base = r[r["selector"] == "all"].set_index("fold")["mae"]
    s["mae_vs_all_paired"] = [float((r[r["selector"] == n].set_index("fold")["mae"] - base).mean()) for n in s["selector"]]
    s.round(4).to_csv(keep(res / f"feature_selection_{tag}_summary.csv"), index=False)
    c = pd.DataFrame(chosen)
    if len(c):
        c.groupby(["selector", "predictor", "group"]).size().rename("folds").reset_index() \
         .sort_values(["selector", "folds"], ascending=[True, False]).to_csv(keep(res / f"feature_selection_{tag}_chosen.csv"), index=False)
    print(s.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
