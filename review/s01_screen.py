"""Stage 1 - screening and abstract-level coding.

Pass 1: transparent keyword rules (first screener) -> decision + reason.
Pass 2: human decisions in inputs/screening_overrides.csv replace rule decisions.
Dual screening: a seeded random sample is written to inputs/ for the second reviewer;
Cohen's kappa is computed once their file is filled in.

Output: outputs/screening_decisions.csv, outputs/stats_screening.json
Feeds : PRISMA screening boxes, Table 7 (modalities), Fig. 10 (evidence map), Fig. 5 (map), Section 4.1-4.5.
"""
import re
import numpy as np, pandas as pd
from common import (EFF, GEO, PV, OUTDOOR, INDOOR, UAV_CLOSE, STOCK_WORDS, RATING, ML, MODALITY, TARGET, METHOD,
                    VALIDATION, COUNTRIES, CITY2C, CNORM, has, codes, dump, read_csv)

INCLUDED = "Included (core)"
DECISIONS = [INCLUDED, "Excluded (T/A)", "Review (umbrella)", "Excluded (record type)"]


def rule_decision(r, years):
    t, ta, tl = r["text"], r["ta"], r["tl"]
    dt = str(r["doc_type"])
    if dt not in ("Article", "Review", "Conference Paper"):
        return "Excluded (record type)", f"Record type not eligible ({dt})"
    if pd.notna(r["year"]) and not (years[0] <= int(r["year"]) <= years[1]):
        return "Excluded (record type)", "Outside publication years"
    if dt == "Review":
        return "Review (umbrella)", "Review article - context/umbrella evidence"
    if not has(EFF, ta):
        if has(OUTDOOR, ta) or "thermal comfort" in ta:
            return "Excluded (T/A)", "Outcome is thermal comfort, not energy efficiency"
        return "Excluded (T/A)", "Outcome not related to building energy efficiency"
    if has(PV, tl) and not has(EFF, tl):
        return "Excluded (T/A)", "Renewable/solar potential only"
    if has(INDOOR, ta) and not has(STOCK_WORDS, ta):
        return "Excluded (T/A)", "Indoor sensing/positioning or laboratory, no geospatial component"
    if not has(GEO, t):
        return "Excluded (T/A)", "No geospatial or remote-sensing data/method"
    if has(UAV_CLOSE, ta) and not has(STOCK_WORDS, ta):
        return "Excluded (T/A)", "UAV/close-range thermography of single buildings (covered by existing reviews)"
    return INCLUDED, ""


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
    for c in ["title", "abstract", "author_keywords", "index_keywords"]:
        df[c] = df[c].fillna("")
    df["text"] = (df["title"] + " . " + df["abstract"] + " . " + df["author_keywords"] + " . " + df["index_keywords"]).str.lower()
    df["ta"] = (df["title"] + " . " + df["abstract"]).str.lower()
    df["tl"] = df["title"].str.lower()
    res = df.apply(lambda r: rule_decision(r, cfg.SEARCH["years"]), axis=1, result_type="expand")
    df["rule_decision"], df["rule_reason"] = res[0], res[1]
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
    keep = ["rid", "db", "found_in", "doi", "authors", "title", "year", "source_title", "doc_type", "cited_by",
            "rule_decision", "rule_reason", "decision", "reason", "decided_by", "rating_ml", "study_country", "country_source",
            "modality", "target", "method", "validation", "accuracy_pct", "r2", "f1", "cvrmse_pct", "auc"]
    df[keep].to_csv(P["out"] / "screening_decisions.csv", index=False, encoding="utf-8-sig")

    C = df[core]
    pct = lambda n, d: round(100 * n / d, 1) if d else 0.0
    st = {"n_screened": int((df["decision"] != "Excluded (record type)").sum()),
          "n_removed_record_type": int((df["decision"] == "Excluded (record type)").sum()),
          "n_reviews": int((df["decision"] == "Review (umbrella)").sum()),
          "n_excluded_ta": int((df["decision"] == "Excluded (T/A)").sum()),
          "excluded_reasons": df.loc[df["decision"] == "Excluded (T/A)", "reason"].value_counts().to_dict(),
          "n_core": int(core.sum()), "n_core_conference": int((C["doc_type"] == "Conference Paper").sum()),
          "n_verified_by_reviewer": n_over, "n_rule_decisions_changed": changed, "kappa": kappa,
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
