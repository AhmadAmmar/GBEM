"""Footprint statistics beyond the mean for the 10 m layers: minimum, maximum and standard deviation within each
building footprint (extract.py gives the point value, the area-weighted footprint mean and neighbourhood means).

    python fp_stats.py --area belfast --year 2024

Variables: Sentinel-2 annual reflectance B2, B4, B8, B11, B12 and NDVI, NDBI, BSI, MNDWI; Sentinel-1 annual VV and VH
(dB). Footprints are rasterised on the 5 x 5 sub-grid of extract.Grid; the standard deviation is weighted by the share
of each pixel the footprint covers, and minimum and maximum use the pixels covered by at least a quarter. A footprint
needs at least 2 pixels for a standard deviation and minimum/maximum (fps_px is the number of covered pixels).
Output: data/<area>/gee_v2/features/fpstats_<year>.parquet (rec_id = certificate; columns fps_<variable>_{min,max,sd})
"""
import argparse, sys, pathlib
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import spec
import extract as E
from safeio import keep                      # existing outputs are archived, never overwritten

S2_KEEP = ["B2", "B4", "B8", "B11", "B12", "NDVI", "NDBI", "BSI", "MNDWI"]


def s2_vars(b):
    refl = {k: b[f"{k}_annual"] / 10000 for k in spec.S2_BANDS}
    idx = E.s2_indices(refl)
    return {f"s2_{k}": (refl.get(k) if k in refl else idx[k]) for k in S2_KEEP}


def s1_vars(b):
    out = {}
    for pol in ("VV", "VH"):
        v = b[f"{pol}_annual"] / 100                                 # stored as dB x 100
        out[f"s1_{pol}dB"] = v
    return out


def stats(path, grid, compute, n_lab):
    s, s2, w = {}, {}, {}
    mn, mx = {}, {}
    with rasterio.open(path) as r:
        names = list(r.descriptions)
        for r0 in range(0, grid.h, E.STRIP):
            cov = grid.cover.get(r0)
            if cov is None:
                continue
            r1 = min(grid.h, r0 + E.STRIP)
            raw = r.read(window=Window(0, r0, grid.w, r1 - r0))
            bands = {nm: np.where(raw[i] == r.nodata, np.nan, raw[i].astype("float32")) for i, nm in enumerate(names)}
            lab, pix, wgt = cov
            for name, v in compute(bands).items():
                x = v.ravel()[pix].astype("float64")
                ok = ~np.isnan(x)
                for d in (s, s2, w):
                    d.setdefault(name, np.zeros(n_lab))
                mn.setdefault(name, np.full(n_lab, np.inf)); mx.setdefault(name, np.full(n_lab, -np.inf))
                s[name] += np.bincount(lab[ok], weights=wgt[ok] * x[ok], minlength=n_lab)
                s2[name] += np.bincount(lab[ok], weights=wgt[ok] * x[ok] ** 2, minlength=n_lab)
                w[name] += np.bincount(lab[ok], weights=wgt[ok], minlength=n_lab)
                big = ok & (wgt >= 0.25)
                np.minimum.at(mn[name], lab[big], x[big]); np.maximum.at(mx[name], lab[big], x[big])
    out = {}
    for name in s:
        m = s[name] / np.maximum(w[name], 1e-12)
        sd = np.sqrt(np.clip(s2[name] / np.maximum(w[name], 1e-12) - m ** 2, 0, None))
        enough = w[name] >= 2
        out[f"fps_{name}_sd"] = np.where(enough, sd, np.nan)
        out[f"fps_{name}_min"] = np.where(enough & np.isfinite(mn[name]), mn[name], np.nan)
        out[f"fps_{name}_max"] = np.where(enough & np.isfinite(mx[name]), mx[name], np.nan)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--year", type=int, required=True)
    a = ap.parse_args()
    recs, uniq = E.load_certificates(a.area, a.year)
    lab = recs["fp_label"].to_numpy()
    cols = {"rec_id": recs["rec_id"].values}
    for prod, compute in (("s2", s2_vars), ("s1", s1_vars)):
        p = spec.raw_path(a.area, prod, a.year)
        g = E.Grid(p, uniq, recs["pt"])
        if prod == "s2":
            cols["fps_px"] = np.where(lab > 0, g.px[lab], 0)
        for k, v in stats(p, g, compute, g.n_lab).items():
            cols[k] = np.where(lab > 0, v[lab], np.nan)
        print(prod, "done", flush=True)
    out = pd.DataFrame(cols)
    dest = spec.features_dir(a.area) / f"fpstats_{a.year}.parquet"
    out.to_parquet(keep(dest), index=False)
    print(f"{a.area} {a.year}: {len(out):,} certificates, {out.shape[1] - 1} columns; footprints with >= 2 pixels: "
          f"{(out['fps_px'] >= 2).mean():.1%} -> {dest}")


if __name__ == "__main__":
    main()
