# -*- coding: utf-8 -*-
"""
study_area_maps_final.py

• Robust UK+IE inset (local → GeoPandas NE-lowres; optional Cartopy admin1 lines).
• Clean inset labels (halo only), optional admin1 lines OFF by default.
• City dot with white outline; no stray boxes around labels.
• Scalebars share a *figure-aligned* Y (perfectly straight across panels; clip_off).
• Equal visual width panels; equal point totals via stratified sampling.
• Optional density underlay; Belfast can be slightly padded smaller.
"""

import os, json, warnings, math, textwrap
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import box as shp_box, LineString
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import matplotlib.patheffects as pe
from matplotlib.transforms import blended_transform_factory as _btf

# ───────────────────────── I/O (EDIT THESE) ─────────────────────────
OUTDIR = r"D:\OneDrive - Ulster University\PhD\Maps"

# London
LONDON_BOUNDARY = r"D:\OneDrive - Ulster University\PhD\data\london\SHP\london.shp"
LONDON_EPC      = r"D:\OneDrive - Ulster University\PhD\data\london\london_epc_points.geojson"
LONDON_CRS      = "EPSG:27700"     # OSGB36 / BNG

# Belfast
BELFAST_BOUNDARY  = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-dissolved\belfast-dissolved.shp"
BELFAST_EPC_CSV   = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-epc\gee_epc_2024_points_uid_wgs84.csv"
BELFAST_EPC_POLYS = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-epc\gee_epc_2024_polygons_uid_wgs84_shp\gee_epc_2024_polys.shp"
BELFAST_CRS       = "EPSG:2157"    # Irish Transverse Mercator

# Optional local admin0 file for the inset background (if you have one)
UK_IE_LOCATOR_PATH = None  # e.g., r"D:\data\ne_admin_0_countries.shp"

# ─────────────────── Cartography / pipeline ───────────────────
EPC_COL   = "CURRENT_ENERGY_RATING"
EPC_ORDER = list("ABCDEFG"); EPC_ALL = EPC_ORDER + ["UNK"]

EPC_COLOURS = {"A":"#67c36b","B":"#89d07d","C":"#c8e37c","D":"#f5d36f",
               "E":"#f29d5c","F":"#e16656","G":"#c13b3b","UNK":"#bdbdbd"}
FIG_BG="#ffffff"; AX_BG="#ffffff"
EDGE="#232323"; TEXT="#111111"; GRID_CLR="#666666"

# Thinning / visibility
CELL_SIZE_M  = 800.0
MAX_PER_CELL = 10
SEED         = 42
JITTER_M     = 0.0
USE_SJOIN    = True

# Boost visible points (≈ density multiplier)
THIN_DENSITY_FACTOR = 2.0  # 1.0 = base thinning; 2.0 shows ~2× points

# Optional density underlay behind dots: "none" or "hexbin"
DENSITY_LAYER   = "none"
HXBINS_PER_SIDE = 65
HXBIN_ALPHA     = 0.35

# Layout (A4 landscape)
WSPACE      = 0.03
PAD_FRAC    = 0.015
TITLE_BAND  = 0.09
BOTTOM_BAND = 0.20
WIDTH_RATIOS = [1, 1]

# Belfast slightly smaller (extra pad around its extent)
CITY_EXTRA_PAD = {"london": 0.000, "belfast": 0.045}

# Points
DOT_SIZE = 2.6
ALPHA    = 0.90

# Titles
TITLE_LON = "Greater London (Pilot Area)"
SUB_LON   = "Data: EPC points • EO stack available (not shown)"
TITLE_BEL = "Belfast (Transfer Area)"
SUB_BEL   = "Data: EPC points • EO stack pending"

# Ornaments
NORTH_ARROW_ON_LEFT = True
SCALEBAR_KM_LONDON  = None
SCALEBAR_KM_BELFAST = None

# Graticule
GRATICULE_ON        = True
GRAT_ALPHA          = 0.35
GRAT_LW             = 0.7
GRAT_STYLE          = (0, (1.5, 2.5))
GRAT_LABELS         = True
GRAT_LABEL_SIZE     = 9.0
GRAT_LABEL_OUTLINE  = pe.withStroke(linewidth=1.2, foreground="white")
MAX_LONG_LABELS     = 6
MAX_LAT_LABELS      = 6
GRAT_LON_SIDES      = ("top",)   # lon labels only on top
GRAT_LAT_SIDES      = ("left",)  # lat labels only on left

# Inset region + labels (CLEAN)
UKIE_XLIM = (-11, 3)
UKIE_YLIM = (49, 60)
INSET_FACE       = "#f3f3f3"
INSET_COAST_EDGE = "#101010"
INSET_COAST_LW   = 1.2
INSET_FILL       = "#d0d0d0"
INSET_DRAW_ADMIN1 = False     # optional thin admin-1 lines
INSET_LABELS      = True
CITY_DOT_OUTLINE  = True      # white outline around red city dot

# ─────────────────────────── Utilities ───────────────────────────
def read_any(path, layer=None, crs=None):
    gdf = gpd.read_file(path, layer=layer)
    if crs: gdf = gdf.to_crs(crs)
    return gdf

def to_wgs84(gdf):
    return gdf.set_crs(4326) if gdf.crs is None else gdf.to_crs(4326)

def guess_xy_cols(df):
    import re
    rx_x = re.compile(r"(?:^|_)(lon|long|longitude|x|east|easting)\b", re.I)
    rx_y = re.compile(r"(?:^|_)(lat|latitude|y|north|northing)\b", re.I)
    x = next((c for c in df.columns if rx_x.search(str(c))), None)
    y = next((c for c in df.columns if rx_y.search(str(c))), None)
    return x, y

def numeric_to_letter(score):
    try:
        s = float(score)
    except Exception:
        return "UNK"
    if s>=92:return"A"
    if s>=81:return"B"
    if s>=69:return"C"
    if s>=55:return"D"
    if s>=39:return"E"
    if s>=21:return"F"
    if s>0 :return"G"
    return "UNK"

def normalise_epc(df):
    cols = {c.upper(): c for c in df.columns}
    out = df.copy()
    if EPC_COL in out.columns:
        r = out[EPC_COL].astype(str).str.strip().str.upper().str[0]
    else:
        letter_col = next((v for k,v in cols.items() if "RATING" in k), None)
        if letter_col:
            r = out[letter_col].astype(str).str.strip().str.upper().str[0]
        else:
            num_col = next((cols[k] for k in [
                "CURRENT_ENERGY_EFFICIENCY","ENERGY_EFFICIENCY_CURRENT",
                "CURRENT_ENERGY_EFFICIENCY_SCORE"
            ] if k in cols), None)
            r = out[num_col].apply(numeric_to_letter) if num_col is not None \
                else pd.Series(["UNK"]*len(out), index=out.index)
    out[EPC_COL] = r.where(r.isin(EPC_ORDER), "UNK")
    return out

def ensure_points(gdf):
    if gdf.empty: return gdf
    g = gdf.loc[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    try:
        g = g.explode(index_parts=False, ignore_index=True)
    except TypeError:
        g = g.explode(); g.reset_index(drop=True, inplace=True)
    non_pt = g.geom_type.str.lower() != "point"
    if non_pt.any():
        g.loc[non_pt, "geometry"] = g.loc[non_pt, "geometry"].apply(lambda geom: geom.representative_point())
    return g

def thin_points_grid(gdf, cellsize, max_per_cell, seed):
    if gdf.empty: return gdf
    if not gdf.crs or gdf.crs.is_geographic:
        raise ValueError("Projected CRS in metres required.")
    xs = gdf.geometry.x.values; ys = gdf.geometry.y.values
    x0 = np.floor(xs.min()/cellsize).astype(int)
    y0 = np.floor(ys.min()/cellsize).astype(int)
    ix = (np.floor(xs/cellsize).astype(int)-x0).astype(np.int64)
    iy = (np.floor(ys/cellsize).astype(int)-y0).astype(np.int64)
    g = gdf.copy(); g["_cell"] = ix.astype(str)+"_"+iy.astype(str)
    rng = np.random.default_rng(seed); keep=[]
    for _, idx in g.groupby("_cell").indices.items():
        ids = np.fromiter(idx, dtype=int)
        keep.extend(ids.tolist() if ids.size<=max_per_cell
                    else rng.choice(ids, size=max_per_cell, replace=False).tolist())
    return g.iloc[keep].drop(columns=["_cell"])

def clip_safe(points, boundary, use_sjoin=True):
    try:
        if use_sjoin:
            boundary = boundary[["geometry"]].copy(); boundary["__one"]=1
            j = gpd.sjoin(points, boundary, predicate="within", how="inner")
            return j.drop(columns=[c for c in ("__one","index_right") if c in j.columns])
        b = boundary.copy(); b["geometry"] = b.buffer(0)
        return gpd.overlay(points, b[["geometry"]], how="intersection")
    except Exception:
        b = boundary.copy(); b["geometry"] = b.buffer(0)
        return gpd.overlay(points, b[["geometry"]], how="intersection")

def maybe_jitter_points(pts, jitter_m, seed=SEED):
    if jitter_m and jitter_m>0:
        rngx=np.random.default_rng(seed); rngy=np.random.default_rng(seed+1)
        x=pts.geometry.x.values + rngx.normal(0,jitter_m,len(pts))
        y=pts.geometry.y.values + rngy.normal(0,jitter_m,len(pts))
        return gpd.GeoDataFrame(pts.drop(columns=["geometry"]),
                                geometry=gpd.points_from_xy(x,y,crs=pts.crs))
    return pts

def rating_counts(pts):
    out={k:int((pts[EPC_COL]==k).sum()) for k in EPC_ORDER}
    out["UNK"]=int((pts[EPC_COL]=="UNK").sum()); out["_total"]=int(len(pts))
    return out

def proportional_target_counts(counts_dict, N):
    tot = max(int(counts_dict.get("_total", 0)), 1)
    wanted, frac = {}, {}; base_sum = 0
    for k in EPC_ALL:
        val = (counts_dict.get(k, 0) / tot) * N
        base = int(math.floor(val))
        wanted[k]=base; frac[k]=val-base; base_sum+=base
    R = N - base_sum
    if R>0:
        for k in sorted(EPC_ALL, key=lambda x: frac[x], reverse=True):
            if R==0: break
            wanted[k]+=1; R-=1
    return wanted

def stratified_sample(thin_gdf, target_by_class, seed=SEED):
    rng = np.random.default_rng(seed)
    chosen = []; chosen_set=set()
    for k in EPC_ALL:
        need = target_by_class.get(k, 0)
        avail = thin_gdf.index[thin_gdf[EPC_COL]==k].to_numpy()
        take = min(len(avail), need)
        if take>0:
            picks = rng.choice(avail, size=take, replace=False).tolist()
            chosen.extend(picks); chosen_set.update(picks)
    deficit = sum(target_by_class.get(k,0) for k in EPC_ALL) - len(chosen)
    if deficit>0:
        donors=[]
        for k in EPC_ALL:
            avail = thin_gdf.index[thin_gdf[EPC_COL]==k].to_numpy()
            spare = len([i for i in avail if i not in chosen_set])
            if spare>0: donors.append((k, spare, avail))
        donors.sort(key=lambda t: t[1], reverse=True)
        for _, _, avail in donors:
            if deficit<=0: break
            pool = [i for i in avail if i not in chosen_set]
            add = min(len(pool), deficit)
            if add>0:
                picks = rng.choice(pool, size=add, replace=False).tolist()
                chosen.extend(picks); chosen_set.update(picks)
                deficit -= add
    return thin_gdf.loc[chosen].copy()

def choose_scalebar_km(ax, target_frac=0.18):
    xmin, xmax = ax.get_xlim(); width_m = xmax - xmin
    desired = width_m * target_frac / 1000.0
    nice = [0.2, 0.5, 1, 2, 3, 5, 10, 20, 30]
    cand = [v for v in nice if v <= desired]
    return cand[-1] if cand else nice[0]

def fmt_lon(lon, dec=2): return f"{abs(lon):.{dec}f}°{'E' if lon>=0 else 'W'}"
def fmt_lat(lat, dec=2): return f"{abs(lat):.{dec}f}°{'N' if lat>=0 else 'S'}"

def north_arrow(ax, x=0.05, y=0.90, size=11):
    ax.annotate("", xy=(x, y), xytext=(x, y-0.06),
                xycoords="axes fraction", textcoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>", linewidth=1.2, color=TEXT))
    ax.text(x, y, "N", transform=ax.transAxes, ha="center", va="center",
            fontsize=size, color=TEXT, path_effects=[GRAT_LABEL_OUTLINE])

# ───────── scalebar with *figure*-aligned y (perfect cross-panel line) ─────────
def add_scalebar_segmented(ax, total_km=None, segments=2,
                           x_left_frac=0.05, fig=None, y_fig=None, y_axes_frac=0.08):
    if total_km is None: total_km = choose_scalebar_km(ax)
    Lm = total_km * 1000.0
    seg = Lm / segments
    xlim = ax.get_xlim()
    x_left = xlim[0] + x_left_frac * (xlim[1] - xlim[0])

    if fig is not None and y_fig is not None:
        T = _btf(ax.transData, fig.transFigure)
        pos = ax.get_position()
        dy_tick = 0.01 * pos.height
        dy_lbl  = 0.015 * pos.height
        y      = y_fig
        y_low  = y - dy_tick
        y_high = y + dy_tick
        y_lbl  = y + dy_lbl
    else:
        T = _btf(ax.transData, ax.transAxes)
        y = y_axes_frac
        y_low  = y - 0.01
        y_high = y + 0.01
        y_lbl  = y + 0.015

    # segments (clip_off so they don't get chopped)
    for i in range(segments):
        x1 = x_left + i*seg
        x2 = x1 + seg
        ax.plot([x1, x2], [y, y], transform=T, color=TEXT, lw=2.5,
                solid_capstyle="butt", zorder=6, clip_on=False)
        ax.plot([x1, x1], [y_low, y_high], transform=T, color=TEXT, lw=1.0, zorder=6, clip_on=False)
    ax.plot([x_left+Lm, x_left+Lm], [y_low, y_high], transform=T, color=TEXT, lw=1.0, zorder=6, clip_on=False)

    ax.text(x_left + Lm/2, y_lbl, f"{int(total_km) if total_km>=1 else total_km} km",
            transform=T, ha="center", va="bottom", color=TEXT, fontsize=8,
            path_effects=[GRAT_LABEL_OUTLINE], zorder=7, clip_on=False)

# ─────────── Helpers for inset data (no fragile bool masks) ───────────
def _clip_to_bbox(g, xmin, xmax, ymin, ymax):
    bbox = gpd.GeoDataFrame(geometry=[shp_box(xmin, ymin, xmax, ymax)], crs=4326)
    try:
        return g.overlay(bbox, how="intersection")
    except Exception:
        return g.loc[g.geometry.intersects(bbox.iloc[0].geometry)]

def _try_local_uk_ie():
    if UK_IE_LOCATOR_PATH and os.path.exists(UK_IE_LOCATOR_PATH):
        try:
            g = gpd.read_file(UK_IE_LOCATOR_PATH)
        except Exception:
            g = gpd.read_file(UK_IE_LOCATOR_PATH, engine="pyogrio")
        g = g.to_crs(4326) if g.crs else g.set_crs(4326)
        return g, "local"
    return None, None

def _try_geopandas_lowres():
    try:
        p = gpd.datasets.get_path("naturalearth_lowres")
        world = gpd.read_file(p).to_crs(4326)
        return world, "geopandas-lowres"
    except Exception:
        return None, None

def _try_cartopy_admin1_lines():
    # Optional; draw if available
    try:
        from cartopy.io.shapereader import natural_earth
        shp = natural_earth(resolution="110m", category="cultural",
                            name="admin_1_states_provinces_lines")
        g = gpd.read_file(shp).to_crs(4326)
        mask = pd.Series(False, index=g.index)
        for col in [c for c in ["adm0_a3","geonunit","admin"] if c in g.columns]:
            if col == "adm0_a3":
                mask |= g[col].astype(str).isin(["GBR","IRL"])
            else:
                mask |= g[col].astype(str).isin(["United Kingdom","Ireland","UK","U.K."])
        sub = g.loc[mask, ["geometry"]].copy()
        return _clip_to_bbox(sub, *UKIE_XLIM, *UKIE_YLIM), "cartopy-admin1"
    except Exception:
        return None, None

def load_uk_ie_outline():
    """
    Robustly return polygons for UK + Ireland (WGS84), clipped to the inset window.
    Never returns a bare boolean mask; avoids 'bool is not iterable' issues.
    """
    for loader in (_try_local_uk_ie, _try_geopandas_lowres):
        g, label = loader()
        if g is None: 
            continue
        g = g.to_crs(4326) if g.crs else g.set_crs(4326)

        # Build a safe boolean Series mask across plausible columns
        cols = [c for c in ["name","admin","sovereignt","adm0_a3","geonunit"] if c in g.columns]
        if cols:
            m = pd.Series(False, index=g.index)
            for col in cols:
                if col == "adm0_a3":
                    m |= g[col].astype(str).isin(["GBR","IRL"])
                else:
                    m |= g[col].astype(str).isin(["United Kingdom","Ireland","UK","U.K."])
            sub = g.loc[m, ["geometry"]].copy()
            if sub.empty:
                sub = g[["geometry"]].copy()  # fallback to full layer
        else:
            sub = g[["geometry"]].copy()

        # explode and clip
        try:
            sub = sub.explode(index_parts=False, ignore_index=True)
        except TypeError:
            sub = sub.explode(); sub.reset_index(drop=True, inplace=True)

        sub = _clip_to_bbox(sub, *UKIE_XLIM, *UKIE_YLIM)
        if not sub.empty:
            return sub, label

    return None, "fallback"

# ─────────── Inset labels (halo only, no boxes) ───────────
def _label(ax, txt, xy, big=True):
    ax.text(*xy, txt, ha="center", va="center",
            fontsize=(8 if big else 7),
            color=("#111111" if big else "#444444"),
            path_effects=[pe.withStroke(linewidth=2.4, foreground="#ffffff")],
            zorder=5, clip_on=False)

def _annotate_inset_labels(ax):
    if not INSET_LABELS: return
    # Country/region abbrevs
    for t,(x,y) in {
        "SCO": (-4.2, 57.1), "ENG": (-1.6, 52.5),
        "WLS": (-3.6, 52.2), "NI": (-6.6, 54.8), "IE": (-8.0, 53.3)
    }.items():
        _label(ax, t, (x,y), big=True)
    # Seas
    for t,(x,y) in {
        "NORTH SEA": (1.0, 57.0), "IRISH SEA": (-5.0, 53.5),
        "ENGLISH CHANNEL": (-1.3, 50.2), "CELTIC SEA": (-7.6, 50.8),
        "ATLANTIC OCEAN": (-10.1, 53.0)
    }.items():
        _label(ax, t, (x,y), big=False)

def locator_inset(ax, boundary_proj, loc_box=(0.72, 0.06, 0.24, 0.24)):
    inset = ax.inset_axes(loc_box, zorder=4)
    inset.set_facecolor(INSET_FACE)

    ukie, src0 = load_uk_ie_outline()
    if ukie is not None and not ukie.empty:
        # fill + stroke to avoid the “mystery boxes” look
        ukie.plot(ax=inset, facecolor=INSET_FILL, edgecolor=INSET_COAST_EDGE,
                  linewidth=INSET_COAST_LW, zorder=2)
    else:
        # last resort: show a simple frame so it’s never blank
        gpd.GeoSeries([shp_box(*UKIE_XLIM, *UKIE_YLIM)], crs=4326).boundary.plot(
            ax=inset, color=INSET_COAST_EDGE, linewidth=INSET_COAST_LW, zorder=2)

    # Optional admin1 lines (if cartopy data available)
    if INSET_DRAW_ADMIN1:
        a1, src1 = _try_cartopy_admin1_lines()
        if a1 is not None and not a1.empty:
            a1.plot(ax=inset, color=INSET_COAST_EDGE, linewidth=0.7, alpha=0.9, zorder=2.4)

    inset.set_xlim(*UKIE_XLIM); inset.set_ylim(*UKIE_YLIM)
    _annotate_inset_labels(inset)

    # City marker with white outline
    c = boundary_proj.to_crs(4326).centroid.iloc[0]
    inset.scatter([c.x], [c.y], s=40, c="#d33",
                  edgecolors=("white" if CITY_DOT_OUTLINE else "none"),
                  linewidths=(1.0 if CITY_DOT_OUTLINE else 0),
                  zorder=6, clip_on=False)

    inset.set_xticks([]); inset.set_yticks([])
    for sp in inset.spines.values(): sp.set_edgecolor(INSET_COAST_EDGE)

    try:
        print(f"[inset] background source = {src0}; admin1_on={INSET_DRAW_ADMIN1}")
    except Exception:
        pass

# ─────────────────────────── Graticule ───────────────────────────
def nice_step(span, max_labels=5):
    if span <= 0: return 1.0
    raw = span / max(2, max_labels)
    nice = np.array([0.05, 0.1, 0.2, 0.5, 1.0, 2.0])
    return float(nice[np.searchsorted(nice, raw)])

def label_decimals(step):
    if step < 0.11: return 2
    if step < 0.55: return 1
    return 0

def add_graticule(ax, boundary_proj, target_crs,
                  alpha=GRAT_ALPHA, lw=GRAT_LW, style=GRAT_STYLE, labels=GRAT_LABELS):
    b_wgs = boundary_proj.to_crs(4326)
    xmin, ymin, xmax, ymax = b_wgs.total_bounds
    lon_step = nice_step(xmax - xmin, max_labels=MAX_LONG_LABELS)
    lat_step = nice_step(ymax - ymin, max_labels=MAX_LAT_LABELS)
    dlon = label_decimals(lon_step); dlat = label_decimals(lat_step)

    lons = np.arange(math.floor(xmin/lon_step)*lon_step,
                     math.ceil(xmax/lon_step)*lon_step + 0.5*lon_step, lon_step)
    lats = np.arange(math.floor(ymin/lat_step)*lat_step,
                     math.ceil(ymax/lat_step)*lat_step + 0.5*lat_step, lat_step)

    geoms = []
    for L in lons: geoms.append(LineString([(L, ymin-1), (L, ymax+1)]))
    for P in lats: geoms.append(LineString([(xmin-1, P), (xmax+1, P)]))
    grat = gpd.GeoDataFrame(geometry=geoms, crs=4326).to_crs(target_crs)
    grat.plot(ax=ax, color=GRID_CLR, linewidth=lw, alpha=alpha,
              linestyle=style, zorder=1.05)

    if not labels: return
    x0, x1 = ax.get_xlim(); y0, y1 = ax.get_ylim()
    xpad = 0.006*(x1-x0); ypad = 0.012*(y1-y0)

    # top lon labels only
    lons_core = lons[1:-1] if len(lons) > 2 else lons
    if "top" in GRAT_LON_SIDES:
        for L in lons_core:
            seg = gpd.GeoSeries([LineString([(L, ymin-1), (L, ymin-0.8)])],
                                crs=4326).to_crs(target_crs).geometry.iloc[0]
            x_here = seg.coords[1][0]
            ax.text(x_here, y1 - ypad, fmt_lon(L, dlon), ha='center', va='top',
                    fontsize=GRAT_LABEL_SIZE, color=GRID_CLR, alpha=alpha,
                    path_effects=[GRAT_LABEL_OUTLINE], zorder=3)

    # left lat labels only
    lats_core = lats[1:-1] if len(lats) > 2 else lats
    if "left" in GRAT_LAT_SIDES:
        for P in lats_core:
            seg = gpd.GeoSeries([LineString([(xmin-1, P), (xmin-0.8, P)])],
                                crs=4326).to_crs(target_crs).geometry.iloc[0]
            y_here = seg.coords[1][1]
            ax.text(x0 + xpad, y_here, fmt_lat(P, dlat), ha='left', va='center',
                    fontsize=GRAT_LABEL_SIZE, color=GRID_CLR, alpha=alpha,
                    path_effects=[GRAT_LABEL_OUTLINE], zorder=3)

# ─────────────────────────── Loaders ───────────────────────────
def load_london_points_wgs84():
    gdf = read_any(LONDON_EPC)
    gdf = gdf.set_crs(4326) if gdf.crs is None else gdf.to_crs(4326)
    return normalise_epc(ensure_points(gdf))

def load_belfast_points_wgs84():
    if os.path.exists(BELFAST_EPC_CSV):
        df = pd.read_csv(BELFAST_EPC_CSV)
        xcol, ycol = guess_xy_cols(df)
        if xcol and ycol:
            gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[xcol], df[ycol]), crs=4326)
            return normalise_epc(gdf)
    if os.path.exists(BELFAST_EPC_POLYS):
        polys = read_any(BELFAST_EPC_POLYS)
        pts = ensure_points(to_wgs84(polys))
        return normalise_epc(pts)
    raise FileNotFoundError("Belfast EPC points not found.")

# ───────────────────────── Panel plotting ─────────────────────────
def _padded_extent(bounds, pad_frac):
    x0,y0,x1,y1 = bounds
    dx=(x1-x0)*pad_frac; dy=(y1-y0)*pad_frac
    return (x0-dx, y0-dy, x1+dx, y1+dy)

def plot_panel(ax, boundary_proj, pts_to_plot, target_crs,
               fig=None, scalebar_y_fig=None,
               dot_size=DOT_SIZE, draw_north=False,
               scalebar_km=None, locator_pos=(0.72, 0.06, 0.24, 0.24),
               extra_pad_frac=0.0):
    ax.set_facecolor(AX_BG)
    x0p, y0p, x1p, y1p = _padded_extent(boundary_proj.total_bounds, PAD_FRAC + extra_pad_frac)
    ax.set_xlim(x0p, x1p); ax.set_ylim(y0p, y1p)
    ax.set_axis_off()

    if GRATICULE_ON:
        add_graticule(ax, boundary_proj, target_crs)

    if DENSITY_LAYER == "hexbin" and not pts_to_plot.empty:
        ax.hexbin(pts_to_plot.geometry.x.values, pts_to_plot.geometry.y.values,
                  gridsize=HXBINS_PER_SIDE, mincnt=1, linewidths=0,
                  cmap="Greys", alpha=HXBIN_ALPHA, zorder=1.4)

    boundary_proj.boundary.plot(ax=ax, edgecolor=EDGE, linewidth=0.95, zorder=1.6)

    for r in EPC_ORDER:
        sub = pts_to_plot.loc[pts_to_plot[EPC_COL]==r]
        if not sub.empty:
            ax.scatter(sub.geometry.x, sub.geometry.y, s=dot_size,
                       c=EPC_COLOURS[r], marker="o", linewidths=0,
                       alpha=ALPHA, rasterized=True, zorder=2.2)
    unk = pts_to_plot.loc[pts_to_plot[EPC_COL]=="UNK"]
    if not unk.empty:
        ax.scatter(unk.geometry.x, unk.geometry.y, s=dot_size*0.8,
                   c=EPC_COLOURS["UNK"], marker="o", linewidths=0,
                   alpha=0.6, rasterized=True, zorder=2.2)

    if draw_north:
        north_arrow(ax)

    add_scalebar_segmented(ax, total_km=scalebar_km,
                           fig=fig, y_fig=scalebar_y_fig,
                           x_left_frac=0.05)

    locator_inset(ax, boundary_proj, loc_box=locator_pos)

# ───────────────────────────── Main ─────────────────────────────
def main():
    os.makedirs(OUTDIR, exist_ok=True)

    lon_pts_w = load_london_points_wgs84()
    bel_pts_w = load_belfast_points_wgs84()

    lon_bound = read_any(LONDON_BOUNDARY, crs=LONDON_CRS)
    bel_bound = read_any(BELFAST_BOUNDARY, crs=BELFAST_CRS)

    lon_pts = ensure_points(lon_pts_w.to_crs(LONDON_CRS))
    bel_pts = ensure_points(bel_pts_w.to_crs(BELFAST_CRS))

    lon_clip = ensure_points(clip_safe(lon_pts, lon_bound, use_sjoin=USE_SJOIN))
    bel_clip = ensure_points(clip_safe(bel_pts, bel_bound, use_sjoin=USE_SJOIN))

    lon_counts = rating_counts(lon_clip)
    bel_counts = rating_counts(bel_clip)

    # Relax thinning via density factor
    cell_eff = CELL_SIZE_M / math.sqrt(max(THIN_DENSITY_FACTOR, 1.0))
    max_eff  = max(1, int(round(MAX_PER_CELL * max(THIN_DENSITY_FACTOR, 1.0))))

    lon_thin = maybe_jitter_points(thin_points_grid(lon_clip, cell_eff, max_eff, SEED), JITTER_M, seed=SEED)
    bel_thin = maybe_jitter_points(thin_points_grid(bel_clip, cell_eff, max_eff, SEED), JITTER_M, seed=SEED)

    # Equal TOTAL points in both panels (preserving grade proportions)
    N_equal = min(len(lon_thin), len(bel_thin))
    lon_targets = proportional_target_counts(lon_counts, N_equal)
    bel_targets = proportional_target_counts(bel_counts, N_equal)
    lon_sample = stratified_sample(lon_thin, lon_targets, seed=SEED)
    bel_sample = stratified_sample(bel_thin, bel_targets, seed=SEED)

    fig = plt.figure(figsize=(11.69, 8.27), facecolor=FIG_BG)
    from matplotlib.gridspec import GridSpec
    gs = GridSpec(
        nrows=3, ncols=2,
        height_ratios=[TITLE_BAND, 1.0 - (TITLE_BAND + BOTTOM_BAND), BOTTOM_BAND],
        width_ratios=WIDTH_RATIOS,
        left=0.05, right=0.97, bottom=0.07, top=0.95, wspace=WSPACE, hspace=0.06
    )

    # Titles
    ax_t1 = fig.add_subplot(gs[0,0]); ax_t2 = fig.add_subplot(gs[0,1])
    for a in (ax_t1, ax_t2): a.axis("off")
    ax_t1.text(0.5, 0.72, TITLE_LON, ha="center", va="center", fontsize=16, color=TEXT, weight="bold")
    ax_t1.text(0.5, 0.25, SUB_LON,   ha="center", va="center", fontsize=9,  color=TEXT)
    ax_t2.text(0.5, 0.72, TITLE_BEL, ha="center", va="center", fontsize=16, color=TEXT, weight="bold")
    ax_t2.text(0.5, 0.25, SUB_BEL,   ha="center", va="center", fontsize=9,  color=TEXT)

    # Panels
    ax_lon = fig.add_subplot(gs[1,0])
    ax_bel = fig.add_subplot(gs[1,1])

    # Single global y for scalebars in figure coords (use left panel as reference)
    pos = ax_lon.get_position()
    y_bar_fig = pos.y0 + 0.085 * pos.height  # tweak up/down if desired

    plot_panel(ax_lon, lon_bound, lon_sample, LONDON_CRS,
               fig=fig, scalebar_y_fig=y_bar_fig,
               dot_size=DOT_SIZE, draw_north=NORTH_ARROW_ON_LEFT,
               scalebar_km=SCALEBAR_KM_LONDON,
               locator_pos=(0.72, 0.06, 0.24, 0.24),
               extra_pad_frac=CITY_EXTRA_PAD["london"])

    plot_panel(ax_bel, bel_bound, bel_sample, BELFAST_CRS,
               fig=fig, scalebar_y_fig=y_bar_fig,
               dot_size=DOT_SIZE, draw_north=False,
               scalebar_km=SCALEBAR_KM_BELFAST,
               locator_pos=(0.72, 0.06, 0.24, 0.24),
               extra_pad_frac=CITY_EXTRA_PAD["belfast"])

    # Legend + footer
    ax_leg = fig.add_subplot(gs[2,:]); ax_leg.axis("off")
    handles = [Patch(facecolor=EPC_COLOURS[k], edgecolor='none', label=k) for k in EPC_ORDER]
    ax_leg.legend(handles=handles, ncol=7, loc='center',
                  bbox_to_anchor=(0.5, 0.80), frameon=False, fontsize=9,
                  columnspacing=1.0, handlelength=0.9, handletextpad=0.35,
                  title="EPC grade", title_fontsize=9)

    foot1 = ("Projections: London—OSGB 1936 / British National Grid (EPSG:27700); "
             "Belfast—Irish Transverse Mercator (EPSG:2157). "
             "Graticules in WGS84 (EPSG:4326). Panels have equal visual width; "
             "scalebars show true distances and share a common figure y.")
    foot2 = (f"Each city displays N={len(lon_sample)} points (equal totals). "
             f"Sampling is stratified by EPC grade to match each city's original distribution. "
             f"Thinning ≲{max_eff} points per ~{cell_eff:.0f} m cell (seed {SEED}); "
             "dots are not proportional to totals."
             + (" Optional hexbin shows relative density only." if DENSITY_LAYER=='hexbin' else ""))

    def _wrap(text, width=110): return "\n".join(textwrap.wrap(text, width))
    ax_leg.text(0.5, 0.42, _wrap(foot1), ha='center', va='center', color=TEXT, fontsize=8, transform=ax_leg.transAxes)
    ax_leg.text(0.5, 0.16, _wrap(foot2), ha='center', va='center', color="#222222", fontsize=8, transform=ax_leg.transAxes)

    # Save
    os.makedirs(OUTDIR, exist_ok=True)
    out_png = os.path.join(OUTDIR, "Fig1_StudyAreas_side_by_side.png")
    out_svg = os.path.join(OUTDIR, "Fig1_StudyAreas_side_by_side.svg")
    fig.savefig(out_png, dpi=300, facecolor=FIG_BG)
    fig.savefig(out_svg, dpi=300, facecolor=FIG_BG)

    manifest = {
        "figure": "Fig1_StudyAreas_side_by_side",
        "paths": {
            "london_boundary": LONDON_BOUNDARY, "london_epc": LONDON_EPC,
            "belfast_boundary": BELFAST_BOUNDARY, "belfast_epc_csv": BELFAST_EPC_CSV,
            "belfast_epc_polys": BELFAST_EPC_POLYS, "uk_ie_locator_path": UK_IE_LOCATOR_PATH
        },
        "crs": {"london": LONDON_CRS, "belfast": BELFAST_CRS},
        "thinning": {
            "cellsize_base_m": CELL_SIZE_M, "max_per_cell_base": MAX_PER_CELL,
            "density_factor": THIN_DENSITY_FACTOR, "effective_cell_m": cell_eff,
            "effective_max_per_cell": max_eff, "seed": SEED, "jitter_m": JITTER_M
        },
        "equal_points_per_city": len(lon_sample),
        "density_layer": DENSITY_LAYER,
        "notes": [
            "Inset polygons from GeoPandas Natural Earth (or local path).",
            "Halo labels only; optional admin1 lines if Cartopy is present.",
            "Scalebars use x=data, y=figure with clip_on=False for perfect alignment."
        ],
        "outputs": {"png": out_png, "svg": out_svg}
    }
    with open(os.path.join(OUTDIR, "Fig1_StudyAreas_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"✓ Saved {out_png}\n✓ Saved {out_svg}")

# ------------------------------------------------------------------
if __name__ == "__main__":
    main()
