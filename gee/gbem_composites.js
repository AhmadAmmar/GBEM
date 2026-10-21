/*******************************************************************************
 GBEM - Earth Engine composites for Greater London and Greater Belfast
 Version 2.0.0 (21 October 2026)          https://github.com/AhmadAmmar/GBEM

 Purpose
   Builds the image composites that need the full satellite archives (cloud masking, temporal reduction) and exports
   them as multi-band GeoTIFFs to Google Drive. Everything else - spectral indices, terrain derivatives, urban heat
   island intensity, wind speed, and the extraction of values for each building (point, buffer or footprint) - is done
   locally in Python from these rasters (code/gee/README.md). This keeps Earth Engine compute low, lets the extraction be
   repeated without new Earth Engine runs, and keeps property-level EPC data off Earth Engine.

 What is exported (one image per area, product and year; time windows are bands)
   static   WorldCover 2021 class (10 m); Copernicus DEM GLO-30 elevation (30 m); GHSL building height 2018 and
            built volume 2020 (100 m)
   s2       Sentinel-2 L2A surface reflectance, B2-B12 median, Cloud Score+ masked; valid-observation count (10 m)
   s1       Sentinel-1 GRD IW VV and VH backscatter median (dB), incidence angle; count (10 m)
   landsat  Landsat 8 and 9 Collection 2 land surface temperature median (deg C), QA masked; count (30 m)
   modis    MODIS Terra and Aqua day and night land surface temperature median (deg C), QC masked; counts (1 km)
   era5     ERA5-Land air and dew-point temperature, wind components, precipitation, solar radiation, heating and
            cooling degree days (1 km grid, native 0.1 deg)
   viirs    VIIRS monthly night-time light radiance, annual median (500 m)

 Time windows per year: annual (Jan-Dec), summer (Jun-Aug), winter (Dec of the previous year to Feb), plus the event
 windows in CONFIG.events (heatwave and cold spell) for the thermal and climate products.

 Grids
   Each area is exported in its national grid (London: British National Grid EPSG:27700; Belfast: Irish Grid
   EPSG:29902, as the local data), on extents snapped to 3 km, so that the 10, 30, 100, 500 and 1000 m rasters nest
   exactly. 'core' extent: area + 1 km (London) or the Greater Belfast extent; 'context' extent: a wider ring used by
   the coarse products and for the rural reference of the surface urban heat island.
   Greater London: Greater London Authority boundary. Greater Belfast: Belfast City Council area extent + 8 km
   (Lisburn, Castlereagh, Newtownabbey, Holywood, Carrickfergus).

 Data types and missing values
   Large products are integers with scale factors (see SCALE below; value = stored / scale); missing = -32768.
   Small products are float32; missing = -9999.

 How to run
   1. Paste into the Earth Engine Code Editor and press Run with CONFIG.dryRun = true: the console lists the planned
      exports with an upper bound of their size, and preview layers are added to the map.
   2. Set CONFIG.dryRun = false, choose the batch in CONFIG.areas / CONFIG.years / CONFIG.products, press Run, and
      start the tasks in the Tasks tab. Exports go to the Drive folder CONFIG.driveFolder.
   3. A provenance table (number of input scenes per composite and window) is exported with each batch.
*******************************************************************************/

var CONFIG = {
  version: 'v2_0_0',
  driveFolder: 'GBEM_GEE_v2',
  dryRun: true,                         // true: plan and preview only; false: create the export tasks
  areas: ['london', 'belfast'],
  years: [2024],                        // first batch reproduces the 2024 samples; then e.g. [2018, ..., 2025]
  products: ['static', 's2', 's1', 'landsat', 'modis', 'era5', 'viirs'],
  windows: {                            // time windows exported per product (bands of the same image)
    s2: ['annual', 'summer'],
    s1: ['annual'],
    landsat: ['annual', 'summer', 'winter'],
    modis: ['annual', 'summer', 'winter'],
    era5: ['annual', 'summer', 'winter'],
    viirs: ['annual']
  },
  events: [                             // short windows, added to the thermal and climate products of their year
    {name: 'heat2022', start: '2022-07-10', end: '2022-07-26', products: ['landsat', 'modis', 'era5']},
    {name: 'cold2022', start: '2022-12-05', end: '2022-12-20', products: ['landsat', 'modis', 'era5']}
  ],
  s2CloudScore: 0.60,                   // Cloud Score+ cs_cdf threshold (Google's recommended default)
  s2MaxSceneCloud: 80,                  // scene-level prefilter, %
  hddBase: 15.5,                        // heating degree days base, deg C
  cddBase: 22.0                         // cooling degree days base, deg C
};

// ---------------------------------------------------------------- areas (projected extents, metres)
var AREAS = {
  london: {crs: 'EPSG:27700', label: 'Greater London',
           core: [501000, 153000, 564000, 204000], context: [492000, 144000, 573000, 213000]},
  // Irish Grid as the local Northern Ireland data; if Earth Engine rejects the code, use 'EPSG:2157' (Irish Transverse
  // Mercator) and recompute the extents with code/gee/extents.py
  belfast: {crs: 'EPSG:29902', label: 'Greater Belfast',
            core: [315000, 357000, 351000, 390000], context: [309000, 351000, 357000, 399000]}
};

var NODATA_INT = -32768, NODATA_FLOAT = -9999;
var SCALE = {reflectance: 1, dB: 100, degC: 100};   // stored = value * scale (reflectance is already x10000)
var S2_BANDS = ['B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B8A', 'B11', 'B12'];

// ---------------------------------------------------------------- helpers
function rect(area, key) {
  return ee.Geometry.Rectangle({coords: AREAS[area][key], proj: AREAS[area].crs, geodesic: false});
}

function windowDates(win, year) {
  if (win === 'annual') return [year + '-01-01', (year + 1) + '-01-01'];
  if (win === 'summer') return [year + '-06-01', year + '-09-01'];
  if (win === 'winter') return [(year - 1) + '-12-01', year + '-03-01'];
  for (var i = 0; i < CONFIG.events.length; i++) {
    if (CONFIG.events[i].name === win) return [CONFIG.events[i].start, CONFIG.events[i].end];
  }
  throw new Error('Unknown window: ' + win);
}

function windowsFor(product, year) {
  var w = (CONFIG.windows[product] || []).slice();
  CONFIG.events.forEach(function (e) {
    if (e.products.indexOf(product) >= 0 && Number(e.start.slice(0, 4)) === year) w.push(e.name);
  });
  return w;
}

function suffix(img, win) {
  return img.rename(img.bandNames().map(function (b) { return ee.String(b).cat('_').cat(win); }));
}

var PLAN = [], PROVENANCE = [];

function addExport(img, area, name, scale, extent, type, nBands) {
  var A = AREAS[area], r = A[extent];
  var w = (r[2] - r[0]) / scale, h = (r[3] - r[1]) / scale;
  var mb = w * h * nBands * (type === 'int16' ? 2 : 4) / 1e6;
  PLAN.push(name + '  [' + scale + ' m, ' + extent + ', ' + nBands + ' bands, ' + type + ', <= ' + mb.toFixed(0) + ' MB]');
  if (CONFIG.dryRun) return;
  var out = type === 'int16' ? img.unmask(NODATA_INT, false).toInt16() : img.unmask(NODATA_FLOAT, false).toFloat();
  Export.image.toDrive({
    image: out, description: name, folder: CONFIG.driveFolder, fileNamePrefix: name,
    region: rect(area, extent), crs: A.crs, crsTransform: [scale, 0, r[0], 0, -scale, r[3]],
    maxPixels: 1e13, fileFormat: 'GeoTIFF',
    formatOptions: {cloudOptimized: true, noData: type === 'int16' ? NODATA_INT : NODATA_FLOAT}
  });
}

function provenance(area, product, year, win, collection, dates) {
  PROVENANCE.push(ee.Feature(null, {
    version: CONFIG.version, area: area, product: product, year: year, window: win,
    start: dates[0], end: dates[1], n_scenes: collection.size()
  }));
}

// ---------------------------------------------------------------- products
function s2(area, year) {
  var region = rect(area, 'core'), bands = [];
  var cs = ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED');
  windowsFor('s2', year).forEach(function (win) {
    var d = windowDates(win, year);
    var col = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(region).filterDate(d[0], d[1])
      .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', CONFIG.s2MaxSceneCloud))
      .linkCollection(cs, ['cs_cdf'])
      .map(function (img) { return img.updateMask(img.select('cs_cdf').gte(CONFIG.s2CloudScore)).select(S2_BANDS); });
    provenance(area, 's2', year, win, col, d);
    bands.push(suffix(col.median().addBands(col.select('B4').count().rename('n')), win));
  });
  return {img: ee.Image.cat(bands), nBands: bands.length * (S2_BANDS.length + 1)};
}

function s1(area, year) {
  var region = rect(area, 'core'), bands = [];
  windowsFor('s1', year).forEach(function (win) {
    var d = windowDates(win, year);
    var col = ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(region).filterDate(d[0], d[1])
      .filter(ee.Filter.eq('instrumentMode', 'IW'))
      .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
      .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
      .map(function (img) { return img.updateMask(img.select('VV').gt(-30)); })   // dark scene borders
      .select(['VV', 'VH', 'angle']);
    provenance(area, 's1', year, win, col, d);
    var med = col.select(['VV', 'VH']).median().multiply(SCALE.dB);
    var ang = col.select('angle').mean().multiply(SCALE.dB);
    bands.push(suffix(med.addBands(ang).addBands(col.select('VV').count().rename('n')), win));
  });
  return {img: ee.Image.cat(bands), nBands: bands.length * 4};
}

function landsatLST(img) {
  var qa = img.select('QA_PIXEL');
  var clear = qa.bitwiseAnd(1 << 1).eq(0)          // dilated cloud
    .and(qa.bitwiseAnd(1 << 3).eq(0))               // cloud
    .and(qa.bitwiseAnd(1 << 4).eq(0))               // cloud shadow
    .and(qa.bitwiseAnd(1 << 5).eq(0));              // snow
  return img.select('ST_B10').multiply(0.00341802).add(149.0).subtract(273.15)
    .rename('LST').updateMask(clear).copyProperties(img, ['system:time_start']);
}

function landsat(area, year) {
  var region = rect(area, 'context'), bands = [];
  windowsFor('landsat', year).forEach(function (win) {
    var d = windowDates(win, year);
    var col = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
      .merge(ee.ImageCollection('LANDSAT/LC09/C02/T1_L2'))
      .filterBounds(region).filterDate(d[0], d[1]).map(landsatLST);
    provenance(area, 'landsat', year, win, col, d);
    bands.push(suffix(col.median().multiply(SCALE.degC).addBands(col.count().rename('n')), win));
  });
  return {img: ee.Image.cat(bands), nBands: bands.length * 2};
}

function modisLST(id, prefix, d, region) {
  var col = ee.ImageCollection(id).filterBounds(region).filterDate(d[0], d[1]);
  var q = function (band, qc) {
    return col.map(function (img) {
      var flags = img.select(qc);
      var good = flags.bitwiseAnd(3).lte(1).and(flags.rightShift(6).bitwiseAnd(3).lte(1));   // produced; error <= 2 K
      return img.select(band).multiply(0.02).subtract(273.15).updateMask(good);
    });
  };
  var day = q('LST_Day_1km', 'QC_Day'), night = q('LST_Night_1km', 'QC_Night');
  return {col: col, img: day.median().multiply(SCALE.degC).rename(prefix + '_day')
    .addBands(night.median().multiply(SCALE.degC).rename(prefix + '_night'))
    .addBands(day.count().rename(prefix + '_day_n')).addBands(night.count().rename(prefix + '_night_n'))};
}

function modis(area, year) {
  var region = rect(area, 'context'), bands = [];
  windowsFor('modis', year).forEach(function (win) {
    var d = windowDates(win, year);
    var t = modisLST('MODIS/061/MOD11A1', 'terra', d, region), a = modisLST('MODIS/061/MYD11A1', 'aqua', d, region);
    provenance(area, 'modis_terra', year, win, t.col, d);
    provenance(area, 'modis_aqua', year, win, a.col, d);
    bands.push(suffix(t.img.addBands(a.img), win));
  });
  return {img: ee.Image.cat(bands), nBands: bands.length * 8};
}

function era5(area, year) {
  var region = rect(area, 'context'), bands = [];
  windowsFor('era5', year).forEach(function (win) {
    var d = windowDates(win, year);
    var daily = ee.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR').filterBounds(region).filterDate(d[0], d[1]);
    // monthly aggregates cover whole months only, so the short event windows use the daily aggregates throughout
    var t = daily.select('temperature_2m').map(function (i) { return i.subtract(273.15); });
    var means = daily.select(['temperature_2m', 'dewpoint_temperature_2m', 'u_component_of_wind_10m', 'v_component_of_wind_10m'])
      .mean();
    var img = means.select('temperature_2m').subtract(273.15).rename('t2m')
      .addBands(means.select('dewpoint_temperature_2m').subtract(273.15).rename('d2m'))
      .addBands(means.select('u_component_of_wind_10m').rename('u10'))
      .addBands(means.select('v_component_of_wind_10m').rename('v10'))
      .addBands(t.max().rename('t2m_max_daily')).addBands(t.min().rename('t2m_min_daily'))
      .addBands(daily.select('total_precipitation_sum').sum().multiply(1000).rename('precip_mm'))
      .addBands(daily.select('surface_solar_radiation_downwards_sum').sum().divide(1e6).rename('ssrd_MJm2'))
      .addBands(t.map(function (i) { return ee.Image(CONFIG.hddBase).subtract(i).max(0); }).sum().rename('HDD'))
      .addBands(t.map(function (i) { return i.subtract(CONFIG.cddBase).max(0); }).sum().rename('CDD'));
    provenance(area, 'era5', year, win, daily, d);
    bands.push(suffix(img, win));
  });
  return {img: ee.Image.cat(bands), nBands: bands.length * 10};
}

function viirs(area, year) {
  var region = rect(area, 'context'), bands = [];
  windowsFor('viirs', year).forEach(function (win) {
    var d = windowDates(win, year);
    var col = ee.ImageCollection('NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG').filterBounds(region).filterDate(d[0], d[1]);
    var rad = col.map(function (i) { return i.select('avg_rad').updateMask(i.select('cf_cvg').gt(0)); });
    provenance(area, 'viirs', year, win, col, d);
    bands.push(suffix(rad.median().rename('avg_rad').addBands(rad.count().rename('n')), win));
  });
  return {img: ee.Image.cat(bands), nBands: bands.length * 2};
}

function staticLayers(area) {
  var wc = ee.ImageCollection('ESA/WorldCover/v200').first().select('Map').rename('worldcover_2021');
  var dem = ee.ImageCollection('COPERNICUS/DEM/GLO30').filterBounds(rect(area, 'context')).select('DEM').mosaic()
    .rename('elevation_m');
  var ghsl = ee.Image('JRC/GHSL/P2023A/GHS_BUILT_H/2018').select('built_height').rename('built_height_2018_m')
    .addBands(ee.Image('JRC/GHSL/P2023A/GHS_BUILT_V/2020').select('built_volume_total').rename('built_volume_2020_m3'));
  return [
    {name: 'worldcover_10m', img: wc, scale: 10, extent: 'core', type: 'int16', nBands: 1},
    {name: 'dem_30m', img: dem, scale: 30, extent: 'context', type: 'float', nBands: 1},
    {name: 'ghsl_100m', img: ghsl, scale: 100, extent: 'context', type: 'float', nBands: 2}
  ];
}

// ---------------------------------------------------------------- build the batch
var BUILD = {
  s2: {fn: s2, scale: 10, extent: 'core', type: 'int16'},
  s1: {fn: s1, scale: 10, extent: 'core', type: 'int16'},
  landsat: {fn: landsat, scale: 30, extent: 'context', type: 'int16'},
  modis: {fn: modis, scale: 1000, extent: 'context', type: 'int16'},
  era5: {fn: era5, scale: 1000, extent: 'context', type: 'float'},
  viirs: {fn: viirs, scale: 500, extent: 'context', type: 'float'}
};

CONFIG.areas.forEach(function (area) {
  if (CONFIG.products.indexOf('static') >= 0) {
    staticLayers(area).forEach(function (s) {
      addExport(s.img, area, ['gbem', CONFIG.version, area, s.name].join('_'), s.scale, s.extent, s.type, s.nBands);
    });
  }
  CONFIG.years.forEach(function (year) {
    Object.keys(BUILD).forEach(function (p) {
      if (CONFIG.products.indexOf(p) < 0) return;
      var b = BUILD[p], r = b.fn(area, year);
      var name = ['gbem', CONFIG.version, area, p, b.scale + 'm', year].join('_');
      addExport(r.img, area, name, b.scale, b.extent, b.type, r.nBands);
    });
  });
});

var tag = CONFIG.areas.join('-') + '_' + CONFIG.years.join('-');
print('GBEM ' + CONFIG.version + (CONFIG.dryRun ? ' - DRY RUN (no tasks created)' : ' - export tasks created') +
      ': ' + PLAN.length + ' images', PLAN);
var prov = ee.FeatureCollection(PROVENANCE.slice());   // a copy: the preview below adds to PROVENANCE
print('Input scenes per composite and window', prov);
if (!CONFIG.dryRun) {
  Export.table.toDrive({collection: prov, description: ['gbem', CONFIG.version, 'provenance', tag].join('_'),
                        folder: CONFIG.driveFolder, fileFormat: 'CSV'});
}

// ---------------------------------------------------------------- preview (first area and year)
var pa = CONFIG.areas[0], py = CONFIG.years[0];
Map.centerObject(rect(pa, 'core'), 10);
Map.addLayer(ee.Image().paint(rect(pa, 'context'), 0, 2), {palette: ['808080']}, pa + ' context extent');
Map.addLayer(ee.Image().paint(rect(pa, 'core'), 0, 2), {palette: ['ff0000']}, pa + ' core extent');
if (CONFIG.products.indexOf('s2') >= 0) {
  Map.addLayer(s2(pa, py).img, {bands: ['B4_annual', 'B3_annual', 'B2_annual'], min: 0, max: 1800}, 'S2 ' + py + ' annual', false);
}
if (CONFIG.products.indexOf('landsat') >= 0) {
  Map.addLayer(landsat(pa, py).img.select('LST_summer'), {min: 1500, max: 4000, palette: ['313695', 'ffffbf', 'a50026']},
               'Landsat LST ' + py + ' summer (deg C x 100)', false);
}
