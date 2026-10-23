"""How much local data does a model from another city need? Calibration and adaptation for transfer.

    python transfer_calibrate.py [--year 2024] [--sample 50000] [--seeds 2]

Directions: London -> Belfast and Belfast -> London (London: random sample of --sample certificates). Features: the
core set of transfer.py (satellite, climate, morphology, streets, LiDAR; in both areas). For every seed the target's
2 km blocks are split in half: test blocks (fixed) and a pool from which k% of the target certificates (whole blocks)
are drawn as local labels, k in 0, 1, 2, 5, 10, 25, 50.
Methods (same test blocks for all):
  zero_shot            source model as it is
  standardised         features z-scored within each city before training and prediction (removes level differences,
                       e.g. a warmer or cloudier city), no target labels
  prior_em             zero-shot classifier with target band priors re-estimated by EM (Saerens et al. 2002), no
                       target labels; SAP unchanged
  bias_k               zero-shot plus the mean SAP error on the k% local labels subtracted (bands from corrected SAP)
  pooled_k             trained on source + k% target certificates (target rows weighted to equal the source)
  local_k              trained on the k% target certificates only
Metrics on the test blocks: accuracy, macro-F1, quadratic kappa, within one band, SAP MAE, mean SAP bias.
Output: data/model_transfer/calibration_<year>.csv
"""
import argparse, pathlib, sys, time
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import mean_absolute_error
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import baseline as B
import transfer as T
from safeio import keep                      # existing outputs are archived, never overwritten

FRACS = [1, 2, 5, 10, 25, 50]


def fit(X, y, sap, w=None):
    yc = np.searchsorted(B.BANDS, y)
    clf = lgb.LGBMClassifier(class_weight="balanced", **B.LGBM).fit(X, yc, sample_weight=w)
    ok = ~np.isnan(sap)
    reg = lgb.LGBMRegressor(**B.LGBM).fit(X[ok], sap[ok], sample_weight=None if w is None else w[ok])
    return clf, reg


def proba(clf, X):
    p = np.zeros((len(X), len(B.BANDS))); p[:, clf.classes_] = clf.predict_proba(X)
    return p


def em_priors(p, src_prior, iters=100):
    """Saerens, Latinne & Decaestecker (2002): adjust posteriors to unknown target priors by EM."""
    q = src_prior.copy()
    for _ in range(iters):
        w = p * (q / np.maximum(src_prior, 1e-9))
        w /= w.sum(1, keepdims=True)
        q_new = w.mean(0)
        if np.abs(q_new - q).max() < 1e-6:
            break
        q = q_new
    return w


def score(y, pred, sap, psap, **kw):
    ok = ~np.isnan(sap)
    return {**kw, **B.cls_metrics(y, pred), "sap_mae": mean_absolute_error(sap[ok], psap[ok]) if psap is not None else np.nan,
            "sap_bias": float(np.mean(psap[ok] - sap[ok])) if psap is not None else np.nan, "n_test": len(y)}


def standardise(Xs, Xt):
    Xs, Xt = Xs.copy(), Xt.copy()
    for c in Xs.columns:
        if str(Xs[c].dtype) != "category":
            for X in (Xs, Xt):
                m, s = X[c].mean(), X[c].std()
                X[c] = ((X[c] - m) / (s if s and np.isfinite(s) else 1)).astype("float32")
    return Xs, Xt


def run(src_name, src, tgt_name, tgt, cols, seeds, rows):
    Xs_full = T.matrix(src, cols)
    cats = {c: Xs_full[c].cat.categories for c in Xs_full.columns if str(Xs_full[c].dtype) == "category"}
    Xt_full = T.matrix(tgt, cols, cats)
    ys, sap_s = src["label_rating"].to_numpy(), pd.to_numeric(src["label_sap"], errors="coerce").to_numpy("float64")
    yt, sap_t = tgt["label_rating"].to_numpy(), pd.to_numeric(tgt["label_sap"], errors="coerce").to_numpy("float64")
    blocks = (np.floor(tgt["x"] / 2000).astype(int).astype(str) + "_" + np.floor(tgt["y"] / 2000).astype(int).astype(str)).to_numpy()
    d = f"{src_name} -> {tgt_name}"
    # zero-shot, standardised and prior-EM do not depend on the seed's labels but are scored on each seed's test blocks
    clf0, reg0 = fit(Xs_full, ys, sap_s)
    p0, s0 = proba(clf0, Xt_full), reg0.predict(Xt_full)
    src_prior = np.bincount(np.searchsorted(B.BANDS, ys), minlength=7) / len(ys)
    Xs_z, Xt_z = standardise(Xs_full, Xt_full)
    clfz, regz = fit(Xs_z, ys, sap_s)
    pz, sz = proba(clfz, Xt_z), regz.predict(Xt_z)
    for seed in range(seeds):
        rng = np.random.default_rng(seed)
        ub = np.unique(blocks); rng.shuffle(ub)
        test_b = set(ub[: len(ub) // 2]); pool_b = ub[len(ub) // 2:]
        te = np.isin(blocks, list(test_b))
        base = {"direction": d, "seed": seed}
        rows.append(score(yt[te], np.array(B.BANDS)[p0[te].argmax(1)], sap_t[te], s0[te], method="zero_shot", k=0, **base))
        rows.append(score(yt[te], np.array(B.BANDS)[pz[te].argmax(1)], sap_t[te], sz[te], method="standardised", k=0, **base))
        pe = em_priors(p0[te], src_prior)
        rows.append(score(yt[te], np.array(B.BANDS)[pe.argmax(1)], sap_t[te], s0[te], method="prior_em", k=0, **base))
        # local labels: whole pool blocks added in random order until k% of the target certificates
        order = np.concatenate([np.flatnonzero(blocks == b) for b in pool_b])
        for k in FRACS:
            need = int(len(tgt) * k / 100)
            lab = order[:need]
            if len(lab) < 30:
                continue
            bias = float(np.nanmean(s0[lab] - sap_t[lab]))
            sb = s0[te] - bias
            rows.append(score(yt[te], B.sap_to_band(sb), sap_t[te], sb, method="bias", k=k, **base))
            Xp = pd.concat([Xs_full, Xt_full.iloc[lab]], ignore_index=True)
            for c, cat in cats.items():
                Xp[c] = pd.Categorical(Xp[c], categories=cat)
            w = np.concatenate([np.ones(len(ys)), np.full(len(lab), len(ys) / len(lab))])
            clf, reg = fit(Xp, np.concatenate([ys, yt[lab]]), np.concatenate([sap_s, sap_t[lab]]), w)
            rows.append(score(yt[te], np.array(B.BANDS)[proba(clf, Xt_full.iloc[np.flatnonzero(te)]).argmax(1)], sap_t[te],
                              reg.predict(Xt_full.iloc[np.flatnonzero(te)]), method="pooled", k=k, **base))
            clf, reg = fit(Xt_full.iloc[lab], yt[lab], sap_t[lab])
            rows.append(score(yt[te], np.array(B.BANDS)[proba(clf, Xt_full.iloc[np.flatnonzero(te)]).argmax(1)], sap_t[te],
                              reg.predict(Xt_full.iloc[np.flatnonzero(te)]), method="local", k=k, **base))
            r = rows[-2:]
            print(f"  {d} seed {seed} k {k:2d}%: pooled acc {r[0]['accuracy']:.3f} MAE {r[0]['sap_mae']:.2f} | local acc {r[1]['accuracy']:.3f} "
                  f"MAE {r[1]['sap_mae']:.2f} | bias-corrected MAE {rows[-3]['sap_mae']:.2f}", flush=True)
        z = rows[-3 * len([k for k in FRACS if int(len(tgt) * k / 100) >= 30]) - 3:]
        print(f"  {d} seed {seed}: zero-shot acc {z[0]['accuracy']:.3f} MAE {z[0]['sap_mae']:.2f} bias {z[0]['sap_bias']:+.2f} | "
              f"standardised acc {z[1]['accuracy']:.3f} MAE {z[1]['sap_mae']:.2f} | prior-EM acc {z[2]['accuracy']:.3f}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2024); ap.add_argument("--sample", type=int, default=50000)
    ap.add_argument("--seeds", type=int, default=2)
    a = ap.parse_args()
    lon, lon_dd = T.load("london", [a.year], a.sample)
    bel, bel_dd = T.load("belfast", [a.year], None)
    cols = T.common_columns([lon_dd, bel_dd], T.SETS["core_lidar"], [lon, bel])
    print(f"{len(cols)} core features", flush=True)
    rows = []
    t0 = time.time()
    run("London", lon, "Belfast", bel, cols, a.seeds, rows)
    pd.DataFrame(rows).round(4).to_csv(keep(T.OUT / f"calibration_{a.year}.csv"), index=False)
    run("Belfast", bel, "London", lon, cols, a.seeds, rows)
    pd.DataFrame(rows).round(4).to_csv(keep(T.OUT / f"calibration_{a.year}.csv"), index=False)
    s = pd.DataFrame(rows).groupby(["direction", "method", "k"])[["accuracy", "qwk", "sap_mae", "sap_bias"]].mean().round(3)
    print(s.to_string())
    print(f"written {T.OUT / f'calibration_{a.year}.csv'} ({(time.time() - t0) / 60:.0f} min)")


if __name__ == "__main__":
    main()
