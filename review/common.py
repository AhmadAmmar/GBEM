"""Shared dictionaries and helpers (coding rules, normalisation, I/O)."""
import json, re, unicodedata
import pandas as pd

# ---------------------------------------------------------------------------
# Screening dictionaries (applied to title + abstract [+ keywords], lower-case)
# ---------------------------------------------------------------------------
# Eligibility is tested on title + abstract. Every criterion has to be met positively (population, outcome,
# exposure, scale); keywords alone are not enough, because index keywords are assigned by the database.
BUILT = r"building|dwelling|\bhous(e|es|ing)\b|residential|built environment|\bhomes?\b|household|apartment"
EFF = (r"energy[- ]efficien|energy performance|energy rating|energy label|energy class|energy certificat|"
       r"\bepcs?\b|building energy rating|\bsap (rating|score)|thermal performance|"
       r"(heating|cooling) (and (heating|cooling) )?(demand|load|energy|consumption|requirement|need)|space heating|space cooling|energy demand|"
       r"energy use intensity|\beui\b|energy benchmark|building envelope|thermal envelope|"
       r"(thermal|wall|roof|loft|cavity|building|envelope) insulation|insulation (level|thickness|quality|status)|heat loss|"
       r"u-value|thermal transmittance|retrofit|(energy|building|thermal|deep) renovation|hard-to-decarboni|energy poverty|fuel poverty|"
       r"buildings?'? energy|energy (consumption|use|demand)s? (of|in|for) (\w+ ){0,3}(building|dwelling|hous|residential|home)|"
       r"(residential|household|domestic) (energy|electricity|gas|heat)|\bubem\b")
# geospatial or remote-sensing data source or method named in the title or abstract
GEO = (r"remote sens|remotely sensed|earth observation|satellite[- ](imag|data|observ|remote|thermal|deriv|based|product|measure)|"
       r"sentinel-?[123]|landsat|modis|\baster\b|ecostress|worldview|planetscope|lidar|light detection and ranging|point clouds?|laser scan|"
       r"aerial (imag|photo|thermograph|survey|infrared|lidar|laser|thermal|view)|orthophoto|overhead imag|"
       r"airborne (lidar|laser|thermal|thermograph|imag|remote|hyperspectral|infrared|survey|data|sens)|"
       r"\buavs?\b|\buas\b|drones?\b|unmanned aerial|thermal infrared|thermal (imag|camera)|thermograph|infrared imag|"
       r"land surface temperature|\blst\b|synthetic aperture radar|\binsar\b|street[- ]?view|street-level imag|streetscape|mapillary|"
       r"fa[cç]ade imag|\bgis\b|geographic(al)? information (system|science)|geospatial|geo-spatial|spatial data|geodata|geo-?referenc|"
       r"spatial analys|spatial(ly)? (autocorrelat|regression|statistic|cluster|interpolat|explicit|resolved|join)|geographically weighted|"
       r"kriging|hot ?spot analysis|3d city model|citygml|cityjson|digital (surface|elevation|terrain) model|\bdsm\b|"
       r"building footprint|footprint (data|polygon|area)|openstreetmap|\bosm\b|cadastr|\blod\s?[0-4]\b|night-?time light|"
       r"hyperspectral|multispectral|photogrammetr|google earth|ordnance survey|local climate zone|\blczs?\b|"
       r"energy mapp?ing|energy maps?\b|heat (demand )?maps?\b|heat atlas|energy atlas")
# urban-climate and urban-form terms describe the setting; without a term of GEO they do not make a study eligible
CONTEXT = (r"urban heat island|\buhis?\b|urban morpholog|urban form|land use|land cover|\bwrf\b|mesoscale|urban climate|"
           r"microclimat|urban canopy|urban densit")
PV = r"photovoltaic|\bpv\b|solar (potential|energy potential|irradiance|radiation potential)|rooftop solar|wind (energy|power|turbine)"
OUTDOOR = r"outdoor thermal comfort|pedestrian|thermal sensation|\butci\b|\bpet\b"
INDOOR = r"indoor positioning|occupant localization|indoor air quality|pm2\.5|pm10|wi-?fi|indoor temperature|laboratory|test cell|hot box"
# close-range acquisition and single-asset models: eligible only when applied to many buildings
CLOSE = (r"\buavs?\b|\buas\b|drones?\b|unmanned aerial|handheld|close[- ]range|thermograph|thermal (imag|camera)|infrared imag|\birt\b|"
         r"terrestrial laser|laser scan|photogrammetr|\bbim\b|digital twin")
# wide-area sources cover many buildings by construction
WIDE = (r"remote sens|remotely sensed|earth observation|satellite|sentinel-?[123]|landsat|modis|\baster\b|ecostress|lidar|"
        r"aerial (imag|photo|thermograph|survey|infrared|lidar|laser|thermal|view)|orthophoto|overhead imag|airborne|street[- ]?view|street-level imag|"
        r"land surface temperature|\blst\b|night-?time light|\bgis\b|geographic(al)? information (system|science)|geospatial|geo-spatial|"
        r"spatial data|spatial analys|geographically weighted|3d city model|citygml|cityjson|building footprint|openstreetmap|\bosm\b|cadastr|"
        r"local climate zone|\blczs?\b|energy mapp?ing|energy maps?\b|heat (demand )?maps?\b|heat atlas|energy atlas")
MANY = (r"building stock|housing stock|neighbou?rhood|city[- ]?wide|urban[- ]scale|city[- ]scale|district[- ]scale|large[- ]scale|"
        r"\d[\d,]{2,} (\w+ ){0,2}(buildings|dwellings|homes|houses|properties)|(hundreds?|thousands?|millions?) of (\w+ ){0,2}(buildings|dwellings|homes|houses)")
# the rating itself is estimated (with or without a learning method)
RATING_EST = (r"(predict|estimat|classif|infer|forecast)\w* (\w+ ){0,6}(energy (performance |efficiency )?(certificat|rating|label|class)|\bepcs?\b|building energy rating)|"
              r"(energy (performance |efficiency )?(certificat\w*|ratings?|labels?|class\w*)|\bepcs?|building energy ratings?) (\w+ ){0,2}(prediction|estimation|classification)")
# an article that is a review by its title is treated as a review whatever the database calls it
REVIEW_TITLE = (r"\b(a|systematic|literature|critical|comprehensive|scoping|state[- ]of[- ]the[- ]art|narrative|bibliometric) review\b|"
                r":\s*(a )?review\b|^review (of|on)\b|\breview and (perspective|outlook|prospect)|bibliometric analysis|state of the art (and|review)|meta-analysis")
RATING = (r"\bepcs?\b|energy performance certificat|\bbers?\b|building energy rating|energy label|energy rating|energy class|rating band|\bsap (rating|score)|"
          r"energy efficiency (classif|class|rating|band|grade)\w*|efficiency (band|grade)s?\b|energy grade")
ML = (r"machine learning|deep learning|neural network|random forest|xgboost|gradient boost|lightgbm|catboost|"
      r"convolutional|\bcnns?\b|support vector|\bsvm\b|k-nearest|\bknn\b|vision transformer|transformer[- ](based|model|network|architecture)|lstm|artificial intelligence|"
      r"decision tree|ensemble learning|transfer learning|vision[- ]language|large language|foundation model|"
      r"attention (mechanism|fusion|network)|fusion network|dual-branch|multi-branch|graph neural|\bgnns?\b|autoencoder")

MODALITY = {
    "Optical satellite": r"satellite imag|multispectral|sentinel-?2|landsat|worldview|quickbird|planetscope|high-resolution (satellite|remote)|\bndvi\b|very high resolution",
    "Thermal / LST": r"thermal infrared|thermograph|land surface temperature|\blst\b|thermal imag|ecostress|infrared imag|\btir\b",
    "SAR": r"synthetic aperture radar|\bsar\b|sentinel-?1",
    "LiDAR / 3D": r"lidar|point cloud|3d city|citygml|digital surface model|\bdsm\b|building height|3d building|\blod\s?[12]",
    "Street-level imagery": r"street[- ]?view|street-level|streetscape|mapillary|fa[cç]ade imag|\bsvi\b",
    "Aerial / UAV": r"aerial|orthophoto|\buav|drone|unmanned aerial|airborne",
    "GIS / cadastral": r"\bgis\b|geographic(al)? information|cadastr|footprint|openstreetmap|\bosm\b|land use|spatial data infrastructure|building (register|registry)",
    "Climate / LCZ / UHI": r"local climate zone|\blczs?\b|urban heat island|\buhis?\b|microclimat|reanalysis|weather data|degree[- ]day",
}
TARGET = {
    "Rating / label": RATING,
    "Heating / cooling demand": r"heating (demand|load|energy)|cooling (demand|load|energy)|space heating|space cooling|energy demand",
    "Energy use intensity / benchmark": r"energy use intensity|\beui\b|benchmark|energy consumption|energy use\b",
    "Envelope / heat loss": r"heat loss|u-value|thermal transmittance|insulation|building envelope|thermal envelope|thermal performance|thermal bridge",
    "Retrofit potential": r"retrofit|renovation|refurbish",
}
METHOD = {
    "Machine / deep learning": ML,
    "Physics-based simulation / UBEM": r"energyplus|simulation|\bubem\b|urban building energy model|citysim|trnsys|dynamic thermal|archetype|bottom-up",
    "Statistical / spatial statistics": r"regression|correlation|statistical|geographically weighted|kriging|spatial autocorrelation|anova",
}
VALIDATION = {
    "Spatial / cross-city transfer": r"spatial cross[- ]validation|spatial block|leave[- ]one[- ](city|region|area)[- ]out|transferab|other cities|unseen (cit|region|area)|cross-city|different cities|across cities|held[- ]out cit",
    "Temporal hold-out": r"temporal (hold|validation|split)|future (year|period)|different years|out-of-time",
    "External / independent data": r"external validation|independent (dataset|data|test)|validated (against|with) (measured|metered|official)",
    "Cross-validation / random split": r"cross[- ]validation|k-fold|\d+-fold|hold-?out|train(ing)?[- /]test split|test set|testing set",
}

# keyword thesaurus (author keywords)
THESAURUS = {
    r"^(urban )?heat islands?( effect)?$|^uhis?$|^urban heat island \(uhi\)$": "urban heat island",
    r"^gis$|^geographic(al)? information systems?( \(gis\))?$": "GIS",
    r"^lidar$|^light detection and ranging": "LiDAR", r"^remote sensing$|^remotely sensed": "remote sensing",
    r"^energy performance certificates?( \(epcs?\))?$|^epcs?$": "energy performance certificate",
    r"^urban building energy model(l)?ing( \(ubem\))?$|^ubem$": "urban building energy modelling",
    r"^local climate zones?( \(lczs?\))?$|^lczs?$": "local climate zone",
    r"^land surface temperatures?( \(lst\))?$|^lst$": "land surface temperature",
    r"^machine learning( \(ml\))?$": "machine learning", r"^deep learning$": "deep learning",
    r"^building energy simulations?$|^building energy model(l)?ing$|^building energy models?$": "building energy modelling",
    r"^energy efficien(cy|t)$": "energy efficiency", r"^energy performances?$|^building energy performance$": "energy performance",
    r"^energy consumptions?$|^building energy consumption$": "energy consumption", r"^energy demands?$": "energy demand",
    r"^cooling (energy )?demands?$|^cooling loads?$": "cooling demand", r"^heating (energy )?demands?$|^heating loads?$": "heating demand",
    r"^thermal comforts?$|^outdoor thermal comfort$": "thermal comfort", r"^urban morpholog(y|ies)$": "urban morphology",
    r"^urban forms?$": "urban form", r"^microclimates?$|^urban microclimates?$": "microclimate",
    r"^energyplus$": "EnergyPlus", r"^retrofit(ting)?$|^energy retrofit(ting)?$|^building retrofit(ting)?$": "retrofit",
    r"^climate changes?$": "climate change", r"^infrared thermography$|^thermography$|^thermal imaging$": "thermography",
    r"^random forests?$": "random forest", r"^street view( imagery| images)?$|^street-level imagery$": "street view imagery",
    r"^buildings?$": "building", r"^urban planning$": "urban planning", r"^sustainabilit(y|ies)$": "sustainability",
    r"^point clouds?$": "point cloud", r"^convolutional neural networks?( \(cnns?\))?$|^cnns?$": "convolutional neural network",
}
BLOCKS = {
    "A. Built form and urban context": r"urban|building|city|cities|morpholog|form|density|street|canyon|neighbo|district|housing|residential|typolog|height",
    "B. Energy performance": r"energy|thermal|heating|cooling|retrofit|efficien|insulation|envelope|comfort|epc|performance certificate|demand|load|poverty",
    "C. Remote sensing and geospatial": r"remote sensing|gis|lidar|satellite|landsat|sentinel|land surface|urban heat island|local climate|spatial|imag|street view|thermograph|infrared|uav|drone|aerial|point cloud|3d|citygml|geospatial",
    "D. Methods and validation": r"machine learning|deep learning|random forest|neural|simulation|model|regression|energyplus|optimi|validation|calibration|uncertainty|sensitivity|cnn|xgboost|cluster|transfer learning",
}

COUNTRIES = ["United Kingdom", "England", "Scotland", "Wales", "Northern Ireland", "Ireland", "China", "Hong Kong",
    "United States", "USA", "Canada", "Italy", "Spain", "France", "Germany", "Netherlands", "Belgium", "Switzerland",
    "Austria", "Portugal", "Greece", "Sweden", "Norway", "Denmark", "Finland", "Poland", "Czech", "Turkey", "Türkiye",
    "Iran", "Israel", "Egypt", "Saudi Arabia", "United Arab Emirates", "Qatar", "India", "Pakistan", "Bangladesh",
    "Japan", "Korea", "Singapore", "Malaysia", "Indonesia", "Thailand", "Vietnam", "Australia", "New Zealand", "Brazil",
    "Chile", "Mexico", "Colombia", "Argentina", "South Africa", "Nigeria", "Morocco", "Algeria", "Kenya", "Latvia",
    "Lithuania", "Estonia", "Slovenia", "Croatia", "Serbia", "Romania", "Hungary", "Cyprus", "Luxembourg", "Taiwan",
    "Russia", "Kazakhstan", "Jordan", "Lebanon", "Iraq", "Ethiopia", "Ghana", "Peru", "Ecuador", "Sri Lanka", "Nepal"]
CITY2C = {"london": "United Kingdom", "glasgow": "United Kingdom", "edinburgh": "United Kingdom", "sheffield": "United Kingdom",
    "manchester": "United Kingdom", "belfast": "United Kingdom", "cambridge, uk": "United Kingdom", "peterborough": "United Kingdom",
    "dublin": "Ireland", "beijing": "China", "shanghai": "China", "wuhan": "China", "shenzhen": "China", "guangzhou": "China",
    "chongqing": "China", "nanjing": "China", "xi'an": "China", "tianjin": "China", "hangzhou": "China", "harbin": "China",
    "chengdu": "China", "hong kong": "China", "new york": "United States", "los angeles": "United States", "chicago": "United States",
    "phoenix": "United States", "boston": "United States", "seattle": "United States", "san francisco": "United States",
    "rome": "Italy", "milan": "Italy", "turin": "Italy", "naples": "Italy", "bologna": "Italy", "madrid": "Spain",
    "barcelona": "Spain", "seville": "Spain", "valencia": "Spain", "paris": "France", "lyon": "France", "berlin": "Germany",
    "munich": "Germany", "rotterdam": "Netherlands", "amsterdam": "Netherlands", "brussels": "Belgium", "geneva": "Switzerland",
    "zurich": "Switzerland", "vienna": "Austria", "lisbon": "Portugal", "athens": "Greece", "stockholm": "Sweden",
    "oslo": "Norway", "copenhagen": "Denmark", "helsinki": "Finland", "istanbul": "Turkey", "ankara": "Turkey",
    "tehran": "Iran", "cairo": "Egypt", "riyadh": "Saudi Arabia", "dubai": "United Arab Emirates", "abu dhabi": "United Arab Emirates",
    "delhi": "India", "mumbai": "India", "tokyo": "Japan", "osaka": "Japan", "seoul": "South Korea", "singapore": "Singapore",
    "kuala lumpur": "Malaysia", "sydney": "Australia", "melbourne": "Australia", "brisbane": "Australia", "toronto": "Canada",
    "montreal": "Canada", "vancouver": "Canada", "sao paulo": "Brazil", "santiago": "Chile", "taipei": "Taiwan",
    "bangkok": "Thailand", "hanoi": "Vietnam"}
CNORM = {"England": "United Kingdom", "Scotland": "United Kingdom", "Wales": "United Kingdom", "Northern Ireland": "United Kingdom",
         "UK": "United Kingdom", "USA": "United States", "Türkiye": "Turkey", "Korea": "South Korea", "Republic of Korea": "South Korea",
         "Czech": "Czech Republic", "Hong Kong": "China", "Macao": "China", "Macau": "China", "Russian Federation": "Russia",
         "Viet Nam": "Vietnam", "Peoples R China": "China", "U Arab Emirates": "United Arab Emirates"}


def has(pattern, s):
    return re.search(pattern, s or "") is not None


def codes(text, dic):
    return "; ".join(k for k, p in dic.items() if has(p, text))


def norm_title(t):
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def norm_doi(d):
    if not isinstance(d, str) or not d.strip():
        return ""
    d = d.strip().lower()
    return re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", d)


def norm_kw(k):
    k = k.strip().lower()
    for p, v in THESAURUS.items():
        if re.search(p, k):
            return v
    return k


def dump(obj, path):
    json.dump(obj, open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False, default=str)


def load(path):
    return json.load(open(path, encoding="utf-8"))


def read_csv(path):
    return pd.read_csv(path, encoding="utf-8-sig")
