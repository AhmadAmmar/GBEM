"""Results tables for the thesis, written as LaTeX from the results files (one file per table).

    python thesis_tables.py [--out <dir>]        default: Manuscripts/02_Thesis/generated/tables

Every table is regenerated from data/*/model/results, data/*/analysis and data/model_transfer, so the thesis text never
holds a number typed by hand. A table whose results file is missing is written as a short note instead, and the build
log lists it. Captions sit above tables (Ulster University format); labels are tab:<name> for cross-references.
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd

CODE = pathlib.Path(__file__).resolve().parents[1]
PHD = CODE.parent
DATA = PHD / "data"
FS = {"eo": "Satellite (EO) only", "eo_morph_nolidar": "EO + building form", "eo_morph": "EO + form + LiDAR",
      "eo_morph_floor": "EO + form + LiDAR + floor position", "eo_morph_fps": "EO + form + LiDAR + footprint statistics",
      "eo_morph_phys": "EO + form + LiDAR + envelope geometry", "eo_morph_floor_phys": "EO + form + LiDAR + floor + geometry",
      "eo_morph_ctx": "EO + form + LiDAR + Census context", "all": "Reference: + certificate attributes",
      "embed": "Satellite embeddings only", "eo_embed": "EO + satellite embeddings", "eo_morph_embed": "EO + form + LiDAR + embeddings",
      "core": "All open features", "spectral": "Spectral and thermal", "form_physics": "Form, LiDAR and geometry",
      "core_phys": "All open features + geometry"}
ORDER = list(FS)
AREA = {"london": "London", "belfast": "Belfast"}
MISSING = []


def tex(s):
    return str(s).replace("&", r"\&").replace("%", r"\%").replace("_", r"\_").replace("#", r"\#")


def num(v, d=2):
    return "--" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.{d}f}"


def table(name, caption, header, rows, align, note=None, size=r"\small"):
    lines = [r"\begin{table}[htbp]", r"\centering", size, rf"\caption{{{caption}}}\label{{tab:{name}}}",
             r"\begin{adjustbox}{max width=\linewidth}", rf"\begin{{tabular}}{{{align}}}", r"\toprule",
             " & ".join(header) + r" \\", r"\midrule"]
    for r in rows:
        lines.append(r"\midrule" if r == "MID" else " & ".join(r) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{adjustbox}"]
    if note:
        lines.append(rf"\par\smallskip\parbox{{0.95\linewidth}}{{\footnotesize {note}}}")
    lines.append(r"\end{table}")
    return "\n".join(lines) + "\n"


def missing(name, what):
    MISSING.append(name)
    return (f"% table {name}: {what} not available yet\n\\begin{{table}}[htbp]\\centering\\small\n"
            f"\\caption{{Results pending: {tex(what)}.}}\\label{{tab:{name}}}\n"
            f"\\fbox{{\\parbox{{0.9\\linewidth}}{{\\centering The table is generated when the results are available.}}}}\n\\end{{table}}\n")


def read(p):
    p = DATA / p
    return pd.read_csv(p) if p.exists() else None


def baselines():
    rows, notes = [], []
    for area, tag in (("london", "2024_s50k"), ("belfast", "2024")):
        frames = [read(f"{area}/model/results/baseline_{tag}.csv")] + \
                 [pd.read_csv(p) for p in sorted((DATA / area / "model/results").glob(f"baseline_{tag}_*.csv"))]
        frames = [f for f in frames if f is not None]
        if not frames:
            continue
        b = pd.concat(frames).drop_duplicates(["featureset", "validation", "model", "target"], keep="last")
        b = b[b.model == "lgbm"]
        n = int(b["n"].max())
        count = f"{n:,}".replace(",", "{,}")
        sample = ", random sample" if area == "london" else ""
        rows.append([rf"\multicolumn{{7}}{{l}}{{\textbf{{{AREA[area]}}} ({count} certificates, 2024{sample})}}"])
        for fs in [f for f in ORDER if f in set(b.featureset)]:
            band = b[(b.featureset == fs) & (b.validation == "spatial") & (b.target == "band")]
            sap = b[(b.featureset == fs) & (b.validation == "spatial") & (b.target == "sap")]
            if band.empty:
                continue
            band, sap = band.iloc[0], (sap.iloc[0] if len(sap) else None)
            rows.append([tex(FS[fs]), num(100 * band.accuracy, 1), num(band.macro_f1), num(band.qwk),
                         num(100 * band.within_one_band, 1), num(sap.mae, 1) if sap is not None else "--",
                         num(sap.r2) if sap is not None else "--"])
        rows.append("MID")
    if not rows:
        return missing("baselines", "baseline results")
    rows = rows[:-1]
    return table("baselines", "Predictive performance of the gradient-boosting models by feature set under spatial "
                 "cross-validation (five folds of 2 km blocks). Band metrics refer to the seven EPC bands; SAP metrics "
                 "to the SAP score (1--100).",
                 ["Feature set", "Accuracy (\\%)", "Macro-F1", "$\\kappa_w$", "Within one band (\\%)", "SAP MAE", "SAP $R^2$"],
                 rows, "lrrrrrr", note="$\\kappa_w$: quadratic weighted kappa. The reference model uses attributes "
                 "recorded on the certificate and is not available for homes without one.")


def embeddings():
    rows = []
    for area, tag in (("london", "2024_s50k_embed"), ("belfast", "2024_embed")):
        b = read(f"{area}/model/results/baseline_{tag}.csv")
        if b is None:
            continue
        b = b[(b.model == "lgbm") & (b.validation == "spatial")]
        for fs in ("eo", "embed", "eo_embed", "eo_morph", "eo_morph_embed"):
            band, sap = b[(b.featureset == fs) & (b.target == "band")], b[(b.featureset == fs) & (b.target == "sap")]
            if len(band):
                rows.append([AREA[area], tex(FS[fs]), num(100 * band.accuracy.iat[0], 1), num(band.qwk.iat[0]),
                             num(sap.mae.iat[0], 1) if len(sap) else "--", num(sap.r2.iat[0]) if len(sap) else "--"])
        rows.append("MID")
    if not rows:
        return missing("embeddings", "satellite embedding comparison")
    return table("embeddings", "Engineered satellite features and pretrained annual satellite embeddings under the same "
                 "spatial cross-validation.", ["Area", "Feature set", "Accuracy (\\%)", "$\\kappa_w$", "SAP MAE", "SAP $R^2$"],
                 rows[:-1], "llrrrr")


def validation_design():
    rows = []
    for area, tag in (("london", "2024_s50k"), ("belfast", "2024")):
        frames = [read(f"{area}/model/results/baseline_{tag}.csv")] + \
                 [pd.read_csv(p) for p in sorted((DATA / area / "model/results").glob(f"baseline_{tag}_*.csv"))]
        frames = [f for f in frames if f is not None]
        if not frames:
            continue
        b = pd.concat(frames).drop_duplicates(["featureset", "validation", "model", "target"], keep="last")
        b = b[(b.model == "lgbm") & (b.target == "sap")]
        for fs in ("eo", "eo_morph", "all"):
            s, r = b[(b.featureset == fs) & (b.validation == "spatial")], b[(b.featureset == fs) & (b.validation == "random")]
            if len(s) and len(r):
                s, r = s.iloc[0], r.iloc[0]
                rows.append([AREA[area], tex(FS[fs]), num(r.r2), num(s.r2), num(r.r2 - s.r2), num(r.mae, 1), num(s.mae, 1)])
    if not rows:
        return missing("validation_design", "random and spatial results")
    return table("validation_design", "Estimated predictive performance for the SAP score under random and spatial "
                 "cross-validation of the same models.",
                 ["Area", "Feature set", "$R^2$ random", "$R^2$ spatial", "Difference", "MAE random", "MAE spatial"],
                 rows, "llrrrrr", note="Random: five folds drawn at random, so that test homes have close neighbours in "
                 "the training data. Spatial: five folds of 2 km blocks.")


def retest():
    rows = []
    for area in ("london", "belfast"):
        g = read(f"{area}/analysis/ground_truth_retest.csv")
        if g is None:
            continue
        g = g.iloc[0]
        rows.append([AREA[area], f"{int(g.pairs):,}".replace(",", "{,}"), num(100 * g.same_band, 1), num(100 * g.within_one_band, 1),
                     num(g.qwk), num(g.sap_abs_diff_mean, 1), num(g.sap_abs_diff_median, 0), num(g.sap_abs_diff_p90, 0)])
    if not rows:
        return missing("retest", "test-retest results")
    return table("retest", "Agreement between two certificates of the same dwelling issued within 365 days with the "
                 "same main fuel, property type and floor area (test--retest).",
                 ["Area", "Pairs", "Same band (\\%)", "Within one band (\\%)", "$\\kappa_w$", "Mean |$\\Delta$SAP|",
                  "Median", "90th pct."], rows, "lrrrrrrr")


def scale():
    rows = []
    for area, tag in (("london", "2024_s50k"), ("belfast", "2024")):
        s = read(f"{area}/model/results/scale_{tag}.csv")
        if s is None:
            continue
        for fs in ("eo_morph", "eo_morph_floor", "all"):
            t = s[s.featureset == fs]
            if t.empty:
                continue
            row = [AREA[area], tex(FS[fs])]
            for sc in ("certificate", "street", "250 m cell", "neighbourhood"):
                u = t[t.scale == sc]
                row.append(num(u.r2.iat[0]) if len(u) else "--")
            rows.append(row)
    if not rows:
        return missing("scale", "scale results")
    return table("scale", "Coefficient of determination ($R^2$) between predicted and certified SAP scores after "
                 "aggregation to increasing spatial units (out-of-fold predictions, spatial cross-validation).",
                 ["Area", "Feature set", "Dwelling", "Street", "250 m cell", "Neighbourhood"], rows, "llrrrr",
                 note="Neighbourhood: LSOA 2021 (London), electoral ward 2012 (Belfast). Units with fewer than five "
                 "certificates are excluded.")


def neighbours():
    rows = []
    for area in ("london", "belfast"):
        n, bs = read(f"{area}/model/results/neighbour_baseline_2024.csv"), read(f"{area}/model/results/neighbour_bootstrap_2024.csv")
        if n is None:
            continue
        m = n.groupby(["scenario", "model"]).sap_mae.mean().unstack()
        ci = bs.groupby("scenario")[["ci_low", "ci_high"]].mean() if bs is not None else None
        for sc in ("gap filling", "unseen area 1 km", "unseen area 2 km", "unseen area 5 km"):
            if sc not in m.index:
                continue
            r = m.loc[sc]
            c = f"[{num(ci.loc[sc, 'ci_low'], 1)}, {num(ci.loc[sc, 'ci_high'], 1)}]" if ci is not None and sc in ci.index else "--"
            rows.append([AREA[area], tex(sc), num(r.get("knn"), 1), num(r.get("neighbours"), 1), num(r.get("eo_morph"), 1),
                         num(r.get("eo_morph+nb"), 1), c])
        rows.append("MID")
    if not rows:
        return missing("neighbours", "neighbour baseline results")
    return table("neighbours", "Mean absolute error of the SAP score (points) for interpolation from neighbouring "
                 "certificates and for models built from open EO and building data, in two deployment scenarios.",
                 ["Area", "Scenario", "IDW (10 nearest)", "Neighbour features", "EO + form", "EO + form + neighbours",
                  "Difference, 95\\% CI"], rows[:-1], "llrrrrr",
                 note="Gap filling: dwellings held out by building within surveyed areas. Unseen area: all certificates "
                 "inside held-out square blocks of the given size. Difference: EO + form + neighbours minus IDW, "
                 "bootstrap over 1 km cells; means over two random seeds.")


def targets():
    rows = []
    for area in ("london", "belfast"):
        t = read(f"{area}/model/results/metric_targets_{2024}.csv")
        if t is None:
            continue
        for _, r in t.iterrows():
            name = {"fabric": "Fabric heat demand (kWh/m$^2$, U-values as described)", "heating": "Main heating efficiency (1--5)",
                    "gas heated": "Mains gas as main fuel", "sap": "SAP score"}.get(r.target, tex(r.target))
            metric = (f"$R^2$ {num(r.r2)}; $\\rho$ {num(r.spearman)}" if r.target in ("fabric", "sap") else
                      f"$\\kappa_w$ {num(r.qwk)}; accuracy {num(100 * r.accuracy, 1)}\\%" if r.target == "heating" else
                      f"AUC {num(r.auc)} (prevalence {num(100 * r.prevalence, 0)}\\%)")
            rows.append([AREA[area], name, f"{int(r.n):,}".replace(",", "{,}"), metric])
        rows.append("MID")
    if not rows:
        return missing("targets", "alternative target results")
    return table("targets", "Predictive performance for components of the rating (open EO, form, LiDAR and envelope "
                 "geometry; spatial cross-validation).", ["Area", "Target", "Certificates", "Performance"], rows[:-1], "llrl")


def transfer():
    t = read("model_transfer/transfer_2024.csv")
    if t is None:
        return missing("transfer", "transfer results")
    extra = DATA / "model_transfer/transfer_2024_physics.csv"
    if extra.exists():
        t = pd.concat([t, pd.read_csv(extra)])
    t = t[~t.experiment.str.contains("20(?:2[0-3]|25)", regex=True) | t.experiment.str.contains("within")]
    rows = []
    for fs in [f for f in ("core", "spectral", "form_physics", "core_phys") if f in set(t.featureset)]:
        u = t[t.featureset == fs]
        get = lambda e: u[u.experiment == e]
        wl, wb = get("within London 2024 (spatial 5-fold CV)"), get("within Belfast 2024 (spatial 5-fold CV)")
        lb, bl = get("London -> Belfast 2024"), get("Belfast -> London 2024")
        if lb.empty or bl.empty:
            continue
        rows.append([tex(FS[fs]), num(wb.sap_mae.iat[0], 1) if len(wb) else "--", num(lb.sap_mae.iat[0], 1),
                     num(lb.mean_sap_pred.iat[0] - lb.mean_sap_actual.iat[0], 1),
                     num(wl.sap_mae.iat[0], 1) if len(wl) else "--", num(bl.sap_mae.iat[0], 1),
                     num(bl.mean_sap_pred.iat[0] - bl.mean_sap_actual.iat[0], 1)])
    if not rows:
        return missing("transfer", "transfer results")
    return table("transfer", "SAP mean absolute error within each city (spatial cross-validation) and after transfer "
                 "between cities without local labels, by feature family.",
                 ["Features", "Belfast (within)", "London$\\rightarrow$Belfast", "Bias", "London (within)",
                  "Belfast$\\rightarrow$London", "Bias"], rows, "lrrrrrr",
                 note="Bias: mean predicted minus mean certified SAP in the target city. Common features only.")


def typology():
    rows = []
    for area in ("london", "belfast"):
        s = read(f"{area}/analysis/morph_types_summary.csv")
        if s is None:
            continue
        for _, r in s.sort_values("sap_mean", ascending=False).iterrows():
            rows.append([AREA[area], tex(r.type), str(int(r.cells)), f"{int(r.certificates):,}".replace(",", "{,}"),
                         num(r.sap_mean, 1), num(100 * r.share_AC, 0), num(100 * r.poor_walls, 0), num(100 * r.poor_roof, 0)])
        rows.append("MID")
    if not rows:
        return missing("typology", "urban form typology")
    return table("typology", "Urban form types of 250 m cells (k-means on building and street form) with the certificates of "
                 "2020--2025 in each type.",
                 ["Area", "Type", "Cells", "Certificates", "Mean SAP", "A--C (\\%)", "Poor walls (\\%)", "Poor roof (\\%)"],
                 rows[:-1], "lp{5.2cm}rrrrrr", size=r"\footnotesize")


def retrofit():
    rows = []
    label = {"walls": "Walls", "roof": "Roof", "windows": "Windows", "mainheat": "Main heating", "controls": "Heating controls",
             "hotwater": "Hot water", "fabric": "Any fabric element"}
    for area, tag in (("london", "2024_s50k"), ("belfast", "2024")):
        r = read(f"{area}/model/results/retrofit_needs_{tag}_eo_morph.csv")
        if r is None:
            continue
        for _, x in r.iterrows():
            rows.append([AREA[area], label.get(x.element, tex(x.element)), num(100 * x.prevalence, 0), num(x.auc),
                         num(x.avg_precision), num(x.lift_top20, 1)])
        rows.append("MID")
    if not rows:
        return missing("retrofit", "retrofit-need models")
    return table("retrofit", "Prediction of elements rated poor or very poor on the certificate from open EO, form and LiDAR "
                 "(spatial cross-validation).", ["Area", "Element", "Prevalence (\\%)", "AUC", "Average precision",
                 "Lift in top 20\\%"], rows[:-1], "llrrrr")


def adaptation():
    c = read("model_transfer/calibration_2024.csv")
    if c is None:
        return missing("adaptation", "transfer calibration")
    m = c.groupby(["direction", "method", "k"])[["qwk", "sap_mae", "sap_bias"]].mean().reset_index()
    name = {"zero_shot": "Zero-shot", "standardised": "Standardised features", "prior_em": "Prior re-estimation (EM)",
            "bias": "Bias correction", "pooled": "Pooled training", "local": "Local data only"}
    pick = [("zero_shot", 0), ("standardised", 0), ("prior_em", 0), ("bias", 10), ("pooled", 2), ("pooled", 10),
            ("pooled", 50), ("local", 10), ("local", 50)]
    rows = []
    for meth, k in pick:
        row = [name[meth], str(k)]
        for d in ("London -> Belfast", "Belfast -> London"):
            r = m[(m.direction == d) & (m.method == meth) & (m.k == k)]
            row += [num(r.qwk.iat[0]), num(r.sap_mae.iat[0], 1), num(r.sap_bias.iat[0], 1)] if len(r) else ["--"] * 3
        rows.append(row)
    return table("adaptation", "Transfer between cities with and without local certificates: ordinal agreement, SAP error "
                 "and bias on the same test blocks of the target city (means over two seeds).",
                 ["Method", "Local (\\%)", "$\\kappa_w$", "MAE", "Bias", "$\\kappa_w$", "MAE", "Bias"], rows, "lrrrrrrr",
                 note="Columns 3--5: London$\\rightarrow$Belfast; columns 6--8: Belfast$\\rightarrow$London. Local: share of "
                 "target certificates used, drawn as whole 2 km blocks from the half of the target city not used for testing.")


def temporal():
    t = read("model_transfer/transfer_2024.csv")
    if t is None:
        return missing("temporal", "temporal transfer")
    t = t[t.featureset == "core"]
    rows = []
    for area in ("london", "belfast"):
        for e in (f"{area}: within 2024 (spatial 5-fold CV)", f"{area}: 2020-22 -> 2024", f"{area}: within 2025 (spatial 5-fold CV)",
                  f"{area}: 2020-22 -> 2025", f"{area}: 2020-23 -> 2025"):
            r = t[t.experiment == e]
            if len(r):
                r = r.iloc[0]
                rows.append([AREA[area], tex(e.split(": ", 1)[1].replace("2020-2", "2020--2").replace("->", "$\\rightarrow$").replace("(spatial 5-fold CV)", "(spatial CV)")),
                             num(r.qwk), num(r.sap_mae, 1), num(r.mean_sap_pred - r.mean_sap_actual, 1)])
        rows.append("MID")
    return table("temporal", "Temporal transfer: models trained on certificates of earlier years applied to later years, "
                 "compared with spatial cross-validation within the later year.",
                 ["Area", "Training $\\rightarrow$ test", "$\\kappa_w$", "SAP MAE", "Bias"], rows[:-1], "llrrr",
                 note="Bias: mean predicted minus mean certified SAP in the test year.")


def aoa():
    a = read("model_transfer/aoa_2024.csv")
    if a is None:
        return missing("aoa", "area of applicability")
    rows = [[tex(r.experiment), num(100 * r.share_outside_aoa, 1), num(r.sap_mae_inside, 1), num(r.sap_mae_outside, 1)]
            for _, r in a.iterrows()]
    return table("aoa", "Share of dwellings outside the area of applicability (dissimilarity index above the threshold "
                 "of the training data) and SAP error inside and outside it.",
                 ["Experiment", "Outside AOA (\\%)", "MAE inside", "MAE outside"], rows, "lrrr")


def calibration():
    rows = []
    for area, f in (("london", "london/model/results/calibration_methods_2024_s50k_eo_morph_floor.csv"),
                    ("belfast", "belfast/model/results/calibration_methods_2024_eo_morph.csv")):
        c = read(f)
        if c is None:
            continue
        for _, r in c.iterrows():
            rows.append([AREA[area], tex(FS.get(r.featureset, r.featureset)), tex(r.variant.replace("_T", " + temperature")),
                         num(r.temperature_mean), num(100 * r.accuracy, 1), num(r.nll), num(r.ece_top, 3)])
        rows.append("MID")
    if not rows:
        return missing("calibration", "probability calibration")
    return table("calibration", "Calibration of the predicted band probabilities: class weighting and temperature "
                 "scaling (out-of-fold, spatial cross-validation).",
                 ["Area", "Features", "Variant", "$T$", "Accuracy (\\%)", "NLL", "ECE"], rows[:-1], "lllrrrr",
                 note="NLL: negative log-likelihood; ECE: expected calibration error of the top-class probability.")


def noise_eval():
    rows = []
    for area, tag in (("london", "2024_s50k"), ("belfast", "2024")):
        n = read(f"{area}/model/results/noise_eval_{tag}.csv")
        if n is None:
            continue
        for _, r in n.iterrows():
            rows.append([AREA[area], tex(FS.get(r.featureset, r.featureset)), str(int(r.pairs)), num(r.mae_vs_own, 2),
                         num(r.mae_vs_mean_of_two, 2), num(r.noise_single_cert_est, 2)])
        rows.append("MID")
    if not rows:
        return missing("noise_eval", "noise-aware evaluation")
    return table("noise_eval", "SAP error against the certificate used in evaluation and against the mean of two "
                 "certificates of the same dwelling.",
                 ["Area", "Features", "Pairs", "MAE vs own", "MAE vs mean of two", "Noise of one certificate"],
                 rows[:-1], "llrrrr", note="Noise of one certificate: standard deviation implied by the test--retest "
                 "differences ($\\sigma_{\\Delta}/\\sqrt{2}$).")


def physics():
    rows = []
    for area in ("london", "belfast"):
        p = read(f"{area}/analysis/physics_check.csv")
        if p is None:
            continue
        for _, r in p[p.u_values == "as_described"].iterrows():
            rows.append([AREA[area], tex(r.group), f"{int(r.n):,}".replace(",", "{,}"), num(r.q_median_kwh_m2, 0),
                         num(r.spearman_q_vs_sap), num(r.spearman_q_vs_energy_m2)])
        rows.append("MID")
    if not rows:
        return missing("physics", "physics check")
    return table("physics", "Steady-state space-heating demand from envelope geometry and certificate U-values compared "
                 "with the certified SAP score and energy use per m$^2$ (Spearman's $\\rho$).",
                 ["Area", "Dwelling type", "Dwellings", "Median $Q$ (kWh/m$^2$)", "$\\rho$ with SAP", "$\\rho$ with energy/m$^2$"],
                 rows[:-1], "llrrrr")


def energy():
    g = read("london/analysis/ground_truth_energy.csv")
    if g is None:
        return missing("energy", "metered energy check")
    rows = [[tex(r.fuel.capitalize()), f"{int(r.lsoas):,}".replace(",", "{,}"), num(r.spearman_sap),
             num(r.partial_spearman_sap_given_floor_area), num(r.spearman_floor_area)] for _, r in g.iterrows()]
    return table("energy", "Mean certified SAP score of LSOAs against metered domestic consumption per meter "
                 "(London, DESNZ sub-national statistics).",
                 ["Fuel", "LSOAs", "$\\rho$ (SAP)", "Partial $\\rho$ given floor area", "$\\rho$ (floor area)"], rows, "lrrrr")


def software():
    import importlib, platform, subprocess
    rows = [["Python", platform.python_version()]]
    for m, label in (("numpy", "NumPy"), ("pandas", "pandas"), ("scipy", "SciPy"), ("sklearn", "scikit-learn"),
                     ("lightgbm", "LightGBM"), ("geopandas", "GeoPandas"), ("shapely", "Shapely"), ("rasterio", "rasterio"),
                     ("pyproj", "pyproj"), ("pyarrow", "PyArrow"), ("matplotlib", "Matplotlib"), ("duckdb", "DuckDB")):
        try:
            rows.append([label, importlib.import_module(m).__version__])
        except Exception:
            pass
    tag = subprocess.run(["git", "-C", str(CODE), "describe", "--tags", "--always"], capture_output=True, text=True).stdout.strip()
    rows.append(["Code version (GBEM)", tex(tag)])
    return table("software", "Software used for the analyses in this thesis (versions at the time of the build).",
                 ["Component", "Version"], rows, "lr")


def need():
    b, e = read("national/need_2024/need_band_summary.csv"), read("national/need_2024/need_explained.csv")
    if b is None or e is None:
        return missing("need", "NEED analysis")
    rows = []
    for area in ("England and Wales", "London"):
        u = b[b.area == area]
        for _, r in u.iterrows():
            rows.append([tex(area), tex(r.band), f"{int(r.homes):,}".replace(",", "{,}"), f"{r.gas_kwh_median:,.0f}".replace(",", "{,}"),
                         f"{r.gas_median_floor_band_3:,.0f}".replace(",", "{,}")])
        x = e[e.area == area].iloc[0]
        rows.append(["", r"\multicolumn{4}{l}{\emph{$R^2$ of log gas use: band " + num(x.r2_epc_band) + "; floor area " +
                     num(x.r2_floor_area_band) + "; type, age and floor area " + num(x.r2_type_age_floor) + "; all " +
                     num(x.r2_band_type_age_floor) + "}}"])
        rows.append("MID")
    return table("need", "Metered annual gas use by EPC band in the anonymised National Energy Efficiency Data-Framework "
                 "(2024 release): median of all homes and of homes in the middle floor-area band.",
                 ["Area", "Band", "Homes", "Median gas (kWh)", "Median gas, middle floor-area band (kWh)"], rows[:-1], "llrrr")


def applications():
    rows = []
    h = read("london/analysis/hp_readiness_summary.csv")
    if h is not None:
        a = h[h.group == "all"].iloc[0]
        rows += [["Heat-pump readiness", "Dwellings with HLP $<$ 2 W/m$^2$K", f"{num(100 * a.share_ready, 1)}\\%"],
                 ["", "Heat pumps among them", f"{num(100 * a.heat_pump_share_in_ready, 1)}\\%"],
                 ["", "Heat pumps among HLP $\\geq$ 3 W/m$^2$K", f"{num(100 * a.heat_pump_share_in_fabric_first, 1)}\\%"],
                 ["", "Median HLP of dwellings that switched to a heat pump", f"{num(a.switchers_hlp_median, 2)} W/m$^2$K"]]
    d = read("london/analysis/heat_density_check.csv")
    if d is not None:
        r = d[d.measure == "density per km2"].iloc[0]; q = d[d.measure == "demand per LSOA"].iloc[0]
        rows += [["Heat density", "$\\rho$ with metered gas density (LSOA)", num(r.spearman)],
                 ["", "Estimated total / metered gas", num(q.ratio_totals_est_to_gas)]]
    v = read("london/analysis/vulnerability_summary.csv")
    if v is not None:
        v = v.iloc[0]
        rows += [["Deprivation", "$\\rho$, mean SAP vs income deprivation (LSOA)", num(v.spearman_sap_vs_income_deprivation)],
                 ["", "LSOAs with low SAP and high deprivation", str(int(v.double_burden_units))]]
    if not rows:
        return missing("applications", "application analyses")
    return table("applications", "Summary of the application analyses for London.", ["Analysis", "Measure", "Value"],
                 rows, "llr", note="HLP: heat-loss parameter (heat-loss coefficient per m$^2$ of floor area).")


def targeting():
    t = read("london/analysis/targeting_rules.csv")
    if t is None:
        return missing("targeting", "targeting rules")
    rows = [[tex(r.outcome), tex(r.rule), num(r.precision), num(r.spearman)] for _, r in t.iterrows()]
    return table("targeting", "Precision of area-selection rules (top 20\\% of LSOAs selected by each rule) for official "
                 "fuel poverty and for high metered gas use (London).",
                 ["Outcome", "Selection rule", "Precision", "$\\rho$"], rows, "llrr", note="Random selection gives a "
                 "precision of 0.20.")


TABLES = {"baselines": baselines, "embeddings": embeddings, "validation_design": validation_design, "retest": retest, "scale": scale,
          "neighbours": neighbours, "targets": targets, "transfer": transfer, "adaptation": adaptation, "temporal": temporal,
          "typology": typology, "retrofit": retrofit, "need": need, "software": software, "aoa": aoa, "calibration": calibration,
          "noise_eval": noise_eval, "physics": physics, "energy": energy, "applications": applications,
          "targeting": targeting}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(PHD / "Manuscripts/02_Thesis/generated/tables"))
    out = pathlib.Path(ap.parse_args().out); out.mkdir(parents=True, exist_ok=True)
    for name, fn in TABLES.items():
        (out / f"{name}.tex").write_text(fn(), encoding="utf-8")
    print(f"{len(TABLES)} tables -> {out}" + (f"; pending: {', '.join(MISSING)}" if MISSING else ""))


if __name__ == "__main__":
    main()
