# -*- coding: utf-8 -*-
"""
study_area_maps_final_projection_inset.py

• Robust UK+IE inset using a true map projection (no manual scaling):
  default = Lambert Conformal Conic centered on the UK; alternatively use EPSG:3035 (LAEA Europe).
• Minimal inset labels: only SCO, ENG, WLS, NI, IE (no seas).
• Figure-aligned, perfectly level scalebars across main panels.
• Equal visual widths; equal-N stratified sampling per city; optional hexbin underlay.

Edit only the I/O paths and (optionally) the INSET_CRS_CHOICE block.
"""

import os, json, warnings, math, textwrap
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import box as shp_box, LineString, Point
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import matplotlib.patheffects as pe
from matplotlib.transforms import blended_transform_factory as _btf
from pyproj import CRS  # for a real inset projection

# ───────────────────────── I/O (EDIT THESE) ─────────────────────────
OUTDIR = r"D:\OneDrive - Ulster University\PhD\Maps"

# London
LONDON_BOUNDARY = r"D:\OneDrive - Ulster University\PhD\data\London\SHP\london.shp"
LONDON_EPC      = r"D:\OneDrive - Ulster University\PhD\data\London\london_epc_points.geojson"
LONDON_CRS      = "EPSG:27700"     # OSGB36 / British National Grid

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

# Density underlay
DENSITY_LAYER   = "none"    # "none" or "hexbin"
HXBINS_PER_SIDE = 65
HXBIN_ALPHA     = 0.35

# Layout (A4 landscape)
WSPACE      = 0.03
PAD_FRAC    = 0.015
TITLE_BAND  = 0.09
BOTTOM_BAND = 0.20
WIDTH_RATIOS = [1, 1]
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
GRAT_LON_SIDES      = ("top",)
GRAT_LAT_SIDES      = ("left",)

# ── Inset window in geographic coords for clipping source data
UKIE_XLIM = (-11, 3)
UKIE_YLIM = (49, 60)

# ── Inset rendering options
INSET_FACE       = "#f3f3f3"
INSET_COAST_EDGE = "#101010"
INSET_COAST_LW   = 1.2
INSET_FILL       = "#d0d0d0"
INSET_DRAW_ADMIN1 = False
INSET_LABELS      = True
INSET_REGION_LABEL_SIZE = 8

# ── Choose a real map projection for the inset (no manual scaling)
# Option A (default): UK-centric Lambert Conformal Conic (looks pleasantly wider)
INSET_CRS_CHOICE = CRS.from_proj4(
    "+proj=lcc +lat_1=49 +lat_2=61 +lat_0=54.5 +lon_0=-3 "
    "+x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
)
# Option B: comment above and un-comment below for LAEA Europe (EPSG:3035)
# INSET_CRS_CHOICE = CRS.from_epsg(3035)

# Minimal region labels (lon, lat) — tuned to avoid ENG↔WLS overlap
INSET_REGION_LABELS_LL = {
    "SCO": (-4.2, 57.2),
    "ENG": ( 0.6, 52.7),   # slightly east
    "WLS": (-4.9, 51.9),   # SW of ENG
    "NI" : (-6.3, 54.8),
    "IE" : (-8.2, 53.2),
}

# ─────────────────────────── Utilities ───────────────────────────
def read_any(path, layer=None, crs=None):
    try:
        gdf = gpd.read_file(path, layer=layer, engine="pyogrio")
    except Exception:
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

# ─────────── Inset helpers (load & project) ───────────
def _clip_to_bbox(g, xmin, xmax, ymin, ymax):
    bbox = gpd.GeoDataFrame(geometry=[shp_box(xmin, ymin, xmax, ymax)], crs=4326)
    try:
        return g.overlay(bbox, how="intersection")
    except Exception:
        return g.loc[g.geometry.intersects(bbox.iloc[0].geometry)]

def _mask_uk_ie(g):
    cols = [c for c in ["name","admin","sovereignt","adm0_a3","geonunit"] if c in g.columns]
    if not cols:
        return pd.Series(True, index=g.index)
    m = pd.Series(False, index=g.index)
    for col in cols:
        s = g[col].astype(str)
        if col == "adm0_a3":
            m |= s.isin(["GBR","IRL","UK"])
        else:
            m |= s.isin(["United Kingdom","Ireland","UK","U.K."])
    return m

def _try_local_admin0():
    if UK_IE_LOCATOR_PATH and os.path.exists(UK_IE_LOCATOR_PATH):
        try:
            g = gpd.read_file(UK_IE_LOCATOR_PATH, engine="pyogrio")
        except Exception:
            g = gpd.read_file(UK_IE_LOCATOR_PATH)
        g = g.to_crs(4326) if g.crs else g.set_crs(4326)
        return g, "local"
    return None, None

def _try_cartopy_admin0():
    try:
        from cartopy.io.shapereader import natural_earth
        shp = natural_earth(resolution="110m", category="cultural", name="admin_0_countries")
        g = gpd.read_file(shp).to_crs(4326)
        return g, "cartopy-admin0"
    except Exception:
        return None, None

def _try_geopandas_lowres():
    try:
        p = gpd.datasets.get_path("naturalearth_lowres")
        g = gpd.read_file(p).to_crs(4326)
        return g, "geopandas-lowres"
    except Exception:
        return None, None

def _try_cartopy_admin1_lines():
    try:
        from cartopy.io.shapereader import natural_earth
        shp = natural_earth(resolution="110m", category="cultural",
                            name="admin_1_states_provinces_lines")
        g = gpd.read_file(shp).to_crs(4326)
        m = _mask_uk_ie(g)
        sub = _clip_to_bbox(g.loc[m, ["geometry"]].copy(), *UKIE_XLIM, *UKIE_YLIM)
        return sub, "cartopy-admin1"
    except Exception:
        return None, None

def load_uk_ie_outline():
    """Return UK+IE polygons (WGS84) clipped to the window."""
    for loader in (_try_local_admin0, _try_cartopy_admin0, _try_geopandas_lowres):
        g, label = loader()
        if g is None: 
            continue
        g = g.to_crs(4326) if g.crs else g.set_crs(4326)
        m = _mask_uk_ie(g)
        sub = g.loc[m, ["geometry"]].copy() if m.any() else g[["geometry"]].copy()
        try:
            sub = sub.explode(index_parts=False, ignore_index=True)
        except TypeError:
            sub = sub.explode(); sub.reset_index(drop=True, inplace=True)
        sub = _clip_to_bbox(sub, *UKIE_XLIM, *UKIE_YLIM)
        if not sub.empty:
            return sub, label
    return None, "fallback"

# ─────────── Minimal inset labels (projected) ───────────
def _annotate_inset_labels(ax, inset_crs):
    if not INSET_LABELS:
        return
    pts_ll = gpd.GeoSeries([Point(xy) for xy in INSET_REGION_LABELS_LL.values()], crs=4326)
    pts_xy = pts_ll.to_crs(inset_crs)
    for (txt, _), (x, y) in zip(INSET_REGION_LABELS_LL.items(), pts_xy.geometry.apply(lambda p: (p.x, p.y))):
        ax.text(x, y, txt, ha="center", va="center",
                fontsize=INSET_REGION_LABEL_SIZE, color="#111111",
                path_effects=[pe.withStroke(linewidth=2.4, foreground="#ffffff")],
                zorder=5, clip_on=False)

# ─────────── Locator inset (projection-based) ───────────
def locator_inset(ax, boundary_proj, loc_box=(0.72, 0.06, 0.24, 0.24), inset_crs=INSET_CRS_CHOICE):
    inset = ax.inset_axes(loc_box, zorder=4)
    inset.set_facecolor(INSET_FACE)

    ukie_4326, src0 = load_uk_ie_outline()

    if ukie_4326 is not None and not ukie_4326.empty:
        ukie_xy = ukie_4326.to_crs(inset_crs)
        ukie_xy.plot(ax=inset, facecolor=INSET_FILL, edgecolor=INSET_COAST_EDGE,
                     linewidth=INSET_COAST_LW, zorder=2)

        # Optional admin1 lines
        if INSET_DRAW_ADMIN1:
            a1_4326, _ = _try_cartopy_admin1_lines()
            if a1_4326 is not None and not a1_4326.empty:
                a1_xy = a1_4326.to_crs(inset_crs)
                a1_xy.plot(ax=inset, color=INSET_COAST_EDGE, linewidth=0.7, alpha=0.9, zorder=2.4)

        # Limits with a small pad
        x0,y0,x1,y1 = ukie_xy.total_bounds
        dx = (x1-x0)*0.04; dy = (y1-y0)*0.04
        inset.set_xlim(x0-dx, x1+dx); inset.set_ylim(y0-dy, y1+dy)
    else:
        # last resort: show a simple frame in geographic degrees (rare)
        gpd.GeoSeries([shp_box(*UKIE_XLIM, *UKIE_YLIM)], crs=4326).boundary.plot(
            ax=inset, color=INSET_COAST_EDGE, linewidth=INSET_COAST_LW, zorder=2)

    # City marker: compute centroid in geographic → project to inset CRS
    c_ll = boundary_proj.to_crs(4326).centroid.iloc[0]
    c_xy = gpd.GeoSeries([Point(c_ll.x, c_ll.y)], crs=4326).to_crs(inset_crs).geometry.iloc[0]
    inset.scatter([c_xy.x], [c_xy.y], s=40, c="#d33", edgecolors="white", linewidths=1.0, zorder=6, clip_on=False)

    _annotate_inset_labels(inset, inset_crs)

    inset.set_xticks([]); inset.set_yticks([])
    for sp in inset.spines.values(): sp.set_edgecolor(INSET_COAST_EDGE)

    try:
        print(f"[inset] source={src0}; crs={inset_crs.to_string()}")
    except Exception:
        pass

# ─────────────────────────── Graticule for main panels ───────────────────────────
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

    # Effective thinning (keep your current density visually similar)
    cell_eff = CELL_SIZE_M
    max_eff  = MAX_PER_CELL

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

    # Shared y for scalebars
    pos = ax_lon.get_position()
    y_bar_fig = pos.y0 + 0.085 * pos.height

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
             "scalebars show true distances and share a common figure y. "
             "Locator inset uses a UK-centric Lambert Conformal Conic projection.")
    foot2 = (f"Each city displays N={len(lon_sample)} points (equal totals). "
             f"Sampling is stratified by EPC grade to match each city's original distribution. "
             f"Thinning ≤{MAX_PER_CELL} points per ~{CELL_SIZE_M:.0f} m cell (seed {SEED}); "
             "dots are not proportional to totals.")

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
        "crs": {"london": LONDON_CRS, "belfast": BELFAST_CRS, "inset": str(INSET_CRS_CHOICE)},
        "thinning": {
            "cellsize_m": CELL_SIZE_M, "max_per_cell": MAX_PER_CELL,
            "seed": SEED, "jitter_m": JITTER_M
        },
        "equal_points_per_city": len(lon_sample),
        "density_layer": DENSITY_LAYER,
        "notes": [
            "Inset polygons from LOCAL→Cartopy admin_0→GeoPandas NE-lowres (first available).",
            "Inset projection is true cartographic (LCC or LAEA), not manual stretching.",
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
