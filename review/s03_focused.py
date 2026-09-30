"""Stage 3 - focused subset: candidate list + full-text extraction sheet.

Candidates = core studies with a rating/label target (database arm)
           + studies in inputs/supplementary_studies.csv (other methods).
The extraction sheet inputs/focused_extraction.csv is the single place where full-text
data are entered. New candidates are appended with abstract-derived pre-fills and
include_focused = "?" until a reviewer sets Y or N; existing rows are never overwritten.

Output: outputs/focused_final.csv (include_focused == Y), outputs/focused_candidates_pending.csv,
        outputs/stats_focused.json
Feeds : Tables 8, 9, D.13, E.14; Figs 11, 12; Sections 4.2-4.8.
"""
import pathlib
import pandas as pd
from common import norm_doi, norm_title, dump, read_csv

SEED = pathlib.Path(__file__).resolve().parent / "seed" / "focused_seed.csv"
COLS = ["key", "doi", "study", "title", "year", "arm", "country", "area", "data", "target", "target_type", "n_classes",
        "model_family", "validation", "validation_detail", "metric", "value", "metric_note", "source_of_extraction",
        "code_data_open", "q1_label", "q2_timegap", "q3_spatial", "q4_unseen", "q5_classwise", "q6_leakage",
        "q7_uncertainty", "q8_open", "include_focused", "verified_by", "notes"]
VALIDATION_ORDER = ["Random split", "Held-out city", "Held-out area", "Spatially blocked CV", "Temporal hold-out",
                    "Transfer with local fine-tuning", "Internal (not specified)", "Not reported"]
PREDICTIVE_EXCLUDE = {"Not applicable", "Not applicable (zero-shot)"}


def run(cfg, P):
    dec = read_csv(P["out"] / "screening_decisions.csv")
    sheet_path = P["inputs"] / cfg.HUMAN["focused_extraction"]
    supp_path = P["inputs"] / cfg.HUMAN["supplementary_studies"]
    if not sheet_path.exists():
        read_csv(SEED).reindex(columns=COLS).to_csv(sheet_path, index=False, encoding="utf-8-sig")
    if not supp_path.exists():
        s = read_csv(SEED)
        s = s[s["arm"] == "Supplementary"][["doi", "study", "year"]].assign(route="citation searching / expert suggestion", note="")
        s.to_csv(supp_path, index=False, encoding="utf-8-sig")
    sheet = read_csv(sheet_path).reindex(columns=COLS)
    known = set(sheet["doi"].map(norm_doi)) - {""}
    known_titles = set(sheet["title"].map(norm_title)) - {""}

    # database-arm candidates not yet in the sheet (matched by DOI, or by title when there is no DOI)
    core = dec[dec["decision"] == "Included (core)"].copy()
    cand = core[core["target"].fillna("").str.contains("Rating")]
    new = []
    for _, r in cand.iterrows():
        d = norm_doi(r["doi"])
        if (d and d in known) or (not d and norm_title(r["title"]) in known_titles):
            continue
        first = str(r["authors"]).split(";")[0].split(",")[0].strip()
        new.append({"key": "", "doi": r["doi"], "study": f"{first} et al.", "year": r["year"], "arm": "Database",
                    "country": r["study_country"], "data": r["modality"], "target": r["target"],
                    "model_family": r["method"], "validation": "", "source_of_extraction": "Abstract (pre-fill)",
                    "include_focused": "?", "title": r["title"]})
    supp = read_csv(supp_path)
    for _, r in supp.iterrows():
        d = norm_doi(r.get("doi"))
        if d and d not in known and d not in {norm_doi(x["doi"]) for x in new}:
            new.append({"doi": r["doi"], "study": r.get("study"), "year": r.get("year"), "arm": "Supplementary",
                        "include_focused": "?", "source_of_extraction": "", "notes": r.get("note", "")})
    if new:
        sheet = pd.concat([sheet, pd.DataFrame(new).reindex(columns=COLS)], ignore_index=True)
        sheet.to_csv(sheet_path, index=False, encoding="utf-8-sig")

    # database arm = in the current screened records; otherwise other methods
    in_db = set(dec["doi"].map(norm_doi))
    sheet["arm_now"] = sheet["doi"].map(lambda d: "Database" if norm_doi(d) in in_db else "Other methods")
    F = sheet[sheet["include_focused"].astype(str).str.upper().eq("Y")].copy()
    F.to_csv(P["out"] / "focused_final.csv", index=False, encoding="utf-8-sig")
    sheet[sheet["include_focused"].astype(str).eq("?")].to_csv(P["out"] / "focused_candidates_pending.csv", index=False, encoding="utf-8-sig")
    pred = F[~F["validation"].fillna("").isin(PREDICTIVE_EXCLUDE) & F["validation"].fillna("").ne("")]
    vc = pred["validation"].value_counts()
    held = int(vc.get("Held-out city", 0) + vc.get("Held-out area", 0))
    num = lambda s: pd.to_numeric(s, errors="coerce")
    binf1 = num(F.loc[F["target_type"].eq("Binary") & F["metric"].str.contains("F1", na=False), "value"])
    st = {"n_focused": int(len(F)), "n_focused_db": int((F["arm_now"] == "Database").sum()),
          "n_focused_other": int((F["arm_now"] == "Other methods").sum()),
          "n_pending": int(sheet["include_focused"].astype(str).eq("?").sum()),
          "n_predictive": int(len(pred)), "validation_counts": {k: int(vc.get(k, 0)) for k in VALIDATION_ORDER},
          "n_heldout": held, "n_temporal": int(vc.get("Temporal hold-out", 0)),
          "n_random": int(vc.get("Random split", 0)),
          "n_uk": int(F["country"].eq("United Kingdom").sum()),
          "countries": F["country"].value_counts().to_dict(),
          "binary_f1_range": [float(binf1.min()), float(binf1.max())] if len(binf1) else None,
          "n_metrics": int(pred["metric"].replace({"Not reported in abstract": None, "Not extracted": None}).dropna().nunique()),
          "n_fulltext": int(F["source_of_extraction"].fillna("").str.startswith("Full text").sum())}
    dump(st, P["out"] / "stats_focused.json")
    return st
