"""Stage 8 - triage of the candidates for the focused subset.

A core study is a candidate when its abstract names an energy rating, label or class (stage 3). This stage checks,
with documented keyword rules, what the focused subset requires:

    target   the rating is what the study estimates (not only an input, a price driver or a policy topic)
    level    the estimate is made for individual buildings or dwellings
    method   a model or estimation method is named
    metric   a performance metric is reported

Evidence is taken from the title and abstract and, where a PDF of the work is in the literature library, from the
full text as well. Each candidate is sorted into Likely, Unclear or Unlikely, with the reasons and the sentences
that triggered them. The rules only order the work of the reviewer: include_focused in the extraction sheet is
never changed here. The rules are tested on the studies the reviewer has already decided (include_focused Y or N).

Output: outputs/focused_triage.csv, outputs/fulltext_to_download.csv, outputs/stats_triage.json
Feeds : Section 2 (selection of the focused subset); work list for full-text screening.
"""
import re
import pandas as pd
from common import RATING, RATING_EST, ML, norm_doi, norm_title, dump, read_csv, has
from s04_fulltext import build_index, pdf_text, conclusions

RAT = RATING + r"|energy (performance|efficiency) (rating|class|label|band|score)s?|\bsap\b|energy score"
TARGET = (RATING_EST + r"|(predict|estimat|classif|infer|forecast|determin|identif|map)\w* (\w+ ){0,8}(" + RAT + r")"
          r"|(" + RAT + r")\w* (\w+ ){0,3}(prediction|estimation|classification|inference|mapping)"
          r"|(energy[- ]efficient (or|and|versus|vs\.?) (energy[- ])?inefficient)|hard-to-decarboni[sz]e"
          # the efficiency or performance of buildings is estimated (every candidate also names a rating, label or class)
          r"|(predict|estimat|classif|infer|forecast|learn)\w* (\w+ ){0,5}(building'?s?'? )?energy[- ](efficiency|performance)(?! contract)"
          r"|energy[- ](efficiency|performance) (\w+ ){0,2}(prediction|estimation|classification)")
# a dataset built for such estimation is eligible as well
DATASET = r"\b(data ?set|benchmark)\b"
LEVEL = (r"individual (building|dwelling|propert|home|house)|building[- ]level|per[- ]building|each (building|dwelling|property|home|house)|"
         r"property[- ]level|dwelling[- ]level|building[- ]by[- ]building|address[- ]level|\buprns?\b|at the building scale|every (building|dwelling|property)")
METHOD = ML + r"|regression|classifier|classification model|predictive model|statistical model|clustering|k-means|bayesian|typolog|data mining|unsupervised|nearest neighbo"
METRIC = r"accuracy|f1[- ]?score|\bf1\b|precision|recall|\br2\b|r²|r-squared|\bmae\b|\brmse\b|\bauc\b|kappa|confusion matrix|mean absolute error"
NEGATIVE = {
    "property prices or rents": r"house prices?|housing prices?|property (prices?|values?)|sale prices?|rental? (prices?|premium)|price premium|hedonic|capitali[sz]ation|willingness to pay|mortgage",
    "energy performance contracting": r"energy performance contract|\bepc contract|engineering,? procurement",
    "appliance or product labels": r"appliances?\b|refrigerator|vehicle|tyres?\b|lamps?\b",
    "green-building certification (LEED, BREEAM)": r"\bleed\b|breeam|green building (rating|certif)|green star|\bdgnb\b",
    "certificate quality or policy, not estimation": r"quality of (the )?(epcs?|certificat)|reliab\w+ of (the )?(epcs?|certificat)|performance gap|policy (analysis|evaluation|instruments?)|uptake|awareness",
}
AGGREGATE = r"(municipal|district|regional|national|country|neighbou?rhood|postcode|census|city)[- ](level|scale)|aggregat"
HARD = ("energy performance contracting", "appliance or product labels")


def first_sentence(pattern, text):
    m = re.search(r"[^.]{0,220}(?:" + pattern + r")[^.]{0,220}\.?", text, re.I)
    return re.sub(r"\s+", " ", m.group(0)).strip() if m else ""


def assess(title, abstract, fulltext=""):
    ta = f"{title} . {abstract}".lower()
    ft = re.sub(r"\s+", " ", fulltext).lower()
    purpose = ta + " . " + ft[:6000] + " . " + conclusions(fulltext).lower() if ft else ta    # where a study states what it does
    data = has(DATASET, title.lower()) and has(RAT + r"|energy (feature|efficien|performance)", ta)
    s = {"target": has(TARGET, purpose) or data, "level": has(LEVEL, ta) or has(LEVEL, ft), "method": has(METHOD, ta) or has(METHOD, ft[:20000]) or data,
         "metric": has(METRIC, ta) or has(METRIC, ft)}
    neg = [k for k, p in NEGATIVE.items() if has(p, ta)]
    aggregate = has(AGGREGATE, ta) and not s["level"]
    score = 2 * s["target"] + s["level"] + s["method"] + s["metric"] - 2 * sum(k in HARD for k in neg) - (len(neg) > 0) - aggregate
    if s["target"] and s["method"] and (s["level"] or s["metric"]) and not any(k in HARD for k in neg):
        cls = "Likely"
    elif any(k in HARD for k in neg) or (not s["target"] and (neg or not s["method"])):
        cls = "Unlikely"
    else:
        cls = "Unclear"
    why = [k for k, v in (("rating is the estimated target", s["target"]), ("individual buildings", s["level"]), ("method named", s["method"]),
                          ("metric reported", s["metric"])) if v]
    miss = [k for k, v in (("no statement that the rating is estimated", s["target"]), ("building level not stated", s["level"]),
                           ("no method named", s["method"])) if not v]
    return {"triage": cls, "score": int(score), **{"sig_" + k: bool(v) for k, v in s.items()}, "sig_aggregate_only": bool(aggregate),
            "negative_topics": "; ".join(neg), "supports": "; ".join(why), "against": "; ".join(miss + neg + (["aggregate level only"] if aggregate else [])),
            "evidence_target": first_sentence(TARGET, purpose)[:450], "evidence_level": first_sentence(LEVEL, ta + " . " + ft)[:450]}


def run(cfg, P):
    sheet = read_csv(P["inputs"] / cfg.HUMAN["focused_extraction"])
    recs = pd.concat([read_csv(P["out"] / f) for f in ("records.csv", "prior_records.csv") if (P["out"] / f).exists()], ignore_index=True)
    recs["d"], recs["tn"] = recs["doi"].map(norm_doi), recs["title"].map(norm_title)
    by_d = recs[recs["d"] != ""].drop_duplicates("d").set_index("d")
    by_t = recs.drop_duplicates("tn").set_index("tn")
    idx = build_index(cfg, P)
    pdf_by_doi = idx[idx["doi_n"].fillna("").ne("")].drop_duplicates("doi_n").set_index("doi_n")["pdf"]
    log_path = cfg.LIT / "Review_fulltexts" / "download_log.csv"
    oa = read_csv(log_path).drop_duplicates("doi", keep="last").set_index("doi") if log_path.exists() else pd.DataFrame()
    rows = []
    for _, r in sheet.iterrows():
        d = norm_doi(r.get("doi")); tn = norm_title(r.get("title") or "")
        rec = by_d.loc[d] if d and d in by_d.index else (by_t.loc[tn] if tn and tn in by_t.index else None)
        title = str(r.get("title") if isinstance(r.get("title"), str) else (rec["title"] if rec is not None else ""))
        abstract = str(rec["abstract"]) if rec is not None and isinstance(rec["abstract"], str) else ""
        pdf = pdf_by_doi.get(d) if d else None
        if pdf is None and len(tn) > 25:
            hit = idx[idx["head_n"].fillna("").str.contains(re.escape(tn[:70]), regex=True)]
            pdf = hit["pdf"].iloc[0] if len(hit) else None
        full = pdf_text(pdf) if pdf else ""
        a = assess(title, abstract, full)
        o = oa.loc[d] if len(oa) and d in oa.index else None
        rows.append({"decision_so_far": str(r.get("include_focused")), **a, "basis": "full text and abstract" if full else ("abstract" if len(abstract) > 100 else "title only"),
                     "study": r.get("study"), "year": r.get("year"), "title": title, "doi": r.get("doi"),
                     "doi_link": ("https://doi.org/" + d) if d and "/" in d else "", "pdf": str(pdf) if pdf else "",
                     "open_access": (o["oa_status"] if o is not None else ""), "open_access_pdf": (o["url"] if o is not None and isinstance(o["url"], str) else ""),
                     "retrieval": (o["status"] if o is not None else "")})
    T = pd.DataFrame(rows)
    order = {"Likely": 0, "Unclear": 1, "Unlikely": 2}
    T["o"] = T["triage"].map(order)
    T = T.sort_values(["o", "score"], ascending=[True, False]).drop(columns="o")
    pend = T[T["decision_so_far"] == "?"]
    pend.to_csv(P["out"] / "focused_triage.csv", index=False, encoding="utf-8-sig")
    need = pend[(pend["pdf"] == "") & (pend["triage"] != "Unlikely")]
    need[["triage", "study", "year", "title", "doi_link", "open_access", "open_access_pdf", "retrieval"]].to_csv(
        P["out"] / "fulltext_to_download.csv", index=False, encoding="utf-8-sig")
    # test of the rules on the studies the reviewer has decided
    Y, N = T[T["decision_so_far"].str.upper() == "Y"], T[T["decision_so_far"].str.upper() == "N"]
    st = {"n_candidates": int(len(pend)), "triage": {k: int((pend["triage"] == k).sum()) for k in order},
          "n_with_fulltext": int((pend["pdf"] != "").sum()), "n_fulltext_to_download": int(len(need)),
          "n_open_access_to_download": int((need["open_access_pdf"] != "").sum()),
          "check_included": {"n": int(len(Y)), **{k: int((Y["triage"] == k).sum()) for k in order}},
          "check_excluded": {"n": int(len(N)), **{k: int((N["triage"] == k).sum()) for k in order}}}
    dump(st, P["out"] / "stats_triage.json")
    T[T["decision_so_far"].str.upper().isin(["Y", "N"])].to_csv(P["out"] / "focused_triage_check.csv", index=False, encoding="utf-8-sig")
    return st
