"""Sentinel-1 layers, symbology and maps in QGIS (PyQGIS), from the Earth Engine composite of gbem_composites.js.

Version 1.0.0 (21 October 2026). Run inside QGIS (Python console, or exec() through the QGIS MCP server) after setting
S1, BOUNDARY, OUT and MAPS below. Tested with QGIS 4.2.

1. Derived raster (float32, dB, missing = -9999), one band each:
     VV_dB, VH_dB    backscatter (stored value / 100)
     VVminusVH_dB    polarisation ratio, 10 log10(VV/VH); same name and definition as the earlier s1_VV_minus_VH_dB
     span_dB         total power, 10 log10(VV + VH) in linear units
   Not derived, because they carry no extra information: VH-VV (the same ratio with the opposite sign), VV/VH in linear
   units, the normalised difference (VV-VH)/(VV+VH) and the dual-polarisation RVI 4VH/(VV+VH) - each is a monotonic
   function of the same ratio (rank correlation +-1 with VV-VH in the earlier Belfast samples). VV+VH computed on dB
   values has no physical meaning (it is the log of the product).
2. Layers in a group, each styled: false-colour composite (R = VV, G = VH, B = VV-VH), VV and VH in grey, the ratio
   (viridis) and span (magma), stretched between the 2nd and 98th percentiles; observation count and incidence angle
   for quality checks. Each style is saved as a QML file next to the derived raster.
3. A4 maps (PNG, 200 dpi) of the study area and of central London, with title, legend, scale bar, north arrow and
   data credit.
"""
import os
import numpy as np
from osgeo import gdal
from qgis.core import (QgsProject, QgsRasterLayer, QgsVectorLayer, QgsFillSymbol, QgsStyle, QgsColorRampShader,
                       QgsRasterShader, QgsSingleBandPseudoColorRenderer, QgsSingleBandGrayRenderer,
                       QgsMultiBandColorRenderer, QgsContrastEnhancement, QgsRectangle, QgsPrintLayout,
                       QgsLayoutItemMap, QgsLayoutItemLabel, QgsLayoutItemLegend, QgsLayoutItemScaleBar,
                       QgsLayoutItemPicture, QgsLayoutPoint, QgsLayoutSize, QgsLayoutExporter, QgsBilinearRasterResampler,
                       QgsCoordinateReferenceSystem, QgsLegendRenderer, QgsLegendStyle, QgsMapLayerLegendUtils, Qgis)
from qgis.PyQt.QtGui import QFont, QColor

S1 = r"C:\Users\Owner\Downloads\gbem_v2_0_1_london_s1_10m_2024.tif"
BOUNDARY = r"D:\OneDrive - Ulster University\PhD\data\london\SHP\london.shp"
OUT = r"D:\OneDrive - Ulster University\PhD\data\london\gee_v2\derived"
MAPS = r"D:\OneDrive - Ulster University\PhD\Maps\gee_v2"
AREA, YEAR = "Greater London", 2024
ZOOM = QgsRectangle(527000, 177500, 535000, 183500)        # central London, British National Grid
CREDIT = (f"Sentinel-1 GRD IW, {YEAR} annual median (both orbits). Contains modified Copernicus Sentinel data {YEAR}, "
          "processed in Google Earth Engine.")
MM = Qgis.LayoutUnit.Millimeters
NODATA = -9999.0


def derive(src, dst):
    """Derived bands in dB; returns 2nd/98th percentiles per band."""
    ds = gdal.Open(src)
    raw = [ds.GetRasterBand(i).ReadAsArray().astype("float32") for i in (1, 2)]
    nd = ds.GetRasterBand(1).GetNoDataValue()
    ok = (raw[0] != nd) & (raw[1] != nd)
    vv, vh = raw[0] / 100.0, raw[1] / 100.0
    ratio = vv - vh
    span = 10 * np.log10(10 ** (vv / 10) + 10 ** (vh / 10))
    bands = {"VV_dB": vv, "VH_dB": vh, "VVminusVH_dB": ratio, "span_dB": span}
    drv = gdal.GetDriverByName("GTiff")
    out = drv.Create(dst, ds.RasterXSize, ds.RasterYSize, len(bands), gdal.GDT_Float32,
                     ["COMPRESS=DEFLATE", "PREDICTOR=3", "TILED=YES", "BIGTIFF=IF_SAFER"])
    out.SetGeoTransform(ds.GetGeoTransform()); out.SetProjection(ds.GetProjection())
    pct = {}
    for i, (name, a) in enumerate(bands.items(), 1):
        b = out.GetRasterBand(i)
        b.WriteArray(np.where(ok, a, NODATA).astype("float32")); b.SetNoDataValue(NODATA); b.SetDescription(name)
        pct[name] = [float(x) for x in np.percentile(a[ok][::7], [2, 98])]
    out.FlushCache(); out = None
    return pct


def layer(path, name):
    lyr = QgsRasterLayer(path, name)
    lyr.resampleFilter().setZoomedOutResampler(QgsBilinearRasterResampler())
    return lyr


def stretch(provider, band, lo, hi):
    ce = QgsContrastEnhancement(provider.dataType(band))
    ce.setContrastEnhancementAlgorithm(QgsContrastEnhancement.ContrastEnhancementAlgorithm.StretchToMinimumMaximum)
    ce.setMinimumValue(lo); ce.setMaximumValue(hi)
    return ce


def grey(lyr, band, lo, hi):
    r = QgsSingleBandGrayRenderer(lyr.dataProvider(), band)
    r.setContrastEnhancement(stretch(lyr.dataProvider(), band, lo, hi))
    lyr.setRenderer(r)


def ramp(lyr, band, lo, hi, ramp_name, invert=False):
    cr = QgsStyle.defaultStyle().colorRamp(ramp_name)
    if invert:
        cr.invert()
    fn = QgsColorRampShader(lo, hi, cr, QgsColorRampShader.Type.Interpolated)
    fn.classifyColorRamp(9, -1)
    sh = QgsRasterShader(); sh.setRasterShaderFunction(fn)
    r = QgsSingleBandPseudoColorRenderer(lyr.dataProvider(), band, sh)
    r.setClassificationMin(lo); r.setClassificationMax(hi)
    lyr.setRenderer(r)


def rgb(lyr, p):
    r = QgsMultiBandColorRenderer(lyr.dataProvider(), 1, 2, 3)
    for setter, band, key in ((r.setRedContrastEnhancement, 1, "VV_dB"), (r.setGreenContrastEnhancement, 2, "VH_dB"),
                              (r.setBlueContrastEnhancement, 3, "VVminusVH_dB")):
        setter(stretch(lyr.dataProvider(), band, *p[key]))
    lyr.setRenderer(r)


def label(layout, text, x, y, w, h, size=10, bold=False):
    it = QgsLayoutItemLabel(layout); it.setText(text)
    f = QFont("Arial", size); f.setBold(bold)
    fmt = it.textFormat(); fmt.setFont(f); fmt.setSize(size); it.setTextFormat(fmt)
    it.attemptMove(QgsLayoutPoint(x, y, MM)); it.attemptResize(QgsLayoutSize(w, h, MM))
    layout.addLayoutItem(it)
    return it


def make_map(name, title, lyr, boundary, extent, legend_title=None, note=None):
    proj = QgsProject.instance()
    old = proj.layoutManager().layoutByName(name)
    if old:
        proj.layoutManager().removeLayout(old)
    lay = QgsPrintLayout(proj); lay.initializeDefaults(); lay.setName(name)   # A4 landscape
    m = QgsLayoutItemMap(lay)
    m.attemptMove(QgsLayoutPoint(8, 20, MM)); m.attemptResize(QgsLayoutSize(215, 182, MM))
    m.setCrs(QgsCoordinateReferenceSystem("EPSG:27700"))
    m.setLayers([boundary, lyr]); m.setKeepLayerSet(True)
    m.setExtent(extent); m.setFrameEnabled(True)
    lay.addLayoutItem(m)
    label(lay, title, 8, 6, 280, 12, 16, True)
    x = 228
    if legend_title:
        lg = QgsLayoutItemLegend(lay); lg.setLinkedMap(m); lg.setAutoUpdateModel(False)
        root = lg.model().rootGroup(); root.clear(); node = root.addLayer(lyr)
        QgsLegendRenderer.setNodeLegendStyle(node, QgsLegendStyle.Style.Hidden)       # no layer name line
        n_items = len(lg.model().layerLegendNodes(node))
        if n_items > 1:                                                               # keep the colour ramp, drop the band name
            QgsMapLayerLegendUtils.setLegendNodeOrder(node, [n_items - 1]); lg.model().refreshLayerLegend(node)
        lg.setTitle(legend_title); lg.attemptMove(QgsLayoutPoint(x, 22, MM))
        lay.addLayoutItem(lg)
    if note:
        label(lay, note, x, 22 if not legend_title else 120, 62, 110 if not legend_title else 40, 9)
    sb = QgsLayoutItemScaleBar(lay); sb.setLinkedMap(m); sb.setStyle("Single Box")
    sb.setUnits(Qgis.DistanceUnit.Kilometers); sb.setUnitLabel("km")
    sb.setNumberOfSegments(2); sb.setNumberOfSegmentsLeft(0)
    sb.setSegmentSizeMode(Qgis.ScaleBarSegmentSizeMode.FitWidth)    # QGIS picks a round segment length within the width
    sb.setMinimumBarWidth(35); sb.setMaximumBarWidth(50)
    sb.update()
    sb.attemptMove(QgsLayoutPoint(x, 175, MM)); lay.addLayoutItem(sb)
    na = QgsLayoutItemPicture(lay); na.setPicturePath(":/images/north_arrows/layout_default_north_arrow.svg")
    na.attemptMove(QgsLayoutPoint(275, 150, MM)); na.attemptResize(QgsLayoutSize(12, 18, MM)); lay.addLayoutItem(na)
    label(lay, CREDIT + " British National Grid (EPSG:27700).", 8, 203, 280, 6, 7)
    proj.layoutManager().addLayout(lay)
    QgsLayoutExporter(lay).exportToImage(os.path.join(MAPS, name + ".png"), _png())
    return lay


def _png():
    s = QgsLayoutExporter.ImageExportSettings(); s.dpi = 200
    return s


def run():
    os.makedirs(OUT, exist_ok=True); os.makedirs(MAPS, exist_ok=True)
    base = os.path.splitext(os.path.basename(S1))[0]
    dst = os.path.join(OUT, base + "_derived.tif")
    proj = QgsProject.instance()
    grp_name = f"Sentinel-1 {YEAR} {AREA}"
    root = proj.layerTreeRoot()
    old = root.findGroup(grp_name)
    if old:      # a previous run: close its layers (they hold the derived file open) before rewriting it
        proj.removeMapLayers([n.layerId() for n in old.findLayers()])
        root.removeChildNode(old)
    p = derive(S1, dst)
    grp = root.insertGroup(0, grp_name)

    bnd = QgsVectorLayer(BOUNDARY, f"{AREA} boundary", "ogr")
    bnd.setRenderer(bnd.renderer().clone())
    bnd.renderer().setSymbol(QgsFillSymbol.createSimple({"style": "no", "outline_color": "20,20,20", "outline_width": "0.5"}))
    proj.addMapLayer(bnd, False); grp.addLayer(bnd)

    styles = [   # name, band(s), style, legend title
        ("S1 false colour (R VV, G VH, B VV-VH)", None, "rgb", None),
        ("S1 VV (dB)", 1, ("grey",), "VV backscatter (dB)"),
        ("S1 VH (dB)", 2, ("grey",), "VH backscatter (dB)"),
        ("S1 VV-VH ratio (dB)", 3, ("ramp", "Viridis", False), "VV-VH (dB)"),
        ("S1 span (dB)", 4, ("ramp", "Magma", False), "Total power (dB)"),
    ]
    keys = ["VV_dB", "VH_dB", "VVminusVH_dB", "span_dB"]
    made = {}
    for name, band, style, _ in styles:
        lyr = layer(dst, name)
        if style == "rgb":
            rgb(lyr, p)
        elif style[0] == "grey":
            grey(lyr, band, *p[keys[band - 1]])
        else:
            ramp(lyr, band, *p[keys[band - 1]], style[1], style[2])
        proj.addMapLayer(lyr, False); grp.addLayer(lyr)
        lyr.saveNamedStyle(os.path.join(OUT, "style_" + "".join(c for c in name.split("(")[0] if c.isalnum()) + ".qml"))
        made[name] = lyr
    # quality layers from the original composite: observation count and incidence angle
    for name, band, rmp, lo, hi in (("S1 observations (n)", 4, "Blues", None, None), ("S1 incidence angle (deg x 100)", 3, "Spectral", None, None)):
        lyr = layer(S1, name)
        st = lyr.dataProvider().bandStatistics(band)
        ramp(lyr, band, st.minimumValue, st.maximumValue, rmp)
        proj.addMapLayer(lyr, False); grp.addLayer(lyr)
        lyr.saveNamedStyle(os.path.join(OUT, "style_" + "".join(c for c in name.split("(")[0] if c.isalnum()) + ".qml"))
        made[name] = lyr
    for n in list(made)[1:]:
        grp.findLayer(made[n].id()).setItemVisibilityChecked(False)

    full = QgsRectangle(501000, 153000, 564000, 204000)
    notes = {"S1 false colour (R VV, G VH, B VV-VH)": "Red: VV; green: VH; blue: VV-VH ratio, each stretched between "
             "its 2nd and 98th percentiles.\n\nYellow to white: dense built-up areas (high VV and VH).\n"
             "Pink to violet: VV-dominated surfaces, such as buildings oriented away from the radar and paved areas.\n"
             "Green: vegetation (VH from volume scattering).\nDark blue to violet: water and smooth or bare ground "
             "(very low VH, so a high VV-VH ratio).",
             "S1 VV (dB)": "Co-polarised backscatter. Bright: buildings (double bounce between walls and ground) and "
             "rough surfaces; dark: water, runways and other smooth surfaces.",
             "S1 VH (dB)": "Cross-polarised backscatter. Bright: vegetation canopies and complex built structure "
             "(volume and multiple scattering); dark: water and smooth surfaces.",
             "S1 VV-VH ratio (dB)": "10 log10(VV/VH). High: VV dominates (buildings, paved surfaces, open water). "
             "Low: VH relatively strong (trees and other vegetation). Same quantity as VV/VH, the normalised "
             "difference and the dual-polarisation RVI, on another scale.",
             "S1 span (dB)": "Total backscattered power, 10 log10(VV + VH) in linear units: overall brightness, "
             "independent of polarisation."}
    maps = []
    for name, band, style, leg in styles:
        tag = "".join(c for c in name.split("(")[0] if c.isalnum())
        title = f"{name.split(' (')[0].replace('S1', 'Sentinel-1')}, {AREA}, {YEAR}"
        make_map(f"london_s1_{YEAR}_{tag}", title, made[name], bnd, full, leg, notes.get(name))
        maps.append(f"london_s1_{YEAR}_{tag}.png")
    rgbname = styles[0][0]
    make_map(f"london_s1_{YEAR}_FalseColour_central", f"Sentinel-1 false colour, central London, {YEAR}", made[rgbname],
             bnd, ZOOM, None, notes[rgbname])
    maps.append(f"london_s1_{YEAR}_FalseColour_central.png")
    return {"derived": dst, "percentiles_2_98": p, "maps": maps}


result = run()
print(result)
