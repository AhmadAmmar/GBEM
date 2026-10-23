"""Calibrated band probabilities: can the stated confidence be taken at face value?

    python calibrate_probs.py --area belfast|london --years 2024 [--sample 50000] [--featureset eo_morph]

Spatial 5-fold cross-validation (2 km blocks). In every outer training set, 20% of the blocks are held back as a
calibration set. Four variants of the LightGBM band classifier (settings of baseline.py):
  balanced            class weights "balanced" (as in baseline.py), no calibration
  balanced_T          + temperature scaling: logits divided by T fitted on the calibration set (minimum negative
                      log-likelihood); T > 1 softens over-confident probabilities (Guo et al. 2017)
  unweighted          no class weights (probabilities closer to observed frequencies, rare bands predicted less)
  unweighted_T        + temperature scaling
Metrics on the outer test folds: accuracy, macro-F1, quadratic kappa, negative log-likelihood, multi-class Brier
score, expected calibration error of the top-class probability (10 bins) and of all classes (classwise ECE).
Output: data/<area>/model/results/calibration_methods_<tag>.csv and reliability_methods_<tag>.csv
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy.optimize import minimize_scalar
from scipy.special import softmax
from sklearn.model_selection import GroupKFold
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import baseline as B
from safeio import keep                      # existing outputs are archived, never overwritten

K = len(B.BANDS)


def logits(m, X):
    z = m.predict(X, raw_score=True)
    full = np.full((len(X), K), -30.0)
    full[:, m.classes_] = z
    return full


def fit_T(z, y):
    nll = lambda t: -np.log(softmax(z / t, axis=1)[np.arange(len(y)), y] + 1e-12).mean()
    return minimize_scalar(nll, bounds=(0.05, 20), method="bounded").x


def ece_top(p, y, bins=10):
    conf, pred = p.max(1), p.argmax(1)
    b = np.clip((conf * bins).astype(int), 0, bins - 1)
    return sum((b == i).mean() * abs((pred[b == i] == y[b == i]).mean() - conf[b == i].mean()) for i in range(bins) if (b == i).any())


def ece_classwise(p, y, bins=10):
    out = []
    for k in range(K):
        pk, yk = p[:, k], (y == k)
        b = np.clip((pk * bins).astype(int), 0, bins - 1)
        out.append(sum((b == i).mean() * abs(yk[b == i].mean() - pk[b == i].mean()) for i in range(bins) if (b == i).any()))
    return float(np.mean(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--years", nargs="+", type=int, required=True)
    ap.add_argument("--sample", type=int); ap.add_argument("--featureset", default="eo_morph")
    a = ap.parse_args()
    tag = "-".join(map(str, a.years)) + (f"_s{a.sample // 1000}k" if a.sample else "") + f"_{a.featureset}"
    d, dd = B.load(a.area, a.years)
    if a.sample and a.sample < len(d):
        d = d.sample(n=a.sample, random_state=42).reset_index(drop=True)
    X = B.features(d, dd, B.SETS[a.featureset])
    y = np.searchsorted(B.BANDS, d["label_rating"].to_numpy())
    g = (np.floor(d["x"] / 2000).astype(int).astype(str) + "_" + np.floor(d["y"] / 2000).astype(int).astype(str)).to_numpy()
    P = {v: np.zeros((len(d), K)) for v in ("balanced", "balanced_T", "unweighted", "unweighted_T")}
    temps = {"balanced": [], "unweighted": []}
    for fold, (tr, te) in enumerate(GroupKFold(n_splits=5).split(X, groups=g)):
        ub = np.unique(g[tr]); rng = np.random.default_rng(fold); rng.shuffle(ub)
        cal_b = set(ub[: max(1, len(ub) // 5)])
        cal = tr[np.isin(g[tr], list(cal_b))]; fit = tr[~np.isin(g[tr], list(cal_b))]
        for w, name in (("balanced", "balanced"), (None, "unweighted")):
            m = lgb.LGBMClassifier(class_weight=w, **B.LGBM).fit(X.iloc[fit], y[fit])
            t = fit_T(logits(m, X.iloc[cal]), y[cal]); temps[name].append(t)
            zt = logits(m, X.iloc[te])
            P[name][te] = softmax(zt, axis=1)
            P[f"{name}_T"][te] = softmax(zt / t, axis=1)
        print(f"  fold {fold}: T balanced {temps['balanced'][-1]:.2f}, unweighted {temps['unweighted'][-1]:.2f}", flush=True)
    rows, rel = [], []
    for v, p in P.items():
        pred = np.array(B.BANDS)[p.argmax(1)]
        rows.append({"area": a.area, "featureset": a.featureset, "variant": v, "n": len(y),
                     "temperature_mean": np.mean(temps[v.replace("_T", "")]) if v.endswith("_T") else 1.0,
                     **B.cls_metrics(d["label_rating"].to_numpy(), pred),
                     "nll": -np.log(p[np.arange(len(y)), y] + 1e-12).mean(),
                     "brier": ((p - np.eye(K)[y]) ** 2).sum(1).mean(), "ece_top": ece_top(p, y), "ece_classwise": ece_classwise(p, y)})
        conf = p.max(1); b = np.clip((conf * 10).astype(int), 0, 9); ok = p.argmax(1) == y
        for i in range(10):
            if (b == i).any():
                rel.append({"variant": v, "bin": f"{i / 10:.1f}-{(i + 1) / 10:.1f}", "n": int((b == i).sum()),
                            "confidence": conf[b == i].mean(), "accuracy": ok[b == i].mean()})
    out = B.DATA / a.area / "model/results"
    r = pd.DataFrame(rows)
    r.round(4).to_csv(keep(out / f"calibration_methods_{tag}.csv"), index=False)
    pd.DataFrame(rel).round(4).to_csv(keep(out / f"reliability_methods_{tag}.csv"), index=False)
    print(r[["variant", "temperature_mean", "accuracy", "macro_f1", "qwk", "nll", "brier", "ece_top", "ece_classwise"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
