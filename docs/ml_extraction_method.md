# Machine-learning and language-model extraction: method

Stages `review/s10_ml_extract.py` and `review/s11_llm_extract.py` add to the rule-based extraction of stage 9
(`docs/fulltext_extraction_method.md`). Like stage 9, they suggest values for the reviewer, with the page and sentence
each value was taken from. They never change the extraction sheet (`analysis/inputs/focused_extraction.csv`).

## Environment

The two stages use packages that the main pipeline does not need (PyTorch, sentence-transformers, RapidOCR, the
Anthropic client). They therefore run in a separate environment:

```
conda create -n review-ml -c conda-forge python=3.11 pandas openpyxl poppler numpy
conda activate review-ml
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r code/review/requirements-ml.txt
```

## Stage 10: OCR and sentence embeddings (local)

1. **Text and OCR.** Most PDFs have a text layer, which is read with `pdftotext` as in stage 9. A PDF with fewer than
   500 characters of text is treated as scanned. Its pages are rendered at 200 dpi (`pdftoppm`) and read with RapidOCR,
   which runs the PaddleOCR detection and recognition models in ONNX format. The recognised lines are put in reading
   order (top to bottom, then left to right). The OCR text is cached in `Lit/.ocr_cache/` under the file's hash.
2. **Sentences.** The reference list is removed and the body text is split into sentences with the stage 9 functions.
3. **Embeddings.** Each sentence is encoded with `sentence-transformers/all-MiniLM-L6-v2`, a 384-dimensional sentence
   embedding model that runs on the CPU. The vectors are normalised.
4. **Retrieval per field.** Each field has two or three short descriptions (in `FIELDS` in the source file): data,
   target, validation, metric, sample, openness and uncertainty. A sentence's score for a field is its highest cosine
   similarity to any of that field's descriptions. For each work and field, the five best sentences with a similarity
   of at least 0.35 are kept, with page and similarity. For validation, metric and sample, sentences that cite other
   work are left out, using the same filter as stage 9.
5. **Validation design (zero-shot).** Each design has a one-sentence description (in `DESIGNS`). Every retained
   validation sentence is compared with these descriptions and votes for the nearest one, weighted by the similarity,
   if that similarity is at least 0.45. The design with the most weight is the embedding suggestion.
6. **Combination.** The rule-based design from stage 9 is kept when stage 9 found one. Otherwise the embedding design is
   used. Both designs are listed side by side so the reviewer can see where they differ.

## Stage 11: language-model extraction with quote checking (optional)

1. **Request.** The body text of each work is sent to the Claude Messages API, with page markers and without the
   reference list. The settings are:
   - model `claude-opus-5-5` with adaptive reasoning at effort `high`;
   - a fixed instruction (`SYSTEM`) that lists the fields of the extraction sheet;
   - a JSON schema (`SCHEMA`) that the answer must follow.

   For each field the answer gives a value, a sentence copied word for word from the paper, and its page. The
   instruction says that statements about other studies are not evidence for the paper's own design or results.
2. **Quote check.** Each quote is searched for in the PDF text, after normalising spaces, hyphenation at line breaks
   and quotation marks. A quote is *verified* when it is found, either on the stated page or, with the page corrected,
   on another page. A quote that is not found is *not verified*: its value is flagged and is not used as a suggestion.
3. **Records.** Each answer is stored in `outputs/llm_cache/` under a hash of the model, instruction, schema and text,
   so that the outputs can be rebuilt without new requests. Each request is logged with its model and token counts in
   `outputs/llm_requests.csv`.
4. **Running it.** The stage needs an API key, set as `ANTHROPIC_API_KEY` in the environment or in
   `local_settings.py`, which is not under version control. It runs only when called directly:

   ```
   python code/review/s11_llm_extract.py <iteration folder> [--only-included] [--limit N]
   ```

## Agreement with the reviewer

The agreement with the reviewer is measured on the included focused studies that the reviewer extracted by hand. The
counts below were produced on 21 October 2026 from 253 works with full texts, none of which needed OCR.

| Method | Validation design | Headline metric value |
|---|---|---|
| Rules (stage 9) | 8 of 14 | 11 of 13 |
| Sentence embeddings alone (stage 10) | 4 of 14 | not applicable |
| Rules, then embeddings where the rules found no design (stage 10) | 9 of 14 | not applicable |
| Language model, verified quotes (stage 11) | not yet run | not yet run |

On its own, the zero-shot embedding classifier is weaker than the rules: it confuses general statements about testing
with the design itself. Its value lies in finding evidence sentences that use wording the rules miss. The design and
metric results above refer to these 14 studies only. In all, the rules and the embeddings suggest the same validation
design for 107 of the 253 works (iteration v0.14).

Stage 10 took 32 minutes on a laptop CPU for 253 works.

## Reporting

If the values from stage 10 or 11 are used in the review, the methods section should name:
- the models (the embedding model, the OCR models, and the language model with its version);
- the fact that every suggested value was checked by the reviewer against the quoted sentence;
- the agreement figures above.
