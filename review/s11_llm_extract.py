"""Stage 11 - extraction with a large language model, checked against the source text (optional).

For each work with a full text, the body text (reference list removed, pages marked) is sent to the Claude Messages API
with the fields of the extraction sheet and a JSON schema. For every field the model must return a value and the exact
sentence of the paper that supports it, with its page. The quote is then searched for in the PDF text (after
normalising spaces, hyphenation and quotation marks):

    verified      the quote occurs in the paper on the stated page (or another page; the page is corrected)
    not verified  the quote does not occur in the paper; the value is kept only as a pointer and flagged

Values are suggestions for the reviewer, like those of stages 9 and 10; the extraction sheet is never changed. Responses
are cached per work (outputs are reproducible without new requests) and every request is logged with its token counts.

Runs only when an API key is available (environment variable ANTHROPIC_API_KEY, or ANTHROPIC_API_KEY in
local_settings.py) and only when asked for (python s11_llm_extract.py <iteration folder> [--limit N] [--only-included]).
Requires the packages in requirements-ml.txt.

Output: outputs/llm_extraction.csv (one row per work and field, with quote, page and verification),
        outputs/llm_requests.csv (one row per request: model, tokens), outputs/stats_llm_extract.json
"""
import os, re, sys, json, hashlib, pathlib, time
import pandas as pd
from common import norm_doi, dump, read_csv
from s04_fulltext import pdf_text
from s09_fulltext_extract import works_with_pdfs, pages_of

MODEL = "claude-opus-5-5"
EFFORT = "high"
MAX_CHARS = 400_000          # about 100k tokens; longer texts are sent in full up to this length and the cut is recorded

DESIGNS = ["Spatially blocked CV", "Held-out city", "Held-out area", "Temporal hold-out", "Transfer with local fine-tuning",
           "Random split", "Internal (not specified)", "Not reported", "Not applicable"]
FIELD_DOC = {
    "country": "Country or countries of the study area.",
    "area": "City, region or other study area.",
    "data": "Input data: imagery (satellite, aerial, street-level, thermal), LiDAR, registers, open datasets.",
    "target": "What is predicted: rating scale (e.g. EPC bands A-G), classes, or a continuous energy quantity.",
    "n_classes": "Number of target classes, if classification.",
    "sample_size": "Number of buildings, dwellings, certificates or images used.",
    "model_family": "Model family or architecture of the main model.",
    "validation": "Validation design of the paper's own experiments. One of: " + "; ".join(DESIGNS) + ".",
    "metric": "The headline evaluation metric of the paper's own best model (e.g. Macro-F1, Accuracy, R2, MAE).",
    "value": "The value of that metric, as a number exactly as written in the paper.",
    "code_data_open": "Whether code and/or data are openly available, with the link if given.",
    "uncertainty": "Whether uncertainty of predictions is reported (intervals, calibration).",
}
FIELD_SCHEMA = {"type": "object",
                "properties": {"value": {"type": "string"}, "quote": {"type": "string"}, "page": {"type": "integer"}},
                "required": ["value", "quote", "page"], "additionalProperties": False}
SCHEMA = {"type": "object", "properties": {f: FIELD_SCHEMA for f in FIELD_DOC}, "required": list(FIELD_DOC), "additionalProperties": False}

SYSTEM = ("You extract data from a scientific paper for a systematic review of remote sensing and geospatial methods for "
          "estimating building energy efficiency and energy performance certificate (EPC) ratings.\n\n"
          "For each field, return:\n"
          "- value: a short answer. Use \"Not reported\" when the paper does not state it.\n"
          "- quote: one sentence or table line copied character for character from the paper that supports the value "
          "(empty when the value is \"Not reported\"). Do not paraphrase, shorten or join sentences.\n"
          "- page: the page number given in the [Page N] marker before the quote (0 when there is no quote).\n\n"
          "Report only the paper's own work. Sentences that describe other studies (with citations) are not evidence "
          "for the paper's validation design, metric or value.\n\nFields:\n"
          + "\n".join(f"- {f}: {d}" for f, d in FIELD_DOC.items()))


def api_key():
    k = os.environ.get("ANTHROPIC_API_KEY")
    if not k:
        try:
            import local_settings
            k = getattr(local_settings, "ANTHROPIC_API_KEY", None)
        except ImportError:
            pass
    return k


def norm(s):
    s = re.sub(r"-\s*\n\s*(\w)", r"\1", s)
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).strip().lower()


def verify(quote, pages):
    """Page on which the quote occurs (the stated page first), or None."""
    q = norm(quote)
    if len(q) < 12:
        return None
    hits = [p for p, t in pages if q in t]
    return hits[0] if hits else None


def request(client, text):
    with client.beta.messages.stream(
        model=MODEL, max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        thinking={"type": "adaptive"}, output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": text}],
    ) as stream:
        return stream.get_final_message()


def run(cfg, P, limit=None, only_included=False):
    import anthropic
    key = api_key()
    if not key:
        raise SystemExit("No API key: set ANTHROPIC_API_KEY or add it to local_settings.py")
    client = anthropic.Anthropic(api_key=key)
    cache = P["out"] / "llm_cache"; cache.mkdir(exist_ok=True)
    rows, log = [], []
    works = works_with_pdfs(cfg, P)
    if only_included:
        works = [w for w in works if w[2] == "focused (included)"]
    for n, (d, title, status, key_, pdf) in enumerate(works[:limit] if limit else works, 1):
        pages = pages_of(pdf_text(pdf))
        body = "\n\n".join(f"[Page {p}]\n{t}" for p, t in pages)
        if len(body.strip()) < 500:
            continue
        cut = len(body) > MAX_CHARS
        text = f"Title: {title}\n\n{body[:MAX_CHARS]}"
        h = hashlib.sha1((MODEL + SYSTEM + json.dumps(SCHEMA) + text).encode("utf-8")).hexdigest()[:16]
        f = cache / f"{h}.json"
        if f.exists():
            out = json.loads(f.read_text(encoding="utf-8"))
        else:
            try:
                msg = request(client, text)
            except anthropic.RateLimitError:
                time.sleep(60); msg = request(client, text)
            except anthropic.APIStatusError as e:
                log.append({"doi": d, "title": title, "error": f"{e.status_code} {e.message}"[:300]}); continue
            if msg.stop_reason == "refusal":
                log.append({"doi": d, "title": title, "error": "refusal"}); continue
            txt = next((b.text for b in msg.content if b.type == "text"), "")
            out = {"model": msg.model, "stop_reason": msg.stop_reason, "answer": json.loads(txt) if txt else {},
                   "usage": {k: getattr(msg.usage, k, None) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}}
            f.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"{n}/{len(works)} {d or title[:50]} {out['usage']}", flush=True)
        log.append({"doi": d, "title": title, "model": out["model"], "text_cut": cut, **out["usage"]})
        np_ = [(p, norm(t)) for p, t in pages]
        for field, a in out["answer"].items():
            page = verify(a.get("quote", ""), sorted(np_, key=lambda x: x[0] != a.get("page")))
            rows.append({"doi": d, "key": key_, "title": title, "status": status, "field": field, "value": a.get("value", ""),
                         "quote": a.get("quote", ""), "page_stated": a.get("page"), "page_found": page,
                         "verified": None if not a.get("quote") else page is not None, "model": out["model"]})
    R = pd.DataFrame(rows)
    R.to_csv(P["out"] / "llm_extraction.csv", index=False, encoding="utf-8-sig")
    L = pd.DataFrame(log)
    L.to_csv(P["out"] / "llm_requests.csv", index=False, encoding="utf-8-sig")

    st = {"model": MODEL, "effort": EFFORT, "n_works": int(R["doi"].nunique()) if len(R) else 0,
          "quotes": int(R["verified"].notna().sum()) if len(R) else 0, "quotes_verified": int((R["verified"] == True).sum()) if len(R) else 0}
    for c in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
        st[c] = int(pd.to_numeric(L.get(c, pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
    # agreement with the reviewer (included focused studies), verified values only
    sheet = read_csv(P["inputs"] / cfg.HUMAN["focused_extraction"])
    Y = sheet[sheet["include_focused"].astype(str).str.upper() == "Y"].assign(d=lambda x: x["doi"].map(norm_doi))
    if len(R):
        V = R[R["field"] == "validation"].set_index("doi")["value"]
        Mv = R[R["field"] == "value"].set_index("doi")["value"]
        va, mv = [], []
        for r in Y.itertuples():
            if r.d in V.index and isinstance(r.validation, str) and not r.validation.startswith("Not applicable"):
                va.append(V[r.d] == r.validation or {V[r.d], r.validation} <= {"Held-out city", "Held-out area"}
                          or (V[r.d] in ("Not reported", "Internal (not specified)") and r.validation in ("Not reported", "Internal (not specified)")))
            try:
                hv = float(r.value)
                x = float(re.sub(r"[^\d.]", "", str(Mv[r.d]))) if r.d in Mv.index else None
                if x is not None:
                    mv.append(abs((x / 100 if x > 1.5 else x) - (hv / 100 if hv > 1.5 else hv)) <= 0.006)
            except (TypeError, ValueError):
                pass
        st["validation_agreement"] = {"n": len(va), "agree": int(sum(va))}
        st["metric_value_agreement"] = {"n": len(mv), "agree": int(sum(mv))}
    dump(st, P["out"] / "stats_llm_extract.json")
    return st


if __name__ == "__main__":
    import argparse, config as cfg
    ap = argparse.ArgumentParser()
    ap.add_argument("iteration"); ap.add_argument("--limit", type=int); ap.add_argument("--only-included", action="store_true")
    a = ap.parse_args()
    print(run(cfg, cfg.paths(a.iteration), a.limit, a.only_included))
