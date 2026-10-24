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
import argparse, ast, datetime, hashlib, json, pathlib, re, subprocess, sys, textwrap
import pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from safeio import keep                      # existing outputs are archived, never overwritten

CODE = pathlib.Path(__file__).resolve().parents[1]
PHD = CODE.parent
DATA = PHD / "data"
# scripts kept for our own record of how the work developed (exploratory comparisons, early checks): listed in the
# internal pipeline_reference.md, left out of the thesis appendix (pipeline_reference.tex)
INTERNAL = {"models/reproduce_old.py"}
# pipeline in run order: (stage, script, typical command)
PIPELINE = [
    ("1 Satellite data", "gee/gbem_composites.js", "Earth Engine Code Editor, BATCH = 'b1' ... 'b7'"),
    ("1 Satellite data", "gee/spec.py", "imported by the steps below"),
    ("1 Satellite data", "gee/ingest.py", "python gee/ingest.py <batch> <zips>"),
    ("1 Satellite data", "gee/preprocess.py", "python gee/preprocess.py --area <area> --year <year>"),
    ("1 Satellite data", "gee/extract.py", "python gee/extract.py --area <area> --year <year> --certificates"),
    ("1 Satellite data", "gee/fp_stats.py", "python gee/fp_stats.py --area <area> --year <year>"),
    ("1 Satellite data", "gee/extract_embed.py", "python gee/extract_embed.py --area <area> --year 2024"),
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
    ("2 Certificates and buildings", "epc/ber_dublin.py", "python epc/ber_dublin.py"),
    ("2 Certificates and buildings", "epc/assemble.py", "python epc/assemble.py --areas <areas>"),
    ("3 Context data", "geo/get_boundaries.py", "python geo/get_boundaries.py"),
    ("3 Context data", "geo/get_desnz_energy.py", "python geo/get_desnz_energy.py"),
    ("3 Context data", "geo/get_deprivation.py", "python geo/get_deprivation.py"),
    ("3 Context data", "geo/get_need.py", "python geo/get_need.py"),
    ("3 Context data", "geo/get_fuel_poverty.py", "python geo/get_fuel_poverty.py"),
    ("3 Context data", "geo/get_dublin.py", "python geo/get_dublin.py"),
    ("4 Models", "models/reproduce_old.py", "python models/reproduce_old.py --area <area>"),
    ("4 Models", "models/baseline.py", "python models/baseline.py --area <area> --years <years>"),
    ("4 Models", "models/retrofit_needs.py", "python models/retrofit_needs.py --area <area> --years <years>"),
    ("4 Models", "models/transfer.py", "python models/transfer.py --year 2024"),
    ("4 Models", "models/transfer_calibrate.py", "python models/transfer_calibrate.py --year 2024"),
    ("4 Models", "models/stock_predict.py", "python models/stock_predict.py --area <area> --year <year>"),
    ("4 Models", "models/calibrate_probs.py", "python models/calibrate_probs.py --area <area> --years <years>"),
    ("4 Models", "models/aoa.py", "python models/aoa.py --year 2024"),
    ("4 Models", "models/neighbour_baseline.py", "python models/neighbour_baseline.py --area <area> --year 2024"),
    ("4 Models", "models/metric_targets.py", "python models/metric_targets.py --area <area> --year 2024"),
    ("5 Analysis", "analysis/stock.py", "python analysis/stock.py --area <area>"),
    ("5 Analysis", "analysis/morph_types.py", "python analysis/morph_types.py --area <area>"),
    ("5 Analysis", "analysis/vulnerability.py", "python analysis/vulnerability.py --area <area>"),
    ("5 Analysis", "analysis/ground_truth.py", "python analysis/ground_truth.py --area <area>"),
    ("5 Analysis", "analysis/physics_check.py", "python analysis/physics_check.py --area <area>"),
    ("5 Analysis", "analysis/scale_eval.py", "python analysis/scale_eval.py --area <area>"),
    ("5 Analysis", "analysis/address_floor.py", "python analysis/address_floor.py --area <area>"),
    ("5 Analysis", "analysis/need_check.py", "python analysis/need_check.py"),
    ("5 Analysis", "analysis/stock_validate.py", "python analysis/stock_validate.py --area london"),
    ("5 Analysis", "analysis/heatpump_readiness.py", "python analysis/heatpump_readiness.py --area <area>"),
    ("5 Analysis", "analysis/heat_density.py", "python analysis/heat_density.py --area <area>"),
    ("5 Analysis", "analysis/targeting.py", "python analysis/targeting.py"),
    ("5 Analysis", "analysis/solar.py", "python analysis/solar.py --area <area>"),
    ("5 Analysis", "analysis/overheating.py", "python analysis/overheating.py --area <area>"),
    ("5 Analysis", "analysis/noise_eval.py", "python analysis/noise_eval.py --area <area>"),
    ("6 Communication", "viz/paper_figs.py", "python viz/paper_figs.py"),
    ("7 Records", "docs/doi_bib.py", "python docs/doi_bib.py <out.bib> key=doi ..."),
    ("6 Communication", "viz/dashboard.py", "python viz/dashboard.py --area <area> --tag <tag>"),
    ("6 Communication", "viz/atlas.py", "python viz/atlas.py [--public]"),
    ("7 Records", "docs/build_records.py", "python docs/build_records.py"),
    ("5 Analysis", "analysis/simulation_check.py", "python analysis/simulation_check.py"),
    ("4 Models", "models/repeat_cv.py", "python models/repeat_cv.py --area <area> --year 2024"),
    ("5 Analysis", "analysis/temporal_stability.py", "python analysis/temporal_stability.py --area <area>"),
    ("4 Models", "models/predict_footprints.py", "python models/predict_footprints.py --area <area> --fp-ids <ids> | --polygon <file>"),
    ("6 Communication", "geo/export_cityjson.py", "python geo/export_cityjson.py --area <area> [--nbhd <code> | --name <name>] --preview"),
    ("6 Communication", "geo/cityjson_to_ifc.py", "python geo/cityjson_to_ifc.py <district>.city.json (GeoBIM environment)"),
    ("7 Records", "docs/thesis_tables.py", "python docs/thesis_tables.py"),
    ("7 Records", "docs/build_thesis.py", "python docs/build_thesis.py"),
]
RESULTS = ["*/model/results/*.csv", "*/analysis/*.csv", "model_transfer/*.csv", "*/model/stock/*.csv"]


def tex(s):
    return (str(s).replace("\\", r"\textbackslash{}").replace("&", r"\&").replace("%", r"\%").replace("_", r"\_")
            .replace("#", r"\#").replace("$", r"\$").replace("{", r"\{").replace("}", r"\}").replace("~", r"\textasciitilde{}").replace("^", r"\textasciicircum{}"))


CMD = re.compile(r"(python|node|Rscript|rh|Earth Engine)\b")
ITEM = re.compile(r"^(\S(?:.{0,38}?\S)?)\s{2,}(\S.*)$")      # "term  description", term at most 40 characters


def doc_blocks(doc):
    """Parse a docstring written in the project's plain-text style into blocks: ('h', text), ('p', text),
    ('code', [lines]), ('dl', [[term, text]]), ('ul', [text]), ('ol', [text])."""
    first, _, rest = doc.strip("\n").partition("\n")                   # the first line may have lost its indent
    lines = [l.rstrip() for l in [first.strip()] + textwrap.dedent(rest).splitlines()]
    blocks, i, base = [], 0, 0
    nxt = lambda j: next((l for l in lines[j + 1:] if l.strip()), "")
    while i < len(lines):
        raw = lines[i]
        if not raw.strip():
            blocks.append(("blank", "")); i += 1; continue
        ind, t = len(raw) - len(raw.lstrip()), raw.strip()
        if ind == 0:
            base = 0
        ind -= base
        nx = nxt(i)
        # a short title line with an indented block below: a run-in heading; the block below is read as top level
        if ind == 0 and len(t) < 90 and not t.endswith((":", ".", ",", ";")) and nx and nx[:1] == " " and not ITEM.match(t):
            blocks.append(("h", t)); base = len(nx) - len(nx.lstrip()); i += 1; continue
        last = blocks[-1] if blocks else None
        if ind >= 2 and (CMD.match(t) or (last and last[0] == "code" and t[:1] in "[-|")):
            if last and last[0] == "code":
                last[1].append(t)
            else:
                blocks.append(("code", [t]))
            i += 1; continue
        m_ol, m_ul, m_dl = re.match(r"(\d+)[.)]\s+(.*)", t), re.match(r"[-*]\s+(.*)", t), ITEM.match(t)
        if ind <= 2 and m_ol:
            if last and last[0] == "ol" and last[2] == ind:
                last[1].append(m_ol.group(2))
            else:
                blocks.append(("ol", [m_ol.group(2)], ind))
        elif ind <= 4 and m_ul:
            if last and last[0] == "ul" and last[2] == ind:
                last[1].append(m_ul.group(1))
            else:
                blocks.append(("ul", [m_ul.group(1)], ind))
        elif last and last[0] in ("ol", "ul", "dl") and ind > last[2]:
            if last[0] == "dl":
                entry = last[1][-1]
                sub = ITEM.match(t)
                if sub and " " not in sub.group(1) and ind >= last[2] + 2 and len(raw) - len(raw.lstrip()) - base < 20:
                    entry.append([sub.group(1), sub.group(2)])        # nested option: [term, text, [sub], ...]
                elif len(entry) > 2:
                    entry[-1][1] += " " + t
                else:
                    entry[1] += " " + t
            else:
                last[1][-1] += " " + t
        elif last and last[0] == "ul" and last[2] == ind and ind >= 1:        # a bulleted list stays bulleted
            last[1].append(t)
        elif m_dl and not m_dl.group(1).endswith((".", ":")) and (ind >= 1 or base):
            if last and last[0] == "dl" and last[2] == ind:
                last[1].append([m_dl.group(1), m_dl.group(2)])
            else:
                blocks.append(("dl", [[m_dl.group(1), m_dl.group(2)]], ind))
        elif ind >= 1 and not (last and last[0] == "p" and not last[1].endswith(":")):
            if last and last[0] == "ul" and last[2] == ind:
                last[1].append(t)
            else:
                blocks.append(("ul", [t], ind))
        elif last and last[0] == "p":
            last[1] += " " + t
        else:
            blocks.append(["p", t])
        i += 1
    return [b for b in blocks if b[0] != "blank"]


def doc_tex(doc):
    """a script's docstring as LaTeX: paragraphs reflowed, outputs as description lists, commands as code"""
    # paths may break after a slash; command-line options keep both hyphens (no en dash)
    tex = lambda s: re.sub(r"([,=])(?=\S)", r"\1\\allowbreak{}", globals()["tex"](s).replace("/", "/\\allowbreak{}")
                           .replace("\\_", "\\_\\allowbreak{}").replace("--", "-{}-"))
    out = []
    for b in doc_blocks(doc):
        kind = b[0]
        if kind == "h":
            out.append(f"\\par\\textbf{{{tex(b[1])}}}\\par")
        elif kind == "p":
            out.append(tex(b[1]))
        elif kind == "code":
            out.append("\\begin{Verbatim}\n" + "\n".join(b[1]) + "\n\\end{Verbatim}")
        elif kind == "dl":
            items = []
            for k, v, *subs in b[1]:
                inner = ("\n\\begin{description}\n" + "\n".join(f"\\item[{{{tex(sk)}}}] {tex(sv)}" for sk, sv in subs)
                         + "\n\\end{description}") if subs else ""
                items.append(f"\\item[{{{tex(k)}}}] {tex(v)}{inner}")
            out.append("\\begin{description}\n" + "\n".join(items) + "\n\\end{description}")
        else:
            env = "itemize" if kind == "ul" else "enumerate"
            out.append(f"\\begin{{{env}}}\n" + "\n".join(f"\\item {tex(x)}" for x in b[1]) + f"\n\\end{{{env}}}")
    return "\n\n".join(out)


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
            doc = re.sub(r"^\*+\s*$\n?", "", doc, flags=re.M).strip()   # comment banner lines
        last = git("log", "-1", "--format=%h %cs", "--", script)
        md.append(f"\n### `{script}`\n\nCommand: `{cmd}`  \nLast change: {last}\n\n```text\n{doc}\n```\n")
        tx.append(f"\\subsection{{\\texttt{{{tex(script)}}}}}\\label{{code:{script.replace('/', '-').replace('.', '-')}}}\n"
                  f"\\noindent Command: \\texttt{{{tex(cmd).replace('--', '-{}-')}}}. Last change: {tex(last)}.\n\n{doc_tex(doc)}\n")
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
    s = DATA / "sap_stats_2024.csv"                                   # the label (analysis/sap_stats.py)
    if s.exists():
        s = pd.read_csv(s)
        for area, key in (("london", "Lon"), ("belfast", "Bel")):
            r = s[(s.area == area) & s["set"].str.startswith("certificates")]
            if len(r):
                r = r.iloc[0]
                for col, nm, d in (("mean", "Mean", 1), ("sd", "Sd", 1), ("median", "Median", 0), ("p25", "Pquart", 0), ("p75", "Pthreeq", 0),
                                   ("p05", "Pfive", 0), ("p95", "Pninetyfive", 0), ("mae_of_median", "MaeMedian", 1)):
                    put(f"{key}Sap{nm}", float(r[col]), d)
                put(f"{key}ShareCD", 100 * float(r.share_C + r.share_D), 0)
                put(f"{key}ShareEFG", 100 * float(r.share_E + r.share_F + r.share_G), 0)
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
