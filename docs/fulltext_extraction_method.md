# Full-text extraction: method

Stage `review/s09_fulltext_extract.py` of the review pipeline. It runs with every iteration (`run_all.py`,
`new_iteration.py`) after the full texts have been collected and indexed (stages `s04_fulltext.py` and `s08_triage.py`).

## Purpose

To support, not replace, the reviewer's data extraction for the focused subset and the candidates. Every value the
stage suggests carries the page and the sentence or table cell it was read from, so the reviewer can check it at the
source. The extraction sheet that feeds the manuscript tables (`analysis/inputs/focused_extraction.csv`) is never
changed by this stage.

## Input

All PDFs of the literature library that belong to a work of the review: included focused studies, focused-subset
candidates, core studies and review articles. PDFs are matched to records by DOI, or by title where there is no DOI
(index built by `s04_fulltext.py`).

## Steps

1. **Text.** Each PDF is converted to text page by page with `pdftotext` (Poppler). The reference list is cut off.
   Hyphenated line breaks are rejoined and the text is split into sentences.
2. **Sentence rules.** Each sentence is tested against documented dictionaries and patterns (all in the source file):
   - study area: country and city names;
   - data: about 30 named sensors, imagery sources, registers and open datasets;
   - sample size: counts of buildings, dwellings, certificates or images;
   - target: rating scale, number of classes, binary splits;
   - methods: model families and named architectures, interpretability methods;
   - validation: random split or k-fold, spatially blocked, held-out city or area, temporal hold-out, transfer with
     local fine-tuning, and split ratios;
   - metrics: metric name with its value, in either order, including error metrics written as plain numbers;
   - openness: code and data links (GitHub, Zenodo, figshare, OSF and similar) and data-availability statements;
   - uncertainty: calibration, confidence or prediction intervals.

   Sentences that cite other work (a bracketed reference number, "et al." or an author-year citation) are not used for
   validation, metrics or sample size, so that results of other studies are not attributed to the paper being read.
3. **Tables.** Each PDF is also converted with its column layout kept (`pdftotext -layout`). A line made of separate
   cells, at least two of which are metric names, is taken as a table header. In the lines below, each number is
   assigned to the closest header column, and the text at the start of the line is kept as the row label (the model or
   configuration). Mean ± deviation keeps the mean. Reading stops at the next caption or header, or after three lines
   without numbers. Each value is recorded with its table caption and row label.
4. **Summary per work.** Findings are counted per work. The suggested validation design is the strongest design the
   paper states about itself, in the order: spatially blocked, held-out city, held-out area, temporal, transfer with
   fine-tuning, random split.
5. **Check against the reviewer.** For the studies the reviewer has already extracted, the suggested validation design
   and the reviewer's headline metric value are compared with the extraction sheet. A metric value counts as found
   when a value of the same metric family lies within 0.006 of the reviewer's value (percentages converted).

## Outputs (in `analysis/outputs/` of each iteration)

| File | Content |
|---|---|
| `fulltext_extraction_auto.csv` | One row per work: the suggestions, summarised |
| `fulltext_evidence.csv` | One row per finding: work, field, value, page, sentence or table cell |
| `focused_prefill.xlsx` | The reviewer's values next to the suggestions, with agreement columns; one sheet for included studies, one for candidates |
| `stats_fulltext_extract.json` | Coverage and agreement with the reviewer |

## Agreement with the reviewer (iteration v0.13, 21 October 2026)

| Field | Agreement |
|---|---|
| Validation design (included studies with a design to compare) | 8 of 14 |
| Headline metric value found (included studies with a numeric value) | 11 of 13 |

Reasons for the remaining differences: values that the reviewer derived (for example the mean of two cities), a
different model's value reported in the text, metrics given only in figures, and validation designs described without
any of the phrases the rules recognise. The suggestions are therefore checked by the reviewer before they are used.

## How to run it on its own

```
python -c "import sys; sys.path.insert(0, 'code/review'); import config as cfg, s09_fulltext_extract as s; print(s.run(cfg, cfg.paths('<iteration folder>')))"
```

No generative model or external service is used: the stage consists of the regular expressions, dictionaries and
layout rules in the source file, so every suggestion can be traced to the rule and the text that produced it.
