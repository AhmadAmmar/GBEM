"""QGIS project of the Earth Engine products for one area and year, with styles and quick-look images (PyQGIS).

Version 1.0.0 (21 October 2026). Run inside QGIS 4 (Python console, or exec() through the QGIS MCP server) after
setting AREA and YEAR. The project open in QGIS is not changed: a separate project file is written to
data/<area>/gee_v2/<area>_gee_v2_<year>.qgz, and a quick-look PNG of each layer to data/<area>/gee_v2/qa/quicklooks/.

Layers (stretches from the 2nd to the 98th percentile of a sample of pixels unless stated):
  Sentinel-2 true colour (B4, B3, B2) and false colour (B8, B4, B3), annual and summer
  Landsat LST annual, summer and winter; MODIS Terra and Aqua night LST, winter (deg C)
  ERA5-Land heating degree days; VIIRS night lights; GHSL building height
  WorldCover 2021 with the ESA class colours; terrain (hillshade of the DEM) and slope
  study-area boundary
"""
import os
from qgis.core import (QgsProject, QgsRasterLayer, QgsVectorLayer, QgsFillSymbol, QgsStyle, QgsColorRampShader,
                       QgsRasterShader, QgsSingleBandPseudoColorRenderer, QgsMultiBandColorRenderer, QgsContrastEnhancement,
                       QgsPalettedRasterRenderer, QgsHillshadeRenderer, QgsBilinearRasterResampler, QgsMapSettings,
                       QgsMapRendererParallelJob, QgsCoordinateReferenceSystem, QgsRectangle)
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import QSize

AREA, YEAR = "london", 2024
PHD = r"D:\OneDrive - Ulster University\PhD"
METHOD = "v2_0_1"
EPSG = {"london": 27700, "belfast": 29902}[AREA]
BOUNDARY = {"london": r"data\london\SHP\london.shp", "belfast": r"data\belfast\belfast-dissolved\belfast-dissolved.shp"}[AREA]
CORE = {"london": (501000, 153000, 564000, 204000), "belfast": (315000, 357000, 351000, 390000)}[AREA]
BASE = os.path.join(PHD, "data", AREA, "gee_v2")
RAW = os.path.join(BASE, "raw")
WORLDCOVER = [(10, "006400", "Tree cover"), (20, "ffbb22", "Shrubland"), (30, "ffff4c", "Grassland"), (40, "f096ff", "Cropland"),
              (50, "fa0000", "Built-up"), (60, "b4b4b4", "Bare / sparse vegetation"), (70, "f0f0f0", "Snow and ice"),
              (80, "0064c8", "Permanent water"), (90, "0096a0", "Herbaceous wetland"), (95, "00cf75", "Mangroves"),
              (100, "fae6a0", "Moss and lichen")]


def raw(product, scale=None, year=True):
    name = f"gbem_{METHOD}_{AREA}_{product}" + (f"_{scale}m_{YEAR}" if year else "") + ".tif"
    return os.path.join(RAW, name)


def band_index(lyr, name):
    for i in range(1, lyr.bandCount() + 1):
        if lyr.bandName(i).endswith(name) or lyr.dataProvider().bandDescription(i) == name:
            return i
    raise KeyError(name)


def cut(lyr, band):
    lo, hi = lyr.dataProvider().cumulativeCut(band, 0.02, 0.98, QgsRectangle(), 250000)
    return lo, hi


def pseudo(lyr, band, ramp_name, invert=False, lo=None, hi=None):
    if lo is None:
        lo, hi = cut(lyr, band)
    cr = QgsStyle.defaultStyle().colorRamp(ramp_name)
    if invert:
        cr.invert()
    fn = QgsColorRampShader(lo, hi, cr, QgsColorRampShader.Type.Interpolated)
    fn.classifyColorRamp(9, -1)
    sh = QgsRasterShader(); sh.setRasterShaderFunction(fn)
    r = QgsSingleBandPseudoColorRenderer(lyr.dataProvider(), band, sh)
    r.setClassificationMin(lo); r.setClassificationMax(hi)
    lyr.setRenderer(r)


def rgb(lyr, bands):
    r = QgsMultiBandColorRenderer(lyr.dataProvider(), *bands)
    for setter, b in zip((r.setRedContrastEnhancement, r.setGreenContrastEnhancement, r.setBlueContrastEnhancement), bands):
        ce = QgsContrastEnhancement(lyr.dataProvider().dataType(b))
        ce.setContrastEnhancementAlgorithm(QgsContrastEnhancement.ContrastEnhancementAlgorithm.StretchToMinimumMaximum)
        lo, hi = cut(lyr, b); ce.setMinimumValue(lo); ce.setMaximumValue(hi)
        setter(ce)
    lyr.setRenderer(r)


def quicklook(lyr, boundary, path, extent):
    ms = QgsMapSettings()
    ms.setLayers([boundary, lyr]); ms.setDestinationCrs(QgsCoordinateReferenceSystem(f"EPSG:{EPSG}"))
    ms.setExtent(extent); ms.setOutputSize(QSize(1400, int(1400 * extent.height() / extent.width())))
    ms.setBackgroundColor(QColor("white"))
    job = QgsMapRendererParallelJob(ms); job.start(); job.waitForFinished()
    job.renderedImage().save(path, "PNG")


def run():
    proj = QgsProject()
    proj.setCrs(QgsCoordinateReferenceSystem(f"EPSG:{EPSG}"))
    qa = os.path.join(BASE, "qa", "quicklooks"); os.makedirs(qa, exist_ok=True)
    root = proj.layerTreeRoot()
    bnd = QgsVectorLayer(os.path.join(PHD, BOUNDARY), "Study-area boundary", "ogr")
    bnd.renderer().setSymbol(QgsFillSymbol.createSimple({"style": "no", "outline_color": "20,20,20", "outline_width": "0.5"}))
    proj.addMapLayer(bnd)

    specs = []   # (group, name, path, styler)
    for w in ("annual", "summer"):
        specs.append(("Sentinel-2", f"S2 true colour {w}", raw("s2", 10), lambda l, w=w: rgb(l, [band_index(l, f"B4_{w}"), band_index(l, f"B3_{w}"), band_index(l, f"B2_{w}")])))
        specs.append(("Sentinel-2", f"S2 false colour (NIR) {w}", raw("s2", 10), lambda l, w=w: rgb(l, [band_index(l, f"B8_{w}"), band_index(l, f"B4_{w}"), band_index(l, f"B3_{w}")])))
    for w in ("annual", "summer", "winter"):
        specs.append(("Surface temperature", f"Landsat LST {w} (deg C x 100)", raw("landsat", 30), lambda l, w=w: pseudo(l, band_index(l, f"LST_{w}"), "Spectral", True)))
    for s in ("terra", "aqua"):
        specs.append(("Surface temperature", f"MODIS {s} night LST winter (deg C x 100)", raw("modis", 1000), lambda l, s=s: pseudo(l, band_index(l, f"{s}_night_winter"), "Spectral", True)))
    specs += [
        ("Climate and activity", "ERA5-Land heating degree days, annual", raw("era5", 1000), lambda l: pseudo(l, band_index(l, "HDD_annual"), "Blues")),
        ("Climate and activity", "VIIRS night lights, annual (nW cm-2 sr-1)", raw("viirs", 500), lambda l: pseudo(l, band_index(l, "avg_rad_annual"), "Magma")),
        ("Built form and land cover", "GHSL building height 2018 (m)", raw("ghsl_100m", year=False), lambda l: pseudo(l, 1, "Viridis", lo=0, hi=25)),
        ("Built form and land cover", "WorldCover 2021", raw("worldcover_10m", year=False),
         lambda l: l.setRenderer(QgsPalettedRasterRenderer(l.dataProvider(), 1, [QgsPalettedRasterRenderer.Class(v, QColor("#" + c), lab) for v, c, lab in WORLDCOVER]))),
        ("Terrain", "Hillshade (Copernicus DEM)", os.path.join(BASE, "derived", "terrain_30m.tif"), lambda l: l.setRenderer(QgsHillshadeRenderer(l.dataProvider(), 1, 315, 45))),
        ("Terrain", "Slope (deg)", os.path.join(BASE, "derived", "terrain_30m.tif"), lambda l: pseudo(l, 2, "Reds")),
    ]
    groups, done = {}, []
    for group, name, path, styler in specs:
        if not os.path.exists(path):
            print("missing, skipped:", path); continue
        lyr = QgsRasterLayer(path, name)
        lyr.resampleFilter().setZoomedOutResampler(QgsBilinearRasterResampler())
        styler(lyr)
        proj.addMapLayer(lyr, False)
        if group not in groups:
            groups[group] = root.addGroup(group)
        groups[group].addLayer(lyr).setItemVisibilityChecked(not done)
        quicklook(lyr, bnd, os.path.join(qa, "".join(c if c.isalnum() else "_" for c in name) + ".png"), QgsRectangle(*CORE))
        done.append(name)
    out = os.path.join(BASE, f"{AREA}_gee_v2_{YEAR}.qgz")
    proj.write(out)
    return {"project": out, "layers": len(done), "quicklooks": qa}


result = run()
print(result)
