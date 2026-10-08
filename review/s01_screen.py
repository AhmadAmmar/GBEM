"""Stage 1 - screening and abstract-level coding.

Pass 1: transparent keyword rules (first screener) -> decision, reason, inclusion route and a flag for
        decisions that rest on weak evidence. Every criterion has to be met in the title or abstract.
Pass 2: human decisions in inputs/screening_overrides.csv replace rule decisions.
Dual screening: a seeded random sample is written to inputs/ for the second reviewer;
Cohen's kappa is computed once their file is filled in.

Output: outputs/screening_decisions.csv, outputs/stats_screening.json
Feeds : PRISMA screening boxes, Table 7 (modalities), Fig. 10 (evidence map), Fig. 5 (map), Section 4.1-4.5.
"""
import re
import numpy as np, pandas as pd
from common import (BUILT, EFF, GEO, CONTEXT, PV, OUTDOOR, INDOOR, CLOSE, WIDE, MANY, REVIEW_TITLE, RATING, RATING_EST, ML,
                    MODALITY, TARGET, METHOD, VALIDATION, COUNTRIES, CITY2C, CNORM, has, codes, dump, read_csv)

INCLUDED = "Included (core)"
DECISIONS = [INCLUDED, "Excluded (T/A)", "Review (umbrella)", "Excluded (record type)"]
ROUTE_GEO, ROUTE_RATING = "geospatial data or method", "rating estimation"


def rule_decision(r, years, doc_types=("Article", "Review", "Conference Paper", "Data Paper")):
    """First-pass decision for one record: (decision, reason, route, to_verify).

    A record is included only if every eligibility criterion is met in the title or abstract:
    population (buildings), outcome (energy efficiency or a recognised proxy), exposure (a geospatial or
    remote-sensing data source or method, named in the title, abstract or author keywords) and scale (a wide-area
    source, or close-range sensing applied to many buildings).
    Studies that estimate an energy rating with a learning method are included without the exposure and
    scale criteria (route "rating estimation"), because they answer the focused question of the review.
    to_verify marks decisions that rest on weak evidence and are checked first by the reviewer.
    """
    t, ta, tl = r["text"], r["ta"], r["tl"]
    dt = str(r["doc_type"])
    if re.match(r"\s*(retracted|retraction|withdrawn)\b", str(r["title"]), re.I) or dt in ("Retracted", "Erratum"):
        return "Excluded (record type)", f"Retracted or erratum ({dt})" if dt in ("Retracted", "Erratum") else "Retracted article", "", False
    if dt == "Preprint" and r.get("arm") == "other methods":   # eligibility: preprints only via other methods (flagged)
        dt = "Article"
    if dt not in doc_types:
        return "Excluded (record type)", f"Record type not eligible ({dt})", "", False
    if pd.notna(r["year"]) and not (years[0] <= int(r["year"]) <= years[1]):
        return "Excluded (record type)", "Outside publication years", "", False
    if dt == "Review" or has(REVIEW_TITLE, tl):
        return "Review (umbrella)", "Review article - context/umbrella evidence", "", False
    if not has(BUILT, ta):
        return "Excluded (T/A)", "No building or building stock", "", False
    if not has(EFF, ta):
        if has(OUTDOOR, ta) or "thermal comfort" in ta:
            return "Excluded (T/A)", "Outcome is thermal comfort, not energy efficiency", "", False
        return "Excluded (T/A)", "Outcome not related to building energy efficiency", "", False
    if has(PV, tl) and not has(EFF, tl):
        return "Excluded (T/A)", "Renewable/solar potential only", "", False
    if (has(RATING, ta) and has(ML, ta)) or has(RATING_EST, ta):
        return INCLUDED, "", ROUTE_RATING, not has(BUILT, tl)
    tak = ta + " . " + str(r.get("author_keywords", "") or "").lower()    # the authors' own keywords count; index keywords do not
    if not has(GEO, tak):
        if has(INDOOR, ta):
            return "Excluded (T/A)", "Indoor sensing/positioning or laboratory, no geospatial component", "", False
        if has(GEO, t):
            return "Excluded (T/A)", "Geospatial term in index keywords only", "", True
        if has(CONTEXT, t):
            return "Excluded (T/A)", "Urban climate or urban form context without geospatial data or method", "", False
        return "Excluded (T/A)", "No geospatial or remote-sensing data/method", "", False
    if not has(WIDE, tak) and not has(MANY, ta):
        return "Excluded (T/A)", "Single building or component, not stock scale", "", False
    # buildings have to be the subject of the study, not a passing mention
    if not has(BUILT, tl) and len(re.findall(BUILT, ta)) < 2:
        return "Excluded (T/A)", "Buildings mentioned in passing, not the subject of the study", "", True
    return INCLUDED, "", ROUTE_GEO, has(CLOSE, ta) and not has(MANY, ta)


def abstract_metrics(s):
    out = {}
    m = re.findall(r"accuracy (?:of |rate of |reached |achieved |up to |was |is |=|:)?\s*(?:about |approximately |~)?(\d{2}(?:\.\d+)?)\s?%", s)
    m += re.findall(r"(\d{2}(?:\.\d+)?)\s?% (?:overall )?accuracy", s)
    if m: out["accuracy_pct"] = max(float(x) for x in m)
    m = re.findall(r"(?:r2|r\^2|r²|r-squared|coefficient of determination)[^0-9]{0,25}(0\.\d+)", s)
    if m: out["r2"] = max(float(x) for x in m)
    m = re.findall(r"f1[- ]?(?:score)?[^0-9]{0,20}(0\.\d+|\d{2}(?:\.\d+)?\s?%)", s)
    if m: out["f1"] = max(float(x.replace("%", "")) / (100 if "%" in x else 1) for x in m)
    m = re.findall(r"(?:cv\(?rmse\)?|cvrmse)[^0-9]{0,25}(\d{1,3}(?:\.\d+)?)\s?%", s)
    if m: out["cvrmse_pct"] = min(float(x) for x in m)
    m = re.findall(r"\bauc[^0-9]{0,25}(0\.\d+)", s)
    if m: out["auc"] = max(float(x) for x in m)
    return out


def study_country(r):
    ta = f"{r['title']} {r['abstract']}"
    for c in COUNTRIES:
        if re.search(r"\b" + re.escape(c) + r"\b", ta):
            if c == "Ireland" and "Northern Ireland" in ta:
                continue
            return CNORM.get(c, c), "title/abstract"
    low = ta.lower()
    for city, c in CITY2C.items():
        if city in low:
            return c, "title/abstract (city)"
    aff = str(r["affiliations"]).split(";")[0]
    c = aff.split(",")[-1].strip() if aff and aff != "nan" else ""
    return CNORM.get(c, c), "first-author affiliation"


def cohen_kappa(a, b):
    a, b = pd.Series(a).reset_index(drop=True), pd.Series(b).reset_index(drop=True)
    cats = sorted(set(a) | set(b))
    po = (a == b).mean()
    pe = sum((a == c).mean() * (b == c).mean() for c in cats)
    return float((po - pe) / (1 - pe)) if pe < 1 else 1.0


def run(cfg, P):
    df = read_csv(P["out"] / "records.csv")
    other_path = P["out"] / "prior_records.csv"   # records identified via other methods (previous work of the authors)
    if other_path.exists():
        df = pd.concat([df, read_csv(other_path)], ignore_index=True)
    df["arm"] = df.get("arm", pd.Series("database", index=df.index)).fillna("database")
    for c in ["title", "abstract", "author_keywords", "index_keywords"]:
        df[c] = df[c].fillna("")
    df["text"] = (df["title"] + " . " + df["abstract"] + " . " + df["author_keywords"] + " . " + df["index_keywords"]).str.lower()
    df["ta"] = (df["title"] + " . " + df["abstract"]).str.lower()
    df["tl"] = df["title"].str.lower()
    res = df.apply(lambda r: rule_decision(r, cfg.SEARCH["years"], tuple(cfg.SEARCH["doc_types"])), axis=1, result_type="expand")
    df["rule_decision"], df["rule_reason"], df["route"], df["to_verify"] = res[0], res[1], res[2], res[3].astype(bool)
    # decisions made without an abstract are marked, so that they are verified first
    df["title_only"] = df["abstract"].str.len().lt(100) & df["rule_decision"].isin([INCLUDED, "Excluded (T/A)"])
    df["to_verify"] = df["to_verify"] | df["title_only"]
    df["decision"], df["reason"], df["decided_by"] = df["rule_decision"], df["rule_reason"], "rules"

    # ---- human overrides (first reviewer verification)
    ov_path = P["inputs"] / cfg.HUMAN["screening_overrides"]
    if not ov_path.exists():
        pd.DataFrame(columns=["rid", "decision", "reason", "reviewer", "date"]).to_csv(ov_path, index=False, encoding="utf-8-sig")
    ov = read_csv(ov_path)
    n_over = 0
    if len(ov):
        ov = ov.dropna(subset=["rid", "decision"]).drop_duplicates("rid", keep="last").set_index("rid")
        bad = set(ov["decision"]) - set(DECISIONS)
        if bad:
            raise ValueError(f"Unknown decisions in {ov_path.name}: {bad}. Allowed: {DECISIONS}")
        m = df["rid"].isin(ov.index)
        df.loc[m, "decision"] = df.loc[m, "rid"].map(ov["decision"])
        df.loc[m, "reason"] = df.loc[m, "rid"].map(ov["reason"]).fillna(df.loc[m, "reason"])
        df.loc[m, "decided_by"] = "reviewer"
        n_over = int(m.sum()); changed = int((m & (df["decision"] != df["rule_decision"])).sum())
    else:
        changed = 0

    # ---- dual screening sample + kappa
    elig = df[df["rule_decision"].isin(["Included (core)", "Excluded (T/A)"])]
    samp_path = P["inputs"] / cfg.HUMAN["second_screener"]
    if not samp_path.exists():
        s = elig.sample(frac=cfg.DUAL_SAMPLE_FRACTION, random_state=cfg.RANDOM_SEED)
        s[["rid", "title", "abstract"]].assign(decision_reviewer2="", reason_reviewer2="").to_csv(samp_path, index=False, encoding="utf-8-sig")
    s2 = read_csv(samp_path)
    n_dual_sample = int(len(s2))
    s2 = s2[s2["decision_reviewer2"].fillna("").astype(str).str.strip().ne("")]
    kappa = None
    if len(s2):
        mm = s2.merge(df[["rid", "decision"]], on="rid")
        simp = lambda x: "include" if str(x).lower().startswith("incl") else "exclude"
        kappa = {"n": int(len(mm)), "kappa": round(cohen_kappa(mm["decision"].map(simp), mm["decision_reviewer2"].map(simp)), 3),
                 "agreement_pct": round(100 * (mm["decision"].map(simp) == mm["decision_reviewer2"].map(simp)).mean(), 1)}

    # ---- coding
    core = df["decision"].eq(INCLUDED)
    df["modality"] = df["text"].map(lambda s: codes(s, MODALITY))
    df["target"] = df["ta"].map(lambda s: codes(s, TARGET))
    df["method"] = df["ta"].map(lambda s: codes(s, METHOD))
    df["validation"] = df["ta"].map(lambda s: codes(s, VALIDATION))
    df["rating_ml"] = core & df["ta"].map(lambda s: has(RATING, s) and has(ML, s))
    met = df["ta"].map(abstract_metrics)
    for k in ["accuracy_pct", "r2", "f1", "cvrmse_pct", "auc"]:
        df[k] = met.map(lambda d: d.get(k))
    geo = df.apply(study_country, axis=1, result_type="expand")
    df["study_country"], df["country_source"] = geo[0], geo[1]
    for c in ("searches", "prior_sources"):
        df[c] = df.get(c, pd.Series("", index=df.index)).fillna("")
    keep = ["rid", "arm", "db", "found_in", "searches", "prior_sources", "doi", "authors", "title", "year", "source_title", "doc_type",
            "cited_by", "rule_decision", "rule_reason", "decision", "reason", "decided_by", "route", "title_only", "to_verify", "rating_ml", "study_country", "country_source",
            "modality", "target", "method", "validation", "accuracy_pct", "r2", "f1", "cvrmse_pct", "auc"]
    df[keep].to_csv(P["out"] / "screening_decisions.csv", index=False, encoding="utf-8-sig")
    # the authors' previous literature: decision for every prior work
    ps_path = P["out"] / "prior_literature_status.csv"
    if ps_path.exists():
        ps = read_csv(ps_path).drop(columns=["decision", "reason"], errors="ignore")
        ps.merge(df[["rid", "decision", "reason"]], on="rid", how="left").to_csv(ps_path, index=False, encoding="utf-8-sig")

    C = df[core]
    D, O = df[df["arm"] == "database"], df[df["arm"] == "other methods"]
    pct = lambda n, d: round(100 * n / d, 1) if d else 0.0
    st = {"n_screened": int((D["decision"] != "Excluded (record type)").sum()),
          "n_removed_record_type": int((D["decision"] == "Excluded (record type)").sum()),
          "n_reviews": int((D["decision"] == "Review (umbrella)").sum()),
          "n_excluded_ta": int((D["decision"] == "Excluded (T/A)").sum()),
          "excluded_reasons": D.loc[D["decision"] == "Excluded (T/A)", "reason"].value_counts().to_dict(),
          "n_core_db": int((D["decision"] == INCLUDED).sum()),
          "n_other_identified": int(len(O)), "n_other_record_type": int((O["decision"] == "Excluded (record type)").sum()),
          "n_other_screened": int((O["decision"] != "Excluded (record type)").sum()),
          "n_other_reviews": int((O["decision"] == "Review (umbrella)").sum()),
          "n_other_excluded": int((O["decision"] == "Excluded (T/A)").sum()),
          "n_core_other": int((O["decision"] == INCLUDED).sum()),
          "n_other_scoping": int(O["prior_sources"].str.startswith("earlier scoping").sum()),
          "n_core_other_scoping": int(((O["decision"] == INCLUDED) & O["prior_sources"].str.startswith("earlier scoping")).sum()),
          "n_core_route_rating": int((C["route"] == ROUTE_RATING).sum()), "n_core_route_geo": int((C["route"] == ROUTE_GEO).sum()),
          "n_to_verify": int(df["to_verify"].sum()), "n_to_verify_excluded": int((df["to_verify"] & df["decision"].eq("Excluded (T/A)")).sum()),
          "n_prior_core": int((C["prior_sources"] != "").sum()), "n_title_only": int(df["title_only"].sum()),
          "n_title_only_other": int(O["title_only"].sum()),
          "n_reviews_total": int((df["decision"] == "Review (umbrella)").sum()),
          "n_core": int(core.sum()), "n_core_conference": int((C["doc_type"] == "Conference Paper").sum()),
          "n_verified_by_reviewer": n_over, "n_rule_decisions_changed": changed, "kappa": kappa, "n_dual_sample": n_dual_sample,
          "n_core_title_abstract_country": int(C["country_source"].str.startswith("title").sum()),
          "core_n_countries": int(C["study_country"].replace("", np.nan).nunique()),
          "core_countries": C["study_country"].replace("", np.nan).dropna().value_counts().to_dict(),
          "core_no_validation_terms": int(C["validation"].eq("").sum()),
          "core_by_year": {int(k): int(v) for k, v in C["year"].value_counts().sort_index().items()},
          "core_ml_by_year": {int(k): int(v) for k, v in C.loc[C["method"].str.contains("Machine"), "year"].value_counts().sort_index().items()},
          "n_rating_ml": int(df["rating_ml"].sum())}
    for name, dic in [("modality", MODALITY), ("target", TARGET), ("method", METHOD), ("validation", VALIDATION)]:
        st["core_" + name] = {k: {"n": int(C[name].str.contains(re.escape(k)).sum()),
                                  "pct": pct(C[name].str.contains(re.escape(k)).sum(), len(C))} for k in dic}
    dump(st, P["out"] / "stats_screening.json")
    return st
