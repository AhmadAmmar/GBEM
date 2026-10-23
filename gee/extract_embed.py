"""Pretrained satellite embeddings for every certificate of a year (batch b7 of gbem_composites.js).

    python extract_embed.py --area belfast --year 2024

The 64 embedding components (stored x 10000, here back to -1..1) are taken at the address point (_pt) and as the
area-weighted mean over the building footprint (_fp, extract.Grid sub-grid weighting); a neighbourhood mean within
100 m (_nb100) gives the setting. Tiled exports are read as one virtual mosaic.
Output: data/<area>/gee_v2/features/embed_<year>.parquet (rec_id = certificate; columns emb_A00_pt ... emb_A63_nb100).
assemble.py adds them as the feature group "embedding" (models/baseline.py sets eo_embed, eo_morph_embed).
"""
import argparse, pathlib, sys
import numpy as np
import pandas as pd
import rasterio
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import spec
import extract as E
from safeio import keep                      # existing outputs are archived, never overwritten


def mosaic(area, year):
    """single raster path: the export itself, or a VRT over its tiles"""
    one = spec.raw_path(area, "embed", year)
    if one.exists():
        return one
    tiles = sorted(p for p in spec.raw_dir(area).glob(one.stem + "-*.tif") if "__conflict" not in p.name)
    if not tiles:
        raise SystemExit(f"no embedding export for {area} {year} in {spec.raw_dir(area)}: run batch b7 and ingest it")
    vrt = spec.derived_dir(area) / f"{one.stem}.vrt"
    vrt.parent.mkdir(parents=True, exist_ok=True)
    write_vrt(vrt, tiles)
    return vrt


def write_vrt(vrt, tiles):
    """GDAL virtual mosaic of grid-aligned tiles, written as XML (read by rasterio; no GDAL Python bindings needed)"""
    metas = []
    for t in tiles:
        with rasterio.open(t) as r:
            metas.append((t, r.transform, r.width, r.height, r.count, r.crs.to_wkt(), r.nodata, list(r.descriptions), r.dtypes[0]))
    res = metas[0][1].a
    x0 = min(m[1].c for m in metas); y1 = max(m[1].f for m in metas)
    x1 = max(m[1].c + m[2] * res for m in metas); y0 = min(m[1].f - m[3] * res for m in metas)
    W, H = int(round((x1 - x0) / res)), int(round((y1 - y0) / res))
    dt = {"int16": "Int16", "float32": "Float32"}[metas[0][8]]
    xml = [f'<VRTDataset rasterXSize="{W}" rasterYSize="{H}">', f"<SRS>{metas[0][5]}</SRS>",
           f"<GeoTransform>{x0}, {res}, 0, {y1}, 0, {-res}</GeoTransform>"]
    for b in range(1, metas[0][4] + 1):
        xml.append(f'<VRTRasterBand dataType="{dt}" band="{b}"><Description>{metas[0][7][b - 1]}</Description><NoDataValue>{metas[0][6]}</NoDataValue>')
        for t, tr, w, h, *_ in metas:
            xo, yo = int(round((tr.c - x0) / res)), int(round((y1 - tr.f) / res))
            xml.append(f'<SimpleSource><SourceFilename relativeToVRT="0">{t}</SourceFilename><SourceBand>{b}</SourceBand>'
                       f'<SrcRect xOff="0" yOff="0" xSize="{w}" ySize="{h}"/><DstRect xOff="{xo}" yOff="{yo}" xSize="{w}" ySize="{h}"/></SimpleSource>')
        xml.append("</VRTRasterBand>")
    xml.append("</VRTDataset>")
    vrt.write_text("\n".join(xml), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", required=True); ap.add_argument("--year", type=int, default=2024)
    a = ap.parse_args()
    recs, uniq = E.load_certificates(a.area, a.year)
    p = mosaic(a.area, a.year)
    g = E.Grid(p, uniq, recs["pt"])

    def emb(b):
        return {f"emb_A{i:02d}": b[f"A{i:02d}_annual"] / 10000 for i in range(64)}
    cols = {"rec_id": recs["rec_id"].values}
    for name, st in E.zonal_strips(p, g, emb, recs, {100: 11}).items():
        for s, v in st.items():
            cols[f"{name}_{s}"] = v
    out = pd.DataFrame(cols)
    dest = spec.features_dir(a.area) / f"embed_{a.year}.parquet"
    out.to_parquet(keep(dest), index=False)
    print(f"{a.area} {a.year}: {len(out):,} certificates x {out.shape[1] - 1} embedding features -> {dest}")


if __name__ == "__main__":
    main()
