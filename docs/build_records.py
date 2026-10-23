"""Records for the thesis: what data, which steps, which results, with which software. Rebuild after every run.

    python build_records.py [--out <dir>]        default: Manuscripts/02_Thesis/generated

Writes:
  data_register.csv / .tex      every dataset folder under data/: description, source and licence (SOURCE.txt where
                                present), files, size, rows of tables, last change, checksums (SHA256SUMS.txt or
                                manifests where present; files under 200 MB are hashed here)
  pipeline_reference.md / .tex  every pipeline script in run order: purpose, command, inputs, outputs and method notes,
                                taken from the script's own documentation (module docstring), with its git version
  results_register.xlsx         every results table (models, analysis, transfer) as one sheet each, with its path
  numbers.tex                   LaTeX macros of the key results, read from the results files (e.g. \\LonAccEoMorph)
  environment.txt               Python, packages (conda list), git commit and tag of the code, time of the build
Nothing under data/ is changed. Outputs are archived before being replaced (safeio.keep).
"""
import argparse, ast, datetime, hashlib, json, pathlib, re, subprocess, sys
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

CODE = pathlib.Path(__file__).resolve().parents[1]
PHD = CODE.parent
DATA = PHD / "data"
# pipeline in run order: (stage, script, typical command)
PIPELINE = [
    ("1 Satellite data", "gee/gbem_composites.js", "Earth Engine Code Editor, BATCH = 'b1' ... 'b6'"),
    ("1 Satellite data", "gee/spec.py", "imported by the steps below"),
    ("1 Satellite data", "gee/ingest.py", "python gee/ingest.py <batch> <zips>"),
    ("1 Satellite data", "gee/preprocess.py", "python gee/preprocess.py --area <area> --year <year>"),
    ("1 Satellite data", "gee/extract.py", "python gee/extract.py --area <area> --year <year> --certificates"),
    ("1 Satellite data", "gee/fp_stats.py", "python gee/fp_stats.py --area <area> --year <year>"),
    ("2 Certificates and buildings", "epc/certificates.py", "python epc/certificates.py"),
    ("2 Certificates and buildings", "epc/footprints.py", "python epc/footprints.py"),
    ("2 Certificates and buildings", "epc/link.py", "python epc/link.py"),
    ("2 Certificates and buildings", "epc/morphology.py", "python epc/morphology.py"),
    ("2 Certificates and buildings", "epc/dwellings.py", "python epc/dwellings.py"),
    ("2 Certificates and buildings", "epc/census_ni.py", "python epc/census_ni.py"),
    ("2 Certificates and buildings", "epc/get_ni_lidar.py", "python epc/get_ni_lidar.py"),
    ("2 Certificates and buildings", "epc/lidar_ni.py", "python epc/lidar_ni.py"),
    ("2 Certificates and buildings", "epc/lidar_london.py", "python epc/lidar_london.py"),
    ("2 Certificates and buildings", "epc/streetscape.py", "python epc/streetscape.py --area <area>"),
    ("2 Certificates and buildings", "epc/physics.py", "python epc/physics.py --area <area>"),
    ("2 Certificates and buildings", "epc/assemble.py", "python epc/assemble.py --areas <areas>"),
    ("3 Context data", "geo/get_boundaries.py", "python geo/get_boundaries.py"),
    ("3 Context data", "geo/get_desnz_energy.py", "python geo/get_desnz_energy.py"),
    ("3 Context data", "geo/get_deprivation.py", "python geo/get_deprivation.py"),
    ("3 Context data", "geo/get_need.py", "python geo/get_need.py"),
    ("4 Models", "models/reproduce_old.py", "python models/reproduce_old.py --area <area>"),
    ("4 Models", "models/baseline.py", "python models/baseline.py --area <area> --years <years>"),
    ("4 Models", "models/retrofit_needs.py", "python models/retrofit_needs.py --area <area> --years <years>"),
    ("4 Models", "models/transfer.py", "python models/transfer.py --year 2024"),
    ("4 Models", "models/transfer_calibrate.py", "python models/transfer_calibrate.py --year 2024"),
    ("4 Models", "models/stock_predict.py", "python models/stock_predict.py --area <area> --year <year>"),
    ("4 Models", "models/calibrate_probs.py", "python models/calibrate_probs.py --area <area> --years <years>"),
    ("4 Models", "models/aoa.py", "python models/aoa.py --year 2024"),
    ("5 Analysis", "analysis/stock.py", "python analysis/stock.py --area <area>"),
    ("5 Analysis", "analysis/morph_types.py", "python analysis/morph_types.py --area <area>"),
    ("5 Analysis", "analysis/vulnerability.py", "python analysis/vulnerability.py --area <area>"),
    ("5 Analysis", "analysis/ground_truth.py", "python analysis/ground_truth.py --area <area>"),
    ("5 Analysis", "analysis/physics_check.py", "python analysis/physics_check.py --area <area>"),
    ("5 Analysis", "analysis/scale_eval.py", "python analysis/scale_eval.py --area <area>"),
    ("5 Analysis", "analysis/address_floor.py", "python analysis/address_floor.py --area <area>"),
    ("5 Analysis", "analysis/need_check.py", "python analysis/need_check.py"),
    ("5 Analysis", "analysis/stock_validate.py", "python analysis/stock_validate.py --area london"),
    ("6 Communication", "viz/paper_figs.py", "python viz/paper_figs.py"),
    ("7 Records", "docs/doi_bib.py", "python docs/doi_bib.py <out.bib> key=doi ..."),
    ("6 Communication", "viz/dashboard.py", "python viz/dashboard.py --area <area> --tag <tag>"),
    ("6 Communication", "viz/atlas.py", "python viz/atlas.py [--public]"),
    ("7 Records", "docs/build_records.py", "python docs/build_records.py"),
]
RESULTS = ["*/model/results/*.csv", "*/analysis/*.csv", "model_transfer/*.csv", "*/model/stock/*.csv"]


def tex(s):
    return (str(s).replace("\\", r"\textbackslash{}").replace("&", r"\&").replace("%", r"\%").replace("_", r"\_")
            .replace("#", r"\#").replace("$", r"\$").replace("{", r"\{").replace("}", r"\}").replace("~", r"\textasciitilde{}"))


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def data_register():
    rows = []
    for d in sorted({p.parent for p in DATA.rglob("*") if p.is_file() and "_archive" not in p.parts}):
        files = [p for p in d.iterdir() if p.is_file() and not p.name.endswith((".part", ".aux.xml"))]
        if not files:
            continue
        src = (d / "SOURCE.txt").read_text(encoding="utf-8", errors="replace").strip().splitlines() if (d / "SOURCE.txt").exists() else []
        n_rows = 0
        for p in files:
            try:
                if p.suffix == ".parquet":
                    import pyarrow.parquet as pq
                    n_rows += pq.ParquetFile(p).metadata.num_rows
            except Exception:
                pass
        small = [p for p in files if p.stat().st_size < 200e6 and p.suffix in (".parquet", ".csv", ".gpkg", ".json", ".zip", ".xlsx", ".xls", ".tif")]
        sums = {p.name: sha(p)[:16] for p in small[:40]}
        rows.append({"folder": str(d.relative_to(PHD)).replace("\\", "/"), "files": len(files),
                     "size_mb": round(sum(p.stat().st_size for p in files) / 1e6, 1), "table_rows": n_rows or None,
                     "types": ", ".join(sorted({p.suffix for p in files})), "last_change": datetime.datetime.fromtimestamp(max(p.stat().st_mtime for p in files)).strftime("%Y-%m-%d"),
                     "source": " ".join(src[:2])[:300], "sha256_16": json.dumps(sums) if sums else ""})
    return pd.DataFrame(rows)


def git(*args):
    return subprocess.run(["git", "-C", str(CODE), *args], capture_output=True, text=True).stdout.strip()


def pipeline_reference():
    md, tx = ["# Pipeline reference\n", f"Code version {git('describe', '--tags', '--always')} ({git('log', '-1', '--format=%h %cs')}).\n"], []
    stage = None
    for st, script, cmd in PIPELINE:
        p = CODE / script
        if not p.exists():
            continue
        if st != stage:
            md.append(f"\n## {st}\n"); tx.append(f"\\section{{{tex(st[2:])}}}"); stage = st
        doc = ""
        if p.suffix == ".py":
            doc = ast.get_docstring(ast.parse(p.read_text(encoding="utf-8"))) or ""
        elif p.suffix == ".js":
            m = re.search(r"/\*(.*?)\*/", p.read_text(encoding="utf-8"), re.S)
            doc = re.sub(r"^\s*\* ?", "", m.group(1), flags=re.M).strip() if m else ""
        last = git("log", "-1", "--format=%h %cs", "--", script)
        md.append(f"\n### `{script}`\n\nCommand: `{cmd}`  \nLast change: {last}\n\n```text\n{doc}\n```\n")
        tx.append(f"\\subsection{{\\texttt{{{tex(script)}}}}}\\label{{code:{script.replace('/', '-').replace('.', '-')}}}\n"
                  f"\\noindent Command: \\texttt{{{tex(cmd)}}}. Last change: {tex(last)}.\n\\begin{{verbatim}}\n{doc}\n\\end{{verbatim}}\n")
    return "\n".join(md), "\n".join(tx)


def results_register(out):
    files = sorted({p for pat in RESULTS for p in DATA.glob(pat) if "_archive" not in p.parts})
    index = []
    with pd.ExcelWriter(keep(out / "results_register.xlsx")) as xw:
        for i, p in enumerate(files):
            name = f"{i:03d}_{p.stem}"[:31]
            try:
                pd.read_csv(p).to_excel(xw, sheet_name=name, index=False)
                index.append({"sheet": name, "path": str(p.relative_to(PHD)).replace("\\", "/"),
                              "changed": datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")})
            except Exception as e:
                index.append({"sheet": "", "path": str(p.relative_to(PHD)), "changed": f"not read: {e}"})
        pd.DataFrame(index).to_excel(xw, sheet_name="index", index=False)
    return len(files)


def numbers():
    """key results as LaTeX macros; a missing file leaves its macros out (the thesis build then reports them)"""
    m = {}
    def put(k, v, d=1):
        if v is not None and v == v:
            m[k] = f"{v:.{d}f}" if isinstance(v, float) else f"{v:,}".replace(",", "{,}")
    for area, tag, key in (("london", "2024_s50k", "Lon"), ("belfast", "2024", "Bel")):
        f = DATA / area / "model/results" / f"baseline_{tag}.csv"
        if f.exists():
            b = pd.read_csv(f)
            for extra in sorted((DATA / area / "model/results").glob(f"baseline_{tag}_*.csv")):
                b = pd.concat([b, pd.read_csv(extra)]).drop_duplicates(["featureset", "validation", "model", "target"], keep="last")
            for fs, nm in (("eo", "Eo"), ("eo_morph_nolidar", "Form"), ("eo_morph", "EoMorph"), ("eo_morph_floor", "Floor"),
                           ("eo_morph_fps", "Fps"), ("eo_morph_ctx", "Ctx"), ("all", "All")):
                for val, vn in (("spatial", ""), ("random", "Rand")):
                    r = b[(b.featureset == fs) & (b.validation == val) & (b.model == "lgbm") & (b.target == "band")]
                    s = b[(b.featureset == fs) & (b.validation == val) & (b.model == "lgbm") & (b.target == "sap")]
                    if len(r):
                        put(f"{key}Acc{nm}{vn}", 100 * r.accuracy.iat[0]); put(f"{key}Qwk{nm}{vn}", r.qwk.iat[0], 2)
                    if len(s):
                        put(f"{key}Mae{nm}{vn}", s.mae.iat[0]); put(f"{key}Rsq{nm}{vn}", s.r2.iat[0], 2)
        cur = DATA / area / "analysis/vulnerability_summary.csv"
        if cur.exists():
            v = pd.read_csv(cur).iloc[0]
            put(f"{key}RhoSapIncome", v.spearman_sap_vs_income_deprivation, 2); put(f"{key}DoubleBurdenUnits", int(v.double_burden_units))
    t = DATA / "model_transfer/transfer_2024.csv"
    if t.exists():
        t = pd.read_csv(t)
        for exp, nm in (("London -> Belfast 2024", "LonToBel"), ("Belfast -> London 2024", "BelToLon")):
            r = t[(t.experiment == exp) & (t.featureset == "core")]
            if len(r):
                put(f"Acc{nm}", 100 * r.accuracy.iat[0]); put(f"Mae{nm}", r.sap_mae.iat[0])
    return "\n".join(f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in sorted(m.items())) + "\n", len(m)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(PHD / "Manuscripts/02_Thesis/generated"))
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    reg = data_register()
    reg.to_csv(keep(out / "data_register.csv"), index=False)
    lines = [r"\begin{longtable}{P{5.2cm}rrP{6.2cm}}", r"\toprule Folder & Files & MB & Source \\ \midrule \endhead"]
    lines += [f"\\texttt{{{tex(r.folder)}}} & {r.files} & {r.size_mb:,.0f} & {tex(r.source[:160])} \\\\" for r in reg.itertuples()]
    lines += [r"\bottomrule", r"\end{longtable}"]
    keep(out / "data_register.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    md, tx = pipeline_reference()
    keep(out / "pipeline_reference.md").write_text(md, encoding="utf-8")
    keep(out / "pipeline_reference.tex").write_text(tx, encoding="utf-8")
    n_res = results_register(out)
    nums, n_num = numbers()
    keep(out / "numbers.tex").write_text(nums, encoding="utf-8")
    env = subprocess.run(["conda", "list", "-n", "eo"], capture_output=True, text=True, shell=True).stdout
    keep(out / "environment.txt").write_text(f"built {datetime.datetime.now():%Y-%m-%d %H:%M}\npython {sys.version}\n"
                                              f"code {git('describe', '--tags', '--always')} {git('log', '-1', '--format=%H %cs')}\n\n{env}", encoding="utf-8")
    print(f"data register: {len(reg)} folders; pipeline: {sum((CODE / s).exists() for _, s, _ in PIPELINE)} scripts; "
          f"results: {n_res} tables; numbers: {n_num} macros -> {out}")


if __name__ == "__main__":
    main()
