"""Run the full review pipeline for one iteration folder.

    python run_all.py --iteration <iteration folder> [--scopus file1.csv file2.csv] [--wos file.txt] [--skip-fulltext]

Writes analysis/outputs/MANIFEST.md, which maps every script to its outputs and to the
manuscript elements they feed.
"""
import argparse, datetime, pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import config as cfg
import s00_ingest, s01_screen, s02_bibliometrics, s03_focused, s04_fulltext, s05_figures, s06_tex_outputs, s07_maps_textmining, s08_triage

STAGES = [
    ("s00_ingest", s00_ingest, "records.csv, duplicates.csv, stats_ingest.json", "PRISMA identification; all later stages"),
    ("s01_screen", s01_screen, "screening_decisions.csv, stats_screening.json; inputs/ templates", "PRISMA screening; Section 4.1-4.5; Table 7; Figs 5, 10"),
    ("s02_bibliometrics", s02_bibliometrics, "stats_biblio.json, top_sources/countries/keywords/thematic CSVs; fig04-fig08", "Section 3; Table 6; Figs 4-8; Appendix F"),
    ("s03_focused", s03_focused, "focused_final.csv, focused_candidates_pending.csv, stats_focused.json", "Sections 4.2-4.8; Tables 8, 9, D, E; Figs 11-12"),
    ("s04_fulltext", s04_fulltext, "pdf_doi_index.csv, fulltext_snippets.csv, fulltext_missing.csv", "Support for the extraction sheet and appraisal (Appendix D)"),
    ("s08_triage", s08_triage, "focused_triage.csv, focused_triage_check.csv, fulltext_to_download.csv, stats_triage.json", "Section 2.3 (candidates for the focused subset); work list for full-text screening"),
    ("s05_figures", s05_figures, "fig01-03, fig09-13, ga", "Figs 1-3, 9-13; graphical abstract"),
    ("s07_maps_textmining", s07_maps_textmining, "figS1-figS9 (word clouds, minimal maps, country profiles, collaboration, trends); review_tables.xlsx; top_authors.csv", "Appendix H (supplementary figures); tables workbook for supervisors"),
    ("s06_tex_outputs", s06_tex_outputs, "latex/generated/numbers.tex, tab_*.tex; references.bib additions", "All numbers and generated tables in the manuscript"),
]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--iteration", required=True)
    ap.add_argument("--scopus", nargs="*"); ap.add_argument("--wos", nargs="*")
    ap.add_argument("--skip-fulltext", action="store_true")
    a = ap.parse_args(argv)
    P = cfg.paths(a.iteration)
    log = []
    for name, mod, outs, feeds in STAGES:
        if name == "s04_fulltext" and a.skip_fulltext:
            log.append((name, "skipped", outs, feeds, 0)); continue
        t = time.time()
        res = mod.run(cfg, P, a.scopus, a.wos) if name == "s00_ingest" else mod.run(cfg, P)
        log.append((name, res, outs, feeds, time.time() - t))
        print(f"[{name}] done in {time.time() - t:.1f}s")
    m = [f"# Pipeline manifest\n\nRun: {datetime.datetime.now():%Y-%m-%d %H:%M}  \nIteration: `{P['it']}`  \n"
         f"Search: {cfg.SEARCH['search_date']} ({cfg.SEARCH['field']}); query file `{cfg.SEARCH['query_file']}`\n",
         "| Stage | Outputs | Feeds (manuscript) | Time (s) |", "|---|---|---|---|"]
    m += [f"| `{n}.py` | {o} | {f} | {t:.1f} |" for n, _, o, f, t in log]
    m.append("\n## Human inputs (analysis/inputs/)\n")
    m += [f"- `{v}`" for v in cfg.HUMAN.values()]
    (P["out"] / "MANIFEST.md").write_text("\n".join(m) + "\n", encoding="utf-8")
    return log


if __name__ == "__main__":
    main()
