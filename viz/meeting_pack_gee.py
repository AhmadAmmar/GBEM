"""Meeting pack for the Earth Engine data (method v2_0_1): map panels, quality charts and a one-page dashboard.

    python meeting_pack_gee.py [--out <folder>]

Reads only the outputs of the gee/ pipeline (quick-looks, ingest QA, feature logs, reproduction tables) and writes to
Outputs/<date>_GEE_data_v2/ by default:
  01_maps_london.png, 02_maps_belfast.png     six products per area (quick-looks with titles)
  03_reproduction_agreement.png                Spearman correlation with the earlier 2024 samples, per variable
  04_feature_coverage.png                      share of certificates with a value, per feature
  05_s1_*.png                                  Sentinel-1 maps (copied from Maps/gee_v2/)
  dashboard.html                               one page with headline numbers, the figures and the tables
Charts use the reference categorical palette (London slot 1, Belfast slot 2; validated adjacent pair).
"""
import argparse, datetime, json, pathlib, shutil
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

PHD = pathlib.Path(__file__).resolve().parents[2]
DATA = PHD / "data"
COL = {"london": "#2a78d6", "belfast": "#eb6834"}
LABEL = {"london": "Greater London", "belfast": "Greater Belfast"}
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({"font.family": "Arial", "font.size": 10, "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK, "axes.edgecolor": GRID, "figure.facecolor": SURF,
                     "axes.facecolor": SURF, "savefig.facecolor": SURF})

PANELS = [("S2_true_colour_annual", "Sentinel-2 true colour, 2024"),
          ("Landsat_LST_summer__deg_C_x_100_", "Landsat LST, summer 2024"),
          ("MODIS_terra_night_LST_winter__deg_C_x_100_", "MODIS night LST, winter 2024"),
          ("VIIRS_night_lights__annual__nW_cm_2_sr_1_", "VIIRS night lights, 2024"),
          ("WorldCover_2021", "ESA WorldCover 2021"),
          ("GHSL_building_height_2018__m_", "GHSL building height, 2018")]

# earlier variable -> label in the chart (best-matching new variable is taken from compare_old_<area>.csv)
AGREE = {"Sentinel-1 VV": ["s1_VV_dB", "VV"], "Sentinel-1 VH": ["s1_VH_dB", "VH"], "NDVI": ["s2_NDVI", "NDVI"],
         "NDWI": ["s2_NDWI", "NDWI"], "EVI": ["s2_EVI", "EVI"], "NDBI": ["s2_NDBI", "NDBI"],
         "Landsat LST": ["l8_LST_C", "L8B10"], "MODIS night LST": ["modis_LST_night_C"], "Elevation": ["dem_elev"],
         "Slope": ["dem_slope"], "VIIRS night lights": ["viirs_avg_rad"], "ERA5 air temperature": ["era5_t2m_K"]}
COVER = {"Sentinel-2 NDVI": "s2_NDVI_annual_pt", "Sentinel-1 VV": "s1_VV_dB_annual_pt",
         "Landsat LST annual": "landsat_LST_annual_pt", "Landsat LST summer": "landsat_LST_summer_pt",
         "Landsat LST winter": "landsat_LST_winter_pt", "MODIS night LST winter": "modis_terra_night_winter_pt",
         "ERA5 air temperature": "era5_t2m_annual_pt"}


def map_panels(area, out):
    q = DATA / area / "gee_v2" / "qa" / "quicklooks"
    fig, axs = plt.subplots(2, 3, figsize=(15, 9.6))
    for ax, (f, title) in zip(axs.ravel(), PANELS):
        ax.imshow(mpimg.imread(q / f"{f}.png")); ax.set_title(title, fontsize=11, loc="left", pad=6); ax.axis("off")
    fig.suptitle(f"{LABEL[area]}: Earth Engine products (method v2_0_1), study-area boundary in black",
                 x=0.01, ha="left", fontsize=13, fontweight="bold")
    fig.text(0.01, 0.01, "Each layer stretched between its 2nd and 98th percentiles. Temperature: blue cool, red warm; "
             "white = no clear observation. Night lights: dark low, light high. Building height: dark low, yellow high.",
             fontsize=9, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 0.96), h_pad=2.5); fig.savefig(out, dpi=150); plt.close(fig)


def hbars(rows, title, xlabel, out, xlim):
    """Grouped horizontal bars: rows = list of (label, {area: value or None})."""
    fig, ax = plt.subplots(figsize=(9, 0.42 * len(rows) + 1.6))
    h = 0.36
    for i, (lab, vals) in enumerate(rows):
        for j, area in enumerate(COL):
            v = vals.get(area)
            if v is None:
                continue
            ax.barh(i + (j - 0.5) * h * 1.06, v, height=h, color=COL[area], edgecolor=SURF, linewidth=1)
    ax.set_yticks(range(len(rows))); ax.set_yticklabels([r[0] for r in rows]); ax.invert_yaxis()
    ax.set_xlim(*xlim); ax.set_xlabel(xlabel)
    ax.grid(axis="x", color=GRID, linewidth=0.8); ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(axis="y", length=0)
    handles = [plt.Rectangle((0, 0), 1, 1, color=COL[a]) for a in COL]
    ax.legend(handles, [LABEL[a] for a in COL], loc="lower right", bbox_to_anchor=(1, 1.0), ncol=2, frameon=False,
              borderaxespad=0.2)
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", pad=24)
    fig.tight_layout(); fig.savefig(out, dpi=150); plt.close(fig)


def agreement():
    best = {}
    for area in COL:
        c = pd.read_csv(DATA / area / "gee_v2" / "features" / f"compare_old_{area}.csv")
        best[area] = c.groupby("old")["spearman"].max()
    rows, table = [], []
    for lab, olds in AGREE.items():
        vals = {a: next((float(best[a][o]) for o in olds if o in best[a]), None) for a in COL}
        if any(v is not None for v in vals.values()):
            rows.append((lab, vals)); table.append({"variable": lab, **{LABEL[a]: vals[a] for a in COL}})
    return rows, pd.DataFrame(table)


def coverage():
    rows, table, logs = [], [], {}
    for area in COL:
        logs[area] = json.loads((DATA / area / "gee_v2" / "features" / "epc2024_2024_log.json").read_text(encoding="utf-8"))
    for lab, col in COVER.items():
        vals = {a: 100 * (1 - logs[a]["missing_share"].get(col, 0.0)) for a in COL}
        rows.append((lab, vals)); table.append({"feature": lab, **{LABEL[a]: round(vals[a], 1) for a in COL}})
    return rows, pd.DataFrame(table), logs


def html(out, logs, agree_t, cover_t, files):
    man = pd.read_csv(DATA / "gee_v2" / "manifest.csv")
    tiles = [("GeoTIFFs ingested, all checks passed", f"{(man['checks'] == 'ok').sum()} / {len(man)}"),
             ("London certificates (2024)", f"{logs['london']['n_records']:,}"),
             ("Belfast certificates (2024)", f"{logs['belfast']['n_records']:,}"),
             ("Features per certificate", f"{logs['london']['n_features']}")]
    tile_html = "".join(f'<div class="tile"><div class="v">{v}</div><div class="k">{k}</div></div>' for k, v in tiles)
    fig_html = "".join(f'<figure><img src="{f}" alt="{c}"><figcaption>{c}</figcaption></figure>' for f, c in files)
    fmt = lambda df: df.to_html(index=False, na_rep="–", float_format=lambda x: f"{x:.2f}", border=0)
    page = f"""<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>GEE data v2</title><style>
:root{{--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--rule:#e4e3df;--accent:#2a78d6}}
@media (prefers-color-scheme:dark){{:root{{--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--rule:#3a3936;--accent:#3987e5}}}}
body{{margin:0;background:var(--surface);color:var(--ink);font:15px/1.5 Arial,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:24px 16px}} h1{{font-size:24px;margin:0 0 4px}} h2{{font-size:18px;margin:32px 0 8px}}
p.sub{{color:var(--ink2);margin:0 0 20px}} .tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}}
.tile{{border:1px solid var(--rule);border-radius:8px;padding:12px}} .v{{font-size:26px;font-weight:bold}} .k{{color:var(--ink2);font-size:13px}}
figure{{margin:16px 0}} img{{max-width:100%;border:1px solid var(--rule);border-radius:6px;background:#fff}} figcaption{{color:var(--ink2);font-size:13px}}
table{{border-collapse:collapse;font-size:14px;margin:8px 0}} th,td{{padding:4px 12px;border-bottom:1px solid var(--rule);text-align:right}} th:first-child,td:first-child{{text-align:left}}
ul{{padding-left:20px}}</style></head><body><main>
<h1>Earth Engine data for the EPC models: 2024 batch</h1>
<p class="sub">Composites method v2_0_1 (gbem_composites.js 2.1.0); local processing GBEM v0.28.0. Generated {datetime.date.today():%d %B %Y}.</p>
<div class="tiles">{tile_html}</div>
<h2>Points for discussion</h2><ul>
<li>Exports for 2024 are in place and checked. 2020–2023 and 2025 are scripted in three batches (at most 5 GB each).</li>
<li>Features per certificate: values at the certificate point, the footprint mean and the mean over about 100 m. Sentinel-2 indices are computed per pixel; Sentinel-1 is averaged in linear power.</li>
<li>Reproduction of the earlier 2024 samples: Sentinel-1, elevation and night lights are reproduced; the optical and thermal variables agree moderately. The earlier composite windows and cloud masks are not recorded.</li>
<li>Two earlier features are not carried over. The earlier UI (B11/B8) duplicated NDBI. IBI was numerically unstable, with values up to ±30,000.</li>
<li>Thermal gaps: seasonal Landsat LST is missing for 14–28% of certificates. Annual Landsat LST and winter-night MODIS LST are complete.</li>
<li>Next input needed: the certificates of 2020–2025 linked to UPRN and footprint (objective 2), so that the other years can be extracted.</li></ul>
<h2>Figures</h2>{fig_html}
<h2>Agreement with the earlier 2024 samples (Spearman, point values)</h2>{fmt(agree_t)}
<h2>Certificates with a value (%)</h2>{fmt(cover_t)}
</main></body></html>"""
    (out / "dashboard.html").write_text(page, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(PHD / "Outputs" / f"{datetime.date.today():%Y-%m-%d}_GEE_data_v2"))
    out = pathlib.Path(ap.parse_args().out); out.mkdir(parents=True, exist_ok=True)
    map_panels("london", out / "01_maps_london.png"); map_panels("belfast", out / "02_maps_belfast.png")
    rows, agree_t = agreement()
    hbars(rows, "Agreement with the earlier 2024 samples (same certificates)", "Spearman correlation, point values", out / "03_reproduction_agreement.png", (0, 1))
    crow, cover_t, logs = coverage()
    hbars(crow, "Certificates with a value, 2024", "% of certificates", out / "04_feature_coverage.png", (0, 100))
    files = [("01_maps_london.png", "Greater London: six of the exported products"), ("02_maps_belfast.png", "Greater Belfast: six of the exported products"),
             ("03_reproduction_agreement.png", "Agreement with the earlier samples; missing bars: variable not in that area's earlier samples"),
             ("04_feature_coverage.png", "Share of certificates with a value per feature")]
    for p in sorted((PHD / "Maps" / "gee_v2").glob("london_s1_2024_*.png")):
        shutil.copy(p, out / ("05_s1_" + p.name.replace("london_s1_2024_", "")))
        files.append(("05_s1_" + p.name.replace("london_s1_2024_", ""), "Sentinel-1, Greater London: " + p.stem.split("_")[-1]))
    agree_t.to_csv(out / "agreement.csv", index=False); cover_t.to_csv(out / "coverage.csv", index=False)
    html(out, logs, agree_t, cover_t, files)
    print("written", out)


if __name__ == "__main__":
    main()
