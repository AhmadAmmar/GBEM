"""Stage 10 - machine-learning extraction from the full texts (OCR and sentence embeddings).

Complements the rule-based stage 9 with two local models (no external service once the model files are downloaded):

    OCR          PDFs without a text layer are rendered page by page (pdftoppm, 200 dpi) and read with RapidOCR
                 (PaddleOCR detection and recognition models in ONNX format). The text is cached next to the other
                 caches so later stages, including stage 9, can read these papers too.
    retrieval    every body-text sentence is encoded with a sentence-embedding model (all-MiniLM-L6-v2). For each field
                 of the extraction sheet (data, target, validation, metric, sample, openness, uncertainty) the sentences
                 closest to a set of field descriptions are kept, with page and similarity, as evidence for the reviewer.
                 This finds sentences that state a field in words the stage 9 patterns do not contain.
    validation   the validation design is classified by comparing the paper's validation sentences with a short
                 description of each design (nearest description, zero-shot). Sentences citing other work are left out,
                 as in stage 9. The stage 9 suggestion and the embedding suggestion are combined: a design found by both
                 is taken; otherwise the stage 9 design is kept and the embedding design is shown next to it.

For the studies the reviewer has already extracted, the suggestions are compared with the reviewer's values.

Requires the packages in requirements-ml.txt (separate environment; see docs/ml_extraction_method.md).
Output: outputs/ml_evidence.csv (top sentences per work and field), outputs/ml_extraction.csv (one row per work),
        outputs/stats_ml_extract.json (coverage and agreement with the reviewer)
"""
import re, json, hashlib, pathlib, subprocess, shutil, tempfile
import numpy as np
import pandas as pd
from common import norm_doi, dump, read_csv
from s04_fulltext import pdf_text
from s09_fulltext_extract import works_with_pdfs, pages_of, sentences, OTHER_WORK, VALIDATION

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 5            # sentences kept per work and field
MIN_SIM = 0.35       # below this a sentence is not kept as evidence
VAL_MIN_SIM = 0.45   # below this no validation design is suggested

FIELDS = {
    "data": ["The input data are satellite images, aerial photographs or street-level images of buildings.",
             "We used energy performance certificate records linked to building footprints.",
             "The dataset combines remote sensing imagery with building attributes from a national register."],
    "target": ["The target variable is the energy efficiency rating band from A to G.",
               "The model predicts the energy performance class of each building.",
               "The ratings were grouped into classes for the classification task."],
    "validation": ["The data were split into training and test sets.",
                   "The model was tested on buildings from a city that was not used for training.",
                   "We used k-fold cross-validation to evaluate the model."],
    "metric": ["The model achieved an accuracy of 0.75 on the test set.",
               "The best model reached a macro F1 score of 0.62.",
               "The results show a mean absolute error and root mean squared error of the predictions."],
    "sample": ["The dataset contains 50,000 buildings with an energy certificate.",
               "A total of 10,000 images of residential buildings were collected."],
    "open": ["The code and data are publicly available on GitHub.",
             "The data are available from the corresponding author on reasonable request."],
    "uncertainty": ["We report the uncertainty of the predictions with confidence intervals.",
                    "The predicted probabilities were calibrated."],
}
DESIGNS = {
    "Spatially blocked CV": "Cross-validation with spatial blocks, so that training and test buildings come from different spatial blocks, postcodes or districts.",
    "Held-out city": "The model was trained in one city and tested on another city that was not seen in training.",
    "Held-out area": "The test buildings come from a separate area or region that was held out from training.",
    "Temporal hold-out": "The model was trained on earlier years and tested on a later period.",
    "Transfer with local fine-tuning": "A model trained elsewhere was fine-tuned with a small number of local labelled samples from the target city.",
    "Random split": "The buildings were randomly split into training, validation and test sets, or k-fold cross-validation was used.",
}


def ocr_text(pdf, cache_dir):
    """Text of a scanned PDF (pages separated by form feeds), read with RapidOCR; cached by file hash."""
    h = hashlib.sha1(pathlib.Path(pdf).read_bytes()).hexdigest()[:16]
    cache = pathlib.Path(cache_dir) / f"{h}.txt"
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    from rapidocr_onnxruntime import RapidOCR
    engine, pages = RapidOCR(), []
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([shutil.which("pdftoppm"), "-r", "200", "-png", str(pdf), str(pathlib.Path(tmp) / "p")], check=True, capture_output=True)
        for png in sorted(pathlib.Path(tmp).glob("p-*.png"), key=lambda p: int(p.stem.split("-")[-1])):
            res, _ = engine(str(png))
            # boxes in reading order: top to bottom, then left to right
            lines = sorted(res or [], key=lambda r: (round(r[0][0][1] / 15), r[0][0][0]))
            pages.append("\n".join(r[1] for r in lines))
    text = "\f".join(pages)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    return text


def body_sentences(pdf, cache_dir):
    text, source = pdf_text(pdf), "text layer"
    if len(text.strip()) < 500:
        text, source = ocr_text(pdf, cache_dir), "OCR"
    out = [(pno, s) for pno, page in pages_of(text) for s in sentences(page)]
    return out, source


def run(cfg, P):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL, device="cpu")
    enc = lambda xs: model.encode(xs, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
    field_vecs = {f: enc(q) for f, q in FIELDS.items()}
    design_names = list(DESIGNS)
    design_vecs = enc([DESIGNS[n] for n in design_names])
    cache_dir = pathlib.Path(cfg.LIT) / ".ocr_cache"

    auto = read_csv(P["out"] / "fulltext_extraction_auto.csv") if (P["out"] / "fulltext_extraction_auto.csv").exists() else pd.DataFrame()
    rule_val = dict(zip(auto.get("doi", []), auto.get("validation_suggested", [])))
    rows, evid = [], []
    for d, title, status, key, pdf in works_with_pdfs(cfg, P):
        sents, source = body_sentences(pdf, cache_dir)
        if not sents:
            continue
        S = enc([s for _, s in sents])
        own = np.array([not re.search(OTHER_WORK, s) for _, s in sents])
        row = {"doi": d, "title": title, "status": status, "key": key, "pdf": pdf, "text_source": source, "n_sentences": len(sents)}
        for f, Q in field_vecs.items():
            sim = (S @ Q.T).max(axis=1)
            if f in ("validation", "metric", "sample"):
                sim = np.where(own, sim, -1)          # results and designs of other studies are not used
            top = [i for i in np.argsort(-sim)[:TOP_K] if sim[i] >= MIN_SIM]
            for rank, i in enumerate(top, 1):
                evid.append({"doi": d, "key": key, "field": f, "rank": rank, "similarity": round(float(sim[i]), 3),
                             "page": sents[i][0], "sentence": sents[i][1][:500]})
            row[f"{f}_top_sentence"] = sents[top[0]][1][:300] if top else ""
            if f == "validation" and top:
                # each candidate sentence votes for its nearest design, weighted by its similarity to that design
                votes = {}
                for i in top:
                    ds = design_vecs @ S[i]
                    j = int(ds.argmax())
                    if ds[j] >= VAL_MIN_SIM:
                        votes[design_names[j]] = votes.get(design_names[j], 0) + float(ds[j])
                row["validation_embedding"] = max(votes, key=votes.get) if votes else "Not found"
            elif f == "validation":
                row["validation_embedding"] = "Not found"
        r9 = rule_val.get(d, "Not found") if d else "Not found"
        row["validation_rules"] = r9
        row["validation_combined"] = r9 if r9 != "Not found" else row["validation_embedding"]
        row["validation_methods_agree"] = r9 == row["validation_embedding"]
        rows.append(row)

    A = pd.DataFrame(rows)
    A.to_csv(P["out"] / "ml_extraction.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(evid).to_csv(P["out"] / "ml_evidence.csv", index=False, encoding="utf-8-sig")

    # agreement with the reviewer (included focused studies)
    sheet = read_csv(P["inputs"] / cfg.HUMAN["focused_extraction"])
    Y = sheet[sheet["include_focused"].astype(str).str.upper() == "Y"].copy()
    Y["d"] = Y["doi"].map(norm_doi)
    Y = Y.merge(A, left_on="d", right_on="doi", how="inner", suffixes=("", "_ml"))
    def agrees(a, h):
        if not isinstance(h, str) or h in ("Not applicable", "Not applicable (zero-shot)"):
            return None
        return (a == h or (a in ("Held-out city", "Held-out area") and h in ("Held-out city", "Held-out area"))
                or (a == "Not found" and h in ("Not reported", "Internal (not specified)")))
    agree = {}
    for col in ("validation_rules", "validation_embedding", "validation_combined"):
        v = pd.Series([agrees(a, h) for a, h in zip(Y[col], Y["validation"])]).dropna()
        agree[col] = {"n": int(len(v)), "agree": int(v.sum())}
    st = {"model": MODEL, "n_works_read": int(len(A)), "ocr_works": int((A["text_source"] == "OCR").sum()) if len(A) else 0,
          "n_evidence_sentences": int(len(evid)), "validation_agreement": agree,
          "rules_and_embedding_agree": int(A["validation_methods_agree"].sum()) if len(A) else 0}
    dump(st, P["out"] / "stats_ml_extract.json")
    return st
