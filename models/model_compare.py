"""Compare model families for the SAP score on identical spatial folds, each tuned the same way, and explain each.

    python model_compare.py --area belfast --years 2024 --featureset eo_morph [--models rf lgbm xgb mlp graph]
                            [--sample 50000] [--trials 25] [--block-km 2] [--tag <name>]

Design:
  Outer folds   5 folds of square spatial blocks, as in baseline.py. Every model sees the same folds, so differences
                between models can be tested fold by fold. All certificates of a building fall in one block.
  Tuning        nested: within each outer training set, Optuna (TPE, fixed seed) searches each model's space on 3 inner
                spatial folds. The outer test block plays no part in tuning, so the reported error is not tuned to it.
  Models        rf     random forest: bagging, a low-tuning reference
                lgbm   LightGBM: leaf-wise boosting, handles gaps and categories natively
                xgb    XGBoost: depth-wise boosting with regularisation
                mlp    neural network on a building's own features, the control for the graph model
                graph  GraphSAGE-style network: each dwelling also reads the features of its k nearest dwellings. With
                       several --years, it also reads the same building's other years (the spatiotemporal form).
                       Labels are never passed along edges, and test labels are never used.
  Explanation   tree models: SHAP (TreeExplainer) on held-out dwellings. Neural models: permutation of feature groups
                on held-out dwellings. Both are summed to the same feature groups, so explanations can be compared.
Outputs in data/<area>/model/results/:
  model_compare_<tag>.csv          MAE, R2, kappa, accuracy, within-one-band and time, per model and outer fold
  model_compare_<tag>_params.csv   the tuned settings per model and outer fold
  model_compare_<tag>_explain.csv  share of explanation per feature group and model
"""
import argparse, json, pathlib, sys, time
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold
from sklearn.neighbors import NearestNeighbors

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from baseline import DATA, SETS, cls_metrics, features, load, sap_to_band
from safeio import keep
SEED = 42


def numeric(X):
    """Numbers only, for models without native category support. Category codes are fitted on the whole table,
    which leaks no labels."""
    X = X.copy()
    for c in X.columns:
        if str(X[c].dtype) == "category":
            X[c] = X[c].cat.codes.astype("float32").where(X[c].notna())
    return X


def space_rf(t):
    return dict(n_estimators=300, max_features=t.suggest_float("max_features", 0.05, 0.5), min_samples_leaf=t.suggest_int("min_samples_leaf", 1, 20),
                max_samples=t.suggest_float("max_samples", 0.5, 1.0))


def space_lgbm(t):
    return dict(n_estimators=t.suggest_int("n_estimators", 200, 1000, step=100), learning_rate=t.suggest_float("learning_rate", 0.01, 0.15, log=True),
                num_leaves=t.suggest_int("num_leaves", 15, 127, log=True), min_child_samples=t.suggest_int("min_child_samples", 5, 100, log=True),
                colsample_bytree=t.suggest_float("colsample_bytree", 0.1, 0.8), subsample=t.suggest_float("subsample", 0.5, 1.0),
                reg_lambda=t.suggest_float("reg_lambda", 1e-3, 10, log=True))


def space_xgb(t):
    return dict(n_estimators=t.suggest_int("n_estimators", 200, 1000, step=100), learning_rate=t.suggest_float("learning_rate", 0.01, 0.15, log=True),
                max_depth=t.suggest_int("max_depth", 3, 10), min_child_weight=t.suggest_float("min_child_weight", 1, 50, log=True),
                colsample_bytree=t.suggest_float("colsample_bytree", 0.1, 0.8), subsample=t.suggest_float("subsample", 0.5, 1.0),
                reg_lambda=t.suggest_float("reg_lambda", 1e-3, 10, log=True))


def space_net(t):
    return dict(hidden=t.suggest_categorical("hidden", [64, 128, 256]), dropout=t.suggest_float("dropout", 0.0, 0.5), lr=t.suggest_float("lr", 3e-4, 3e-3, log=True),
                weight_decay=t.suggest_float("weight_decay", 1e-6, 1e-2, log=True), k=t.suggest_categorical("k", [5, 10, 20]))


SPACES = dict(rf=space_rf, lgbm=space_lgbm, xgb=space_xgb, mlp=space_net, graph=space_net)


class Net:
    """Full-batch network in plain PyTorch. With k > 0, two GraphSAGE layers read each dwelling and the mean of its neighbours."""

    def __init__(self, graph, hidden, dropout, lr, weight_decay, k, epochs=300, patience=30):
        self.graph, self.hidden, self.dropout, self.lr, self.wd, self.k, self.epochs, self.patience = graph, hidden, dropout, lr, weight_decay, k, epochs, patience

    def _edges(self, xy, years, ids):
        """Each dwelling's k nearest dwellings of the same year, plus the same building in other years."""
        import torch
        src, dst = [], []
        for yr in np.unique(years):
            i = np.where(years == yr)[0]
            n = min(self.k + 1, len(i))
            nb = NearestNeighbors(n_neighbors=n).fit(xy[i]).kneighbors(xy[i], return_distance=False)
            src.append(i[nb[:, 1:]].ravel())
            dst.append(np.repeat(i, n - 1))
        frame = pd.DataFrame({"i": np.arange(len(ids)), "b": ids})
        if frame["b"].nunique() < len(frame):
            pairs = frame.merge(frame, on="b")
            pairs = pairs[pairs["i_x"] != pairs["i_y"]]
            src.append(pairs["i_y"].to_numpy())
            dst.append(pairs["i_x"].to_numpy())
        return torch.as_tensor(np.concatenate(src)), torch.as_tensor(np.concatenate(dst))

    def _model(self, n):
        import torch
        from torch import nn
        graph, h, drop = self.graph, self.hidden, self.dropout

        class M(nn.Module):
            def __init__(s):
                super().__init__()
                s.a = nn.Linear(n * (2 if graph else 1), h)
                s.b = nn.Linear(h * (2 if graph else 1), h)
                s.out = nn.Linear(h, 1)
                s.drop = nn.Dropout(drop)

            def mean(s, x, e):
                total = torch.zeros_like(x).index_add_(0, e[1], x[e[0]])
                count = torch.zeros(len(x), device=x.device).index_add_(0, e[1], torch.ones(len(e[1]), device=x.device)).clamp(min=1)
                return total / count[:, None]

            def forward(s, x, e):
                u = torch.cat([x, s.mean(x, e)], 1) if graph else x
                u = s.drop(torch.relu(s.a(u)))
                v = torch.cat([u, s.mean(u, e)], 1) if graph else u
                return s.out(s.drop(torch.relu(s.b(v))))[:, 0]
        return M()

    def fit_predict(self, X, y, tr, te, xy, years, ids):
        """Fits on tr and predicts te. Scaling and gap-filling use tr only. The graph spans all dwellings' features."""
        import torch
        torch.manual_seed(SEED)
        rng = np.random.default_rng(SEED)
        med = np.nanmedian(X[tr], axis=0)
        med = np.where(np.isnan(med), 0, med)
        Z = np.where(np.isnan(X), med, X)
        mu, sd = Z[tr].mean(0), Z[tr].std(0) + 1e-6
        Z = np.clip((Z - mu) / sd, -8, 8).astype("float32")
        ybar, ysd = y[tr].mean(), y[tr].std()
        x = torch.as_tensor(Z)
        t = torch.as_tensor(((y - ybar) / ysd).astype("float32"))
        e = self._edges(xy, years, ids) if self.graph else (torch.zeros(1, dtype=torch.long), torch.zeros(1, dtype=torch.long))
        order = rng.permutation(tr)
        cut = max(1, len(order) // 10)
        val, fit = torch.as_tensor(order[:cut]), torch.as_tensor(order[cut:])
        m = self._model(Z.shape[1])
        opt = torch.optim.AdamW(m.parameters(), lr=self.lr, weight_decay=self.wd)
        best, best_state, wait = 1e9, None, 0
        for _ in range(self.epochs):
            m.train()
            opt.zero_grad()
            loss = torch.nn.functional.huber_loss(m(x, e)[fit], t[fit])
            loss.backward()
            opt.step()
            m.eval()
            with torch.no_grad():
                v = torch.nn.functional.l1_loss(m(x, e)[val], t[val]).item()
            if v < best - 1e-4:
                best, wait, best_state = v, 0, {k: p.clone() for k, p in m.state_dict().items()}
            else:
                wait += 1
                if wait >= self.patience:
                    break
        m.load_state_dict(best_state)
        self.m, self.e, self.ybar, self.ysd, self.med, self.mu, self.sd = m, e, ybar, ysd, med, mu, sd
        return self.predict(X)[te]

    def predict(self, X):
        import torch
        Z = np.where(np.isnan(X), self.med, X)
        Z = np.clip((Z - self.mu) / self.sd, -8, 8).astype("float32")
        self.m.eval()
        with torch.no_grad():
            return self.m(torch.as_tensor(Z), self.e).numpy() * self.ysd + self.ybar


def make_tree(name, params):
    if name == "rf":
        return RandomForestRegressor(n_jobs=-1, random_state=SEED, **params)
    if name == "lgbm":
        import lightgbm as lgb
        return lgb.LGBMRegressor(max_bin=63, subsample_freq=1, force_col_wise=True, verbose=-1, random_state=SEED, **params)
    import xgboost as xgb
    return xgb.XGBRegressor(tree_method="hist", max_bin=63, random_state=SEED, n_jobs=-1, enable_categorical=True, **params)


def run_once(name, params, data, tr, te):
    X, Xn, y, xy, years, ids = data
    if name in ("mlp", "graph"):
        p = dict(params)
        net = Net(name == "graph", **p)
        return net.fit_predict(Xn.to_numpy("float32"), y, tr, te, xy, years, ids), net
    if name == "rf":
        fill = Xn.iloc[tr].median().fillna(0)
        m = make_tree(name, params).fit(Xn.iloc[tr].fillna(fill), y[tr])
        return m.predict(Xn.iloc[te].fillna(fill)), m
    m = make_tree(name, params).fit(X.iloc[tr], y[tr])
    return m.predict(X.iloc[te]), m


def tune(name, data, tr, blocks, trials, max_rows):
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    rng = np.random.default_rng(SEED)
    pool = tr if len(tr) <= max_rows else rng.choice(tr, max_rows, replace=False)
    inner = list(GroupKFold(n_splits=3).split(pool, groups=blocks[pool]))

    def goal(t):
        params = SPACES[name](t)
        errs = []
        for a, b in inner:
            p, _ = run_once(name, params, data, pool[a], pool[b])
            errs.append(mean_absolute_error(data[2][pool[b]], p))
        return float(np.mean(errs))
    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=SEED))
    study.optimize(goal, n_trials=trials)
    t = optuna.trial.FixedTrial(study.best_params)
    return SPACES[name](t), study.best_value


def explain(name, model, data, te, group_of, n=2000):
    """Share of mean absolute attribution per feature group, on held-out dwellings."""
    X, Xn, y, *_ = data
    rng = np.random.default_rng(SEED)
    pick = te if len(te) <= n else rng.choice(te, n, replace=False)
    groups = pd.Series(X.columns).map(group_of).fillna("other").to_numpy()
    out = {}
    if name in ("mlp", "graph"):
        A = Xn.to_numpy("float32")
        base = mean_absolute_error(y[pick], model.predict(A)[pick])
        for g in np.unique(groups):
            B = A.copy()
            cols = np.where(groups == g)[0]
            B[np.ix_(pick, cols)] = B[np.ix_(rng.permutation(pick), cols)]
            out[g] = max(0.0, mean_absolute_error(y[pick], model.predict(B)[pick]) - base)
    else:
        import shap
        Z = Xn.iloc[pick].fillna(Xn.median().fillna(0)) if name == "rf" else X.iloc[pick]
        if name == "rf":
            Z = Z.iloc[:300]    # exact SHAP on forests is slow
        if name == "xgb":    # XGBoost's own exact TreeSHAP; the shap package cannot read this XGBoost version's model
            import xgboost as xgb
            vals = np.abs(model.get_booster().predict(xgb.DMatrix(Z, enable_categorical=True), pred_contribs=True)[:, :-1]).mean(0)
        else:
            vals = np.abs(shap.TreeExplainer(model).shap_values(Z)).mean(0)
        for g in np.unique(groups):
            out[g] = float(vals[groups == g].sum())
    total = sum(out.values()) or 1
    return {k: v / total for k, v in out.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--years", nargs="+", type=int, required=True)
    ap.add_argument("--featureset", default="eo_morph"); ap.add_argument("--models", nargs="+", default=list(SPACES))
    ap.add_argument("--sample", type=int, default=50000); ap.add_argument("--trials", type=int, default=25)
    ap.add_argument("--tune-rows", type=int, default=15000); ap.add_argument("--block-km", type=float, default=2.0)
    ap.add_argument("--folds", type=int, default=5); ap.add_argument("--tag")
    a = ap.parse_args()
    tag = a.tag or f"{'-'.join(map(str, a.years))}_{a.featureset}_s{a.sample // 1000}k"
    d, dd = load(a.area, a.years)
    d = d[pd.to_numeric(d["label_sap"], errors="coerce").notna()]
    if a.sample < len(d):
        d = d.sample(n=a.sample, random_state=SEED)
    d = d.reset_index(drop=True)
    X = features(d, dd, SETS[a.featureset])
    for c in X.columns:
        if str(X[c].dtype) == "category":    # XGBoost accepts text categories only
            X[c] = X[c].astype("string").astype("category")
    Xn = numeric(X)
    y = pd.to_numeric(d["label_sap"]).to_numpy("float32")
    xy = d[["x", "y"]].to_numpy("float64")
    blocks = (np.floor(d["x"] / (a.block_km * 1000)).astype(int).astype(str) + "_" + np.floor(d["y"] / (a.block_km * 1000)).astype(int).astype(str)).to_numpy()
    data = (X, Xn, y, xy, d["year"].to_numpy(), d["id_fp"].astype(str).to_numpy())
    folds = list(GroupKFold(n_splits=a.folds).split(d, groups=blocks))
    group_of = dd.set_index("column")["group"].to_dict()
    print(a.area, a.years, len(d), "certificates", X.shape[1], "features", pd.Series(blocks).nunique(), "blocks", flush=True)
    res = DATA / a.area / "model" / "results"
    rows, params_out, expl = [], [], []
    bands = sap_to_band(y)
    for name in a.models:
        for f, (tr, te) in enumerate(folds):
            t0 = time.time()
            params, inner = tune(name, data, tr, blocks, a.trials, a.tune_rows)
            t1 = time.time()
            pred, model = run_once(name, params, data, tr, te)
            r = dict(area=a.area, years="-".join(map(str, a.years)), model=name, fold=f, n_test=len(te), mae=mean_absolute_error(y[te], pred), r2=r2_score(y[te], pred),
                     tune_seconds=round(t1 - t0), fit_seconds=round(time.time() - t1), inner_mae=inner, **cls_metrics(bands[te], sap_to_band(pred)))
            rows.append(r)
            params_out.append(dict(model=name, fold=f, params=json.dumps(params)))
            if f == 0:
                expl += [dict(model=name, group=k, share=v) for k, v in explain(name, model, data, te, group_of).items()]
            print(name, f, round(r["mae"], 2), round(r["r2"], 3), round(r["qwk"], 3), f"tune {r['tune_seconds']}s", flush=True)
            for frame, suffix in ((rows, ""), (params_out, "_params"), (expl, "_explain")):
                pd.DataFrame(frame).to_csv(res / f"model_compare_{tag}{suffix}.partial.csv", index=False)
    for frame, suffix in ((rows, ""), (params_out, "_params"), (expl, "_explain")):
        path = res / f"model_compare_{tag}{suffix}.csv"
        keep(path)
        pd.DataFrame(frame).to_csv(path, index=False)
        (res / f"model_compare_{tag}{suffix}.partial.csv").unlink()
    print(pd.DataFrame(rows).groupby("model")[["mae", "r2", "qwk", "accuracy", "within_one_band"]].agg(["mean", "std"]).round(3).to_string())


if __name__ == "__main__":
    main()
