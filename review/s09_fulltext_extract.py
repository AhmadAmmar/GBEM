"""Stage 9 - structured extraction from the full texts.

For every work of the review with a PDF in the literature library (focused studies, focused-subset candidates, core
studies and review articles), the full text is read page by page and the following are extracted with documented
rules (dictionaries and patterns, no generative model):

    study area     countries and cities named in the body text (reference list excluded)
    data           named sensors, image sources, registers and open datasets
    sample size    numbers of buildings, dwellings, certificates or images
    target         rating scale, number of classes, binary splits (for example A-D vs E-G)
    methods        model families and named architectures; interpretability methods
    validation     design (random split, k-fold, spatially blocked, held-out city or area, temporal, transfer) and split ratios
    metrics        metric names with their values (accuracy, F1, precision, recall, kappa, AUC, R2, MAE, RMSE, MAPE)
    openness       code and data links (GitHub, Zenodo, figshare, OSF) and data-availability statements
    uncertainty    calibration, confidence or prediction intervals

Every extracted value keeps the page and sentence it came from. The values are suggestions for the reviewer: the
extraction sheet (inputs/focused_extraction.csv) is never changed here. For the studies the reviewer has already
extracted, the suggestions are compared with the reviewer's values, so the reliability of each rule is known.

Output: outputs/fulltext_extraction_auto.csv (one row per work), outputs/fulltext_evidence.csv (one row per finding),
        outputs/focused_prefill.xlsx (reviewer's values next to the suggestions, with evidence),
        outputs/stats_fulltext_extract.json (coverage and agreement with the reviewer)
"""
import re, collections
import pandas as pd
from common import COUNTRIES, CITY2C, CNORM, norm_doi, norm_title, dump, read_csv
from s04_fulltext import build_index, pdf_text

DATASETS = {
    "Google Street View": r"google street ?view|\bgsv\b", "Street-level imagery (other)": r"street[- ]level imag|streetscape|street[- ]view imag",
    "Mapillary": r"mapillary", "Sentinel-2": r"sentinel-?2", "Sentinel-1": r"sentinel-?1", "Landsat": r"landsat",
    "MODIS": r"\bmodis\b", "ECOSTRESS": r"ecostress", "PlanetScope": r"planetscope|planet labs", "WorldView": r"worldview",
    "Aerial imagery": r"aerial (imag|photo)|orthophoto|ortho-?image|ortho-?mosaic", "LiDAR / point clouds": r"lidar|point cloud|laser scan",
    "Environment Agency LiDAR": r"environment agency", "OS MasterMap / Ordnance Survey": r"mastermap|ordnance survey",
    "OpenStreetMap": r"openstreetmap|\bosm\b", "Building footprints": r"building footprint", "UPRN": r"\buprns?\b",
    "EPC register (England and Wales)": r"(domestic )?epc (open data|register|database)|energy performance certificate (register|database)",
    "BER register (Ireland)": r"\bseai\b|\bber (register|database)", "Census": r"\bcensus\b", "Verisk / UKBuildings": r"verisk|ukbuildings",
    "Thermal infrared imagery": r"thermal (infrared|imag|camera)|thermograph|\btir\b", "Land surface temperature": r"land surface temperature|\blst\b",
    "Night-time lights": r"night-?time light|viirs|dmsp", "Google Earth": r"google earth", "PointER": r"pointer", "NEBULA": r"\bnebula\b",
    "TABULA / EPISCOPE": r"tabula|episcope", "3D city models / CityGML": r"citygml|3d city model|\blod ?[1-4]\b",
}
METHODS = {
    "Random forest": r"random forest", "XGBoost": r"xgboost", "LightGBM": r"lightgbm", "CatBoost": r"catboost",
    "Gradient boosting": r"gradient boost", "Support vector machine": r"support vector|\bsvm\b", "k-nearest neighbours": r"k-?nearest|\bk-?nn\b",
    "Logistic regression": r"logistic regression", "Linear regression": r"linear regression|ordinary least squares|\bols\b",
    "Neural network (MLP)": r"multi-?layer perceptron|\bmlp\b|artificial neural network|\bann\b",
    "CNN": r"convolutional neural|\bcnns?\b", "ResNet": r"resnet", "VGG": r"\bvgg", "EfficientNet": r"efficientnet", "DenseNet": r"densenet",
    "Inception": r"inception", "Vision transformer": r"vision transformer|\bvit\b|swin", "U-Net": r"u-?net", "YOLO": r"\byolo",
    "Vision-language model / LLM": r"vision[- ]language|\bclip\b|\bgpt|large language model|\bllm", "Graph neural network": r"graph neural|\bgnn",
    "Transfer learning / fine-tuning": r"transfer learning|fine-?tun", "Kriging / spatial interpolation": r"kriging|spatial interpolation",
    "Clustering": r"k-?means|cluster analysis|hierarchical clustering",
}
INTERPRET = {"SHAP": r"\bshap\b|shapley", "Grad-CAM": r"grad-?cam|class activation map", "Integrated gradients": r"integrated gradient",
             "LIME": r"\blime\b", "Feature importance": r"feature importance|permutation importance"}
VALIDATION = [   # strongest design first
    ("Spatially blocked CV", r"spatial(ly)?[- ](block|cross[- ]validation|k-?fold|split)|leave[- ]one[- ](postcode|district|area|region|city|borough|zone|neighbou?rhood)[- ]out|block(ed)? cross[- ]validation"),
    ("Held-out city", r"(held[- ]out|unseen|independent|test|new|different) cit(y|ies)|cross[- ]city|test(ing)? (set|data|city|region)[^.]{0,60}\b(the )?(city|town|region|county) of\b|(city|town) of \w+ (as|for) (the )?test|transfer(red)? to (a |the )?(new|different|another|other) (city|cities|region)"),
    ("Held-out area", r"(held[- ]out|unseen|separate[d]?|independent) (area|region|district|neighbou?rhood|borough)|geographically (separate|distinct)"),
    ("Temporal hold-out", r"temporal (hold|split|validation|test)|out[- ]of[- ]time|later (year|period)s?"),
    ("Transfer with local fine-tuning", r"fine-?tun\w* (on|with) .{0,40}(local|target|new)|transfer learning (on|with|using) .{0,40}(local|target) (sample|data|label)|adapt\w* (the )?models? to (new|other|different|target) (cit|region|area)"),
    ("Random split", r"random(ly)? (split|divided|partition|sampl\w* .{0,20}(train|test))|\d+[- ]fold cross[- ]validation|k-?fold|\b[5-9]0\s?[:/]\s?[1-5]0\b|\b[5-9]0\s?%.{0,30}(train|training).{0,40}[1-5]0\s?%|train(ing)?[,/ ]+(validation[,/ ]+)?test(ing)? (split|set)|split into (a )?(train|training)|proportions? of \d+\s?%"),
]
METRIC = r"(macro[- ]?(?:averaged )?f1(?:[- ]score)?|weighted[- ]?f1|micro[- ]?f1|f1[- ]?score|\bf1\b|balanced accuracy|overall accuracy|accuracy|precision|recall|cohen'?s kappa|\bkappa\b|\bauc\b|\br\^?2\b|r²|r-squared|coefficient of determination|\bmae\b|\brmse\b|\bmape\b)"
VALUE = r"(\d{1,3}(?:\.\d+)?\s?%|0\.\d{2,4}|1\.0{1,3})"
OTHER_WORK = r"\[\d+(?:[,–\-]\s?\d+)*\]|\bet al\.|\(\D{2,40}\s(?:19|20)\d{2}[a-z]?\)"
UNCERT = r"uncertaint|confidence interval|prediction interval|calibrat|conformal|bootstrap"
OPEN_LINK = r"(https?://)?(www\.)?(github\.com|gitlab\.com|zenodo\.org|figshare\.com|osf\.io|huggingface\.co|data\.mendeley\.com)/[^\s,;)\]]+"
OPEN_STMT = {"available on request": r"(available|provided) (from the (corresponding )?authors? )?(up)?on (reasonable )?request",
             "publicly available": r"(publicly|openly|freely) available|open[- ]source", "data availability statement": r"data availability"}
SAMPLE = r"(\d{1,3}(?:[,\s]\d{3})+|\d{3,})(?:\s?(?:k|thousand|million))?\s(?:\w+\s){0,2}(buildings|dwellings|properties|houses|homes|households|certificates|epcs|images|samples|addresses)"
CLASSES = r"(seven|7)[- ](classes|bands|categories|levels)|\ba\s?[-–]\s?g\b|binary (classification|label|target|task)|\b(a\s?[-–]\s?[b-f])\s?(vs\.?|versus|and)\s?([b-g]\s?[-–]\s?g)\b|(three|four|five|3|4|5)[- ](classes|bands|categories)|sap (score|rating)|energy efficiency rating"


def pages_of(text):
    """Pages of the body text, without the reference list."""
    pages = text.split("\f")
    out = []
    for i, p in enumerate(pages, 1):
        m = re.search(r"\n\s*(References|Bibliography|REFERENCES)\s*\n", p)
        if m and i > 2:
            out.append((i, p[:m.start()])); break
        out.append((i, p))
    return out


def sentences(page):
    flat = re.sub(r"-\n(\w)", r"\1", page)          # rejoin hyphenated words
    flat = re.sub(r"\s+", " ", flat)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z(])", flat) if 25 < len(s) < 700]


def extract(pdf):
    text = pdf_text(pdf)
    if not text.strip():
        return None, []
    ev = []
    def hit(field, value, page, sent):
        ev.append({"field": field, "value": value, "page": page, "sentence": sent[:500]})
    for pno, page in pages_of(text):
        for s in sentences(page):
            low = s.lower()
            other = bool(re.search(OTHER_WORK, s))     # the sentence reports another study
            for name, p in DATASETS.items():
                if re.search(p, low): hit("data", name, pno, s)
            for name, p in METHODS.items():
                if re.search(p, low): hit("method", name, pno, s)
            for name, p in INTERPRET.items():
                if re.search(p, low): hit("interpretability", name, pno, s)
            if not other:
                for name, p in VALIDATION:
                    if re.search(p, low): hit("validation", name, pno, s)
                for m in re.finditer(METRIC + r"[^.;%]{0,60}?" + VALUE, low):
                    hit("metric", f"{canon_metric(m.group(1))}={m.group(2).replace(' ', '')}", pno, s)
                for m in re.finditer(r"\b(mae|rmse|mape|cv\(?rmse\)?)\s?(?:=|:|of)\s?(\d{1,3}(?:\.\d+)?)\s?(%?)", low):   # error metrics as plain numbers
                    hit("metric", f"{canon_metric(m.group(1))}={m.group(2)}{m.group(3)}", pno, s)
                for m in re.finditer(VALUE + r"\s?(?:\(\w+\)\s?)?(?:in |of |for )?(?:the )?(?:[a-z-]+\s){0,2}" + METRIC, low):      # value written first
                    hit("metric", f"{canon_metric(m.group(2))}={m.group(1).replace(' ', '')}", pno, s)
                for m in re.finditer(SAMPLE, low):
                    hit("sample", m.group(0), pno, s)
            m = re.search(CLASSES, low)
            if m: hit("target", m.group(0), pno, s)
            if re.search(UNCERT, low): hit("uncertainty", re.search(UNCERT, low).group(0), pno, s)
            for m in re.finditer(OPEN_LINK, s, flags=re.I):
                hit("open", m.group(0).rstrip("."), pno, s)
            for name, p in OPEN_STMT.items():
                if re.search(p, low): hit("open", name, pno, s)
            for c in COUNTRIES:
                if re.search(r"\b" + re.escape(c) + r"\b", s): hit("country", CNORM.get(c, c), pno, s)
            for city, c in CITY2C.items():
                if city in low: hit("place", city.title(), pno, s)
    return len(pages_of(text)), ev


def canon_metric(m):
    m = m.lower()
    if "f1" in m:
        return "Macro-F1" if "macro" in m else ("Weighted F1" if "weighted" in m else ("Micro-F1" if "micro" in m else "F1"))
    return {"balanced accuracy": "Balanced accuracy", "overall accuracy": "Accuracy", "accuracy": "Accuracy", "precision": "Precision",
            "recall": "Recall", "auc": "AUC", "mae": "MAE", "rmse": "RMSE", "mape": "MAPE"}.get(m, "Kappa" if "kappa" in m else ("R2" if m.startswith(("r", "coef")) else m))


def summarise(ev):
    E = pd.DataFrame(ev)
    if not len(E):
        return {}
    cnt = lambda f: E[E["field"] == f]["value"].value_counts()
    top = lambda f, k=6: "; ".join(f"{v} ({n})" for v, n in cnt(f).head(k).items())
    vc = E.loc[E["field"] == "validation", "value"].value_counts()
    order = [name for name, _ in VALIDATION]
    # the strongest design that the paper states about itself (sentences citing other work are already left out)
    val = next((n for n in order if vc.get(n, 0) >= 1), "Not found")
    mets = E[E["field"] == "metric"]["value"]
    return {"countries": top("country", 4), "places": top("place", 5), "data": top("data", 10), "methods": top("method", 8),
            "interpretability": top("interpretability", 4), "validation_suggested": val, "validation_found": top("validation", 6),
            "metrics": "; ".join(mets.value_counts().head(12).index), "sample_mentions": top("sample", 4), "target_mentions": top("target", 4),
            "uncertainty": top("uncertainty", 3), "open": top("open", 5)}


def value_matches(human_metric, human_value, metrics):
    """Is the reviewer's headline value among the extracted values of the same metric family?"""
    try:
        hv = float(human_value)
    except (TypeError, ValueError):
        return None
    if hv != hv:            # no value recorded by the reviewer
        return None
    fam = canon_metric(str(human_metric).split("(")[0].strip())
    for item in str(metrics).split("; "):
        if "=" not in item:
            continue
        name, v = item.split("=", 1)
        x = float(v.rstrip("%")) / (100 if v.endswith("%") else 1)
        y = hv if hv <= 1.5 else hv / 100
        if (name == fam or fam in name or name in fam) and abs(x - y) <= 0.006:
            return True
    return False


def run(cfg, P):
    idx = build_index(cfg, P)
    by_doi = idx[idx["doi_n"].fillna("").ne("")].drop_duplicates("doi_n").set_index("doi_n")["pdf"]
    dec = read_csv(P["out"] / "screening_decisions.csv")
    sheet = read_csv(P["inputs"] / cfg.HUMAN["focused_extraction"])
    works = []
    for r in sheet.itertuples():
        works.append((norm_doi(r.doi), str(r.title) if isinstance(r.title, str) else "", "focused (included)" if str(r.include_focused).upper() == "Y" else "focused candidate", r.key if isinstance(r.key, str) else ""))
    for r in dec[dec["decision"].isin(["Included (core)", "Review (umbrella)"])].itertuples():
        works.append((norm_doi(r.doi), str(r.title), "core study" if r.decision == "Included (core)" else "review article", ""))
    seen, rows, evid = set(), [], []
    for d, title, status, key in works:
        k = d or norm_title(title)
        if not k or k in seen:
            continue
        seen.add(k)
        pdf = by_doi.get(d) if d else None
        if pdf is None:
            tn = norm_title(title)[:70]
            if len(tn) > 25:
                hit = idx[idx["head_n"].fillna("").str.contains(re.escape(tn), regex=True)]
                pdf = hit["pdf"].iloc[0] if len(hit) else None
        if pdf is None:
            continue
        n_pages, ev = extract(pdf)
        if not ev:
            continue
        rows.append({"doi": d, "title": title, "status": status, "key": key, "pdf": pdf, "pages": n_pages, **summarise(ev)})
        evid += [{"doi": d, "key": key, **e} for e in ev]
    A = pd.DataFrame(rows)
    A.to_csv(P["out"] / "fulltext_extraction_auto.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(evid).to_csv(P["out"] / "fulltext_evidence.csv", index=False, encoding="utf-8-sig")

    # reviewer's values next to the suggestions, for the focused studies and candidates
    S = sheet.copy(); S["d"] = S["doi"].map(norm_doi)
    F = S.merge(A[A["doi"] != ""].drop(columns=["title", "key"]), left_on="d", right_on="doi", how="left", suffixes=("", "_auto"))
    F.loc[F["d"] == "", [c for c in A.columns if c in F.columns and c not in ("doi", "title", "key")]] = None
    F["validation_agrees"] = [(None if not isinstance(a, str) or not str(h).strip() or h in ("Not applicable", "Not applicable (zero-shot)") else
                               (a == h or (a in ("Held-out city", "Held-out area") and h in ("Held-out city", "Held-out area"))
                                or (a == "Not found" and h in ("Not reported", "Internal (not specified)"))))
                              for a, h in zip(F["validation_suggested"], F["validation"])]
    F["metric_value_found"] = [value_matches(m, v, x) if isinstance(x, str) else None for m, v, x in zip(F["metric"], F["value"], F["metrics"])]
    cols = ["include_focused", "key", "study", "year", "title", "pdf", "country", "countries", "area", "places", "data", "data_auto", "target", "target_mentions",
            "model_family", "methods", "validation", "validation_suggested", "validation_agrees", "validation_found", "metric", "value", "metrics",
            "metric_value_found", "code_data_open", "open", "uncertainty", "interpretability", "sample_mentions"]
    F = F.rename(columns={"data_auto": "data_auto"}) if "data_auto" in F else F.rename(columns={})
    if "data_auto" not in F and "data" in A:
        F["data_auto"] = F["d"].map(dict(zip(A["doi"], A["data"])))
    F = F[[c for c in cols if c in F.columns]]
    with pd.ExcelWriter(P["out"] / "focused_prefill.xlsx", engine="openpyxl") as xw:
        for name, part in (("Included", F[F["include_focused"].astype(str).str.upper() == "Y"]), ("Candidates", F[F["include_focused"].astype(str) == "?"])):
            part.to_excel(xw, sheet_name=name, index=False)
        for ws in xw.book.worksheets:
            ws.freeze_panes = "F2"
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(max(10, max(len(str(c.value or "")) for c in col[:30]) * 0.7), 45)
    Y = F[F["include_focused"].astype(str).str.upper() == "Y"]
    va, mv = Y["validation_agrees"].dropna(), Y["metric_value_found"].dropna()
    st = {"n_works_read": int(len(A)), "by_status": A["status"].value_counts().to_dict() if len(A) else {},
          "n_findings": int(len(evid)), "focused_with_fulltext": int(Y["pdf"].notna().sum()),
          "validation_agreement": {"n": int(len(va)), "agree": int(va.sum())}, "metric_value_found": {"n": int(len(mv)), "found": int(mv.sum())},
          "candidates_with_fulltext": int(F[F["include_focused"].astype(str) == "?"]["pdf"].notna().sum())}
    dump(st, P["out"] / "stats_fulltext_extract.json")
    return st
