# -*- coding: utf-8 -*-
"""
study_area_maps_v20_equalwidth_locator_visible.py
"""

import os, json, warnings, math
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import box as shp_box, LineString
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.gridspec import GridSpec
import matplotlib.patheffects as pe

# ----------------------------- I/O (EDIT THESE) -----------------------------
OUTDIR = r"D:\OneDrive - Ulster University\PhD\Maps"

# London
LONDON_BOUNDARY = r"D:\OneDrive - Ulster University\PhD\data\London\SHP\london.shp"
LONDON_EPC      = r"D:\OneDrive - Ulster University\PhD\data\London\london_epc_points.geojson"
LONDON_CRS      = "EPSG:27700"  # OSGB 1936 / British National Grid

# Belfast
BELFAST_BOUNDARY  = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-dissolved\belfast-dissolved.shp"
BELFAST_EPC_CSV   = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-epc\gee_epc_2024_points_uid_wgs84.csv"
BELFAST_EPC_POLYS = r"D:\OneDrive - Ulster University\PhD\data\belfast\belfast-epc\gee_epc_2024_polygons_uid_wgs84_shp\gee_epc_2024_polys.shp"
BELFAST_CRS       = "EPSG:2157"  # Irish Transverse Mercator

# --------------------- Cartography / pipeline settings ----------------------
EPC_COL = "CURRENT_ENERGY_RATING"
EPC_ORDER = list("ABCDEFG")
EPC_ALL   = EPC_ORDER + ["UNK"]

EPC_COLOURS = {
    "A":"#67c36b","B":"#89d07d","C":"#c8e37c","D":"#f5d36f",
    "E":"#f29d5c","F":"#e16656","G":"#c13b3b","UNK":"#bdbdbd"
}

FIG_BG = "#ffffff"; AX_BG = "#ffffff"
EDGE = "#232323"; TEXT = "#111111"; GRID_CLR = "#666666"

# Thinning & privacy
CELL_SIZE_M  = 800.0
MAX_PER_CELL = 10
SEED         = 42
JITTER_M     = 0.0
USE_SJOIN    = True

# Layout (A4 landscape)
WSPACE      = 0.03
PAD_FRAC    = 0.015
TITLE_BAND  = 0.09
BOTTOM_BAND = 0.16
WIDTH_RATIOS = [1, 1]  # equal visual width

# Points & titles
DOT_SIZE = 2.6
ALPHA    = 0.90
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

# ------------------------------- Utilities ----------------------------------
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
    try: s=float(score)
    except Exception: return "UNK"
    if s>=92:return"A"
    if s>=81:return"B"
    if s>=69:return"C"
    if s>=55:return"D"
    if s>=39:return"E"
    if s>=21:return"F"
    if s>0:return"G"
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
                "CURRENT_ENERGY_EFFICIENCY_SCORE"] if k in cols), None)
            r = out[num_col].apply(numeric_to_letter) if num_col is not None else \
                pd.Series(["UNK"]*len(out), index=out.index)
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

# -------------------- Equal-N (stratified) helpers --------------------------
def proportional_target_counts(counts_dict, N):
    tot = max(int(counts_dict.get("_total", 0)), 1)
    wanted, frac = {}, {}
    base_sum = 0
    for k in EPC_ALL:
        val = (counts_dict.get(k, 0) / tot) * N
        base = int(math.floor(val)); wanted[k]=base; frac[k]=val-base; base_sum+=base
    R = N - base_sum
    if R>0:
        for k in sorted(EPC_ALL, key=lambda x: frac[x], reverse=True):
            if R==0: break
            wanted[k]+=1; R-=1
    return wanted

def stratified_sample(thin_gdf, target_by_class, seed=SEED):
    rng = np.random.default_rng(seed)
    chosen = []; chosen_set = set()
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

# ------------------------------- Ornaments ----------------------------------
def choose_scalebar_km(ax, target_frac=0.18):
    xmin, xmax = ax.get_xlim(); width_m = xmax - xmin
    desired = width_m * target_frac / 1000.0
    nice = [0.2, 0.5, 1, 2, 3, 5, 10, 20, 30]
    cand = [v for v in nice if v <= desired]
    return cand[-1] if cand else nice[0]

def fmt_lon(lon, dec=2):
    return f"{abs(lon):.{dec}f}°{'E' if lon>=0 else 'W'}"

def fmt_lat(lat, dec=2):
    return f"{abs(lat):.{dec}f}°{'N' if lat>=0 else 'S'}"

def north_arrow(ax, x=0.05, y=0.90, size=11):
    ax.annotate("", xy=(x, y), xytext=(x, y-0.06),
                xycoords="axes fraction", textcoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>", linewidth=1.4, color=TEXT))
    ax.text(x, y, "N", transform=ax.transAxes, ha="center", va="center",
            fontsize=size, color=TEXT, path_effects=[GRAT_LABEL_OUTLINE])

def add_scalebar_segmented(ax, total_km=None, segments=2):
    if total_km is None: total_km = choose_scalebar_km(ax)
    xlim=ax.get_xlim(); ylim=ax.get_ylim()
    x0=xlim[0]+0.05*(xlim[1]-xlim[0]); y=ylim[0]+0.05*(ylim[1]-ylim[0])
    Lm=total_km*1000.0; seg=Lm/segments
    for i in range(segments):
        x1=x0+i*seg; x2=x1+seg
        ax.plot([x1,x2],[y,y], color=TEXT, lw=2.6, solid_capstyle="butt")
        ax.plot([x1,x1],[y-0.01*(ylim[1]-ylim[0]), y+0.01*(ylim[1]-ylim[0])], color=TEXT, lw=1.1)
    ax.plot([x0+Lm,x0+Lm],[y-0.01*(ylim[1]-ylim[0]), y+0.01*(ylim[1]-ylim[0])], color=TEXT, lw=1.1)
    ax.text(x0+Lm/2, y+0.012*(ylim[1]-ylim[0]), f"{int(total_km) if total_km>=1 else total_km} km",
            ha="center", va="bottom", color=TEXT, fontsize=8, path_effects=[GRAT_LABEL_OUTLINE])

# ---- Natural Earth loader + *explicit* UK/IE filter (robust & visible) ----
_WORLD_4326 = None
def _get_world_4326():
    global _WORLD_4326
    if _WORLD_4326 is None:
        try:
            p = gpd.datasets.get_path("naturalearth_lowres")
            _WORLD_4326 = gpd.read_file(p).to_crs(4326)
        except Exception:
            _WORLD_4326 = None
    return _WORLD_4326

def _get_uk_ie():
    world = _get_world_4326()
    if world is None or world.empty:
        return None
    # Filter by country name variants to be safe across NE versions
    name_cols = [c for c in ["name","admin","sovereignt"] if c in world.columns]
    if not name_cols:
        return None
    mask = False
    for col in name_cols:
        mask = mask | world[col].isin(["United Kingdom","Ireland","U.K.","UK"])
    out = world.loc[mask].copy()
    try:
        out["geometry"] = out["geometry"].buffer(0)
    except Exception:
        pass
    return out if not out.empty else None

def locator_inset(ax, boundary_proj, loc_box=(0.74, 0.08, 0.22, 0.22)):
    inset = ax.inset_axes(loc_box, zorder=12)
    inset.set_facecolor("#f3f3f3")

    ukie = _get_uk_ie()
    if ukie is not None:
        # High-contrast land + coastlines for small scale
        ukie.plot(ax=inset, facecolor="#d0d0d0", edgecolor="#101010",
                  linewidth=1.3, zorder=2)
        inset.set_xlim(-11, 3); inset.set_ylim(49, 60)
    else:
        # Guaranteed visible fallback frame
        gpd.GeoSeries([shp_box(-11,49,3,60)], crs=4326).boundary.plot(
            ax=inset, color="#101010", linewidth=1.4, zorder=2)
        inset.set_xlim(-11, 3); inset.set_ylim(49, 60)

    # City marker
    cx = boundary_proj.to_crs(4326).centroid.iloc[0]
    inset.scatter([cx.x], [cx.y], c="#d33", s=38, edgecolors="white",
                  linewidths=0.9, zorder=5)
    inset.set_xticks([]); inset.set_yticks([])
    for sp in inset.spines.values(): sp.set_edgecolor('#101010')

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

    lons_core = lons[1:-1] if len(lons) > 2 else lons
    lats_core = lats[1:-1] if len(lats) > 2 else lats

    for L in lons_core:
        seg = gpd.GeoSeries([LineString([(L, ymin-1), (L, ymin-0.8)])],
                            crs=4326).to_crs(target_crs).geometry.iloc[0]
        x_here = seg.coords[1][0]
        for y_text, va in ((y0 + ypad, 'bottom'), (y1 - ypad, 'top')):
            ax.text(x_here, y_text, fmt_lon(L, dlon), ha='center', va=va,
                    fontsize=GRAT_LABEL_SIZE, color=GRID_CLR, alpha=alpha,
                    path_effects=[GRAT_LABEL_OUTLINE], zorder=3)

    for P in lats_core:
        seg = gpd.GeoSeries([LineString([(xmin-1, P), (xmin-0.8, P)])],
                            crs=4326).to_crs(target_crs).geometry.iloc[0]
        y_here = seg.coords[1][1]
        for x_text, ha in ((x0 + xpad, 'left'), (x1 - xpad, 'right')):
            ax.text(x_text, y_here, fmt_lat(P, dlat), ha=ha, va='center',
                    fontsize=GRAT_LABEL_SIZE, color=GRID_CLR, alpha=alpha,
                    path_effects=[GRAT_LABEL_OUTLINE], zorder=3)

# ----------------------------- Loaders --------------------------------------
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

# ----------------------------- Panel plotting -------------------------------
def _padded_extent(bounds, pad_frac):
    x0,y0,x1,y1 = bounds
    dx=(x1-x0)*pad_frac; dy=(y1-y0)*pad_frac
    return (x0-dx, y0-dy, x1+dx, y1+dy)

def plot_panel(ax, boundary_proj, pts_to_plot, target_crs,
               dot_size=DOT_SIZE, draw_north=False,
               scalebar_km=None, locator_pos=(0.74, 0.08, 0.22, 0.22)):
    ax.set_facecolor(AX_BG)
    x0p, y0p, x1p, y1p = _padded_extent(boundary_proj.total_bounds, PAD_FRAC)
    ax.set_xlim(x0p, x1p); ax.set_ylim(y0p, y1p)
    ax.set_axis_off()

    if GRATICULE_ON:
        add_graticule(ax, boundary_proj, target_crs)

    boundary_proj.boundary.plot(ax=ax, edgecolor=EDGE, linewidth=0.95, zorder=1.2)

    for r in EPC_ORDER:
        sub = pts_to_plot.loc[pts_to_plot[EPC_COL]==r]
        if not sub.empty:
            ax.scatter(sub.geometry.x, sub.geometry.y, s=dot_size,
                       c=EPC_COLOURS[r], marker="o", linewidths=0,
                       alpha=ALPHA, rasterized=True, zorder=2)
    unk = pts_to_plot.loc[pts_to_plot[EPC_COL]=="UNK"]
    if not unk.empty:
        ax.scatter(unk.geometry.x, unk.geometry.y, s=dot_size*0.8,
                   c=EPC_COLOURS["UNK"], marker="o", linewidths=0,
                   alpha=0.6, rasterized=True, zorder=2)

    if draw_north:
        north_arrow(ax)
    add_scalebar_segmented(ax, total_km=scalebar_km)
    locator_inset(ax, boundary_proj, loc_box=locator_pos)

# --------------------------------- Main -------------------------------------
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

    lon_counts_clip = rating_counts(lon_clip)
    bel_counts_clip = rating_counts(bel_clip)

    lon_thin = maybe_jitter_points(thin_points_grid(lon_clip, CELL_SIZE_M, MAX_PER_CELL, SEED), JITTER_M, seed=SEED)
    bel_thin = maybe_jitter_points(thin_points_grid(bel_clip, CELL_SIZE_M, MAX_PER_CELL, SEED), JITTER_M, seed=SEED)

    N_equal = min(len(lon_thin), len(bel_thin))
    lon_targets = proportional_target_counts(lon_counts_clip, N_equal)
    bel_targets = proportional_target_counts(bel_counts_clip, N_equal)

    lon_sample = stratified_sample(lon_thin, lon_targets, seed=SEED)
    bel_sample = stratified_sample(bel_thin, bel_targets, seed=SEED)

    fig = plt.figure(figsize=(11.69, 8.27), facecolor=FIG_BG)
    gs = GridSpec(nrows=3, ncols=2,
                  height_ratios=[TITLE_BAND, 1.0 - (TITLE_BAND + BOTTOM_BAND), BOTTOM_BAND],
                  width_ratios=WIDTH_RATIOS,
                  left=0.04, right=0.98, bottom=0.06, top=0.96, wspace=WSPACE, hspace=0.06)

    ax_t1 = fig.add_subplot(gs[0,0]); ax_t2 = fig.add_subplot(gs[0,1])
    for a in (ax_t1, ax_t2): a.axis("off")
    ax_t1.text(0.5, 0.72, TITLE_LON, ha="center", va="center", fontsize=16, color=TEXT, weight="bold")
    ax_t1.text(0.5, 0.25, SUB_LON,   ha="center", va="center", fontsize=9,  color=TEXT)
    ax_t2.text(0.5, 0.72, TITLE_BEL, ha="center", va="center", fontsize=16, color=TEXT, weight="bold")
    ax_t2.text(0.5, 0.25, SUB_BEL,   ha="center", va="center", fontsize=9,  color=TEXT)

    ax_lon = fig.add_subplot(gs[1,0])
    ax_bel = fig.add_subplot(gs[1,1])

    plot_panel(ax_lon, lon_bound, lon_sample, LONDON_CRS,
               dot_size=DOT_SIZE, draw_north=NORTH_ARROW_ON_LEFT,
               scalebar_km=SCALEBAR_KM_LONDON, locator_pos=(0.74, 0.08, 0.22, 0.22))

    plot_panel(ax_bel, bel_bound, bel_sample, BELFAST_CRS,
               dot_size=DOT_SIZE, draw_north=False,
               scalebar_km=SCALEBAR_KM_BELFAST, locator_pos=(0.74, 0.08, 0.22, 0.22))

    ax_leg = fig.add_subplot(gs[2,:]); ax_leg.axis("off")
    handles = [Patch(facecolor=EPC_COLOURS[k], edgecolor='none', label=k) for k in EPC_ORDER]
    ax_leg.legend(handles=handles, ncol=7, loc='center',
                  bbox_to_anchor=(0.5, 0.74), frameon=False, fontsize=9,
                  columnspacing=1.0, handlelength=0.9, handletextpad=0.35,
                  title="EPC grade", title_fontsize=9)

    foot1 = ("Projections: London—OSGB 1936 / British National Grid (EPSG:27700); "
             "Belfast—Irish Transverse Mercator (EPSG:2157). "
             "Graticules shown in geographic WGS84 (EPSG:4326).")
    ax_leg.text(0.5, 0.38, foot1, ha='center', va='center', color=TEXT, fontsize=8, transform=ax_leg.transAxes)
    ax_leg.text(0.5, 0.26, "Panels are equal visual size; scalebars indicate true distances in each panel.",
                ha='center', va='center', color="#444444", fontsize=8, transform=ax_leg.transAxes)
    ax_leg.text(0.5, 0.12,
                (f"Each city displays N={len(lon_sample)} points (equal totals). "
                 f"Sampling is stratified by EPC grade to match each city's original distribution. "
                 f"Base thinning ≤{MAX_PER_CELL} points per {CELL_SIZE_M:.0f} m cell (seed {SEED}); "
                 "dots are not proportional to counts."),
                ha='center', va='center', color=TEXT, fontsize=8, transform=ax_leg.transAxes)

    out_png = os.path.join(OUTDIR, "Fig1_StudyAreas_side_by_side.png")
    out_svg = os.path.join(OUTDIR, "Fig1_StudyAreas_side_by_side.svg")
    fig.savefig(out_png, dpi=300, facecolor=FIG_BG)
    fig.savefig(out_svg, dpi=300, facecolor=FIG_BG)

    manifest = {
        "figure":"Fig1_StudyAreas_side_by_side",
        "paths":{
            "london_boundary":LONDON_BOUNDARY,"london_epc":LONDON_EPC,
            "belfast_boundary":BELFAST_BOUNDARY,"belfast_epc_csv":BELFAST_EPC_CSV,
            "belfast_epc_polys":BELFAST_EPC_POLYS
        },
        "crs":{"london":LONDON_CRS,"belfast":BELFAST_CRS},
        "thinning":{"cellsize_m":CELL_SIZE_M,"max_per_cell":MAX_PER_CELL,"seed":SEED,"jitter_m":JITTER_M},
        "equal_points_per_city": len(lon_sample),
        "outputs":{"png":out_png,"svg":out_svg}
    }
    with open(os.path.join(OUTDIR, "Fig1_StudyAreas_manifest.json"),"w",encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"✓ Saved {out_png}\n✓ Saved {out_svg}")

if __name__ == "__main__":
    main()
