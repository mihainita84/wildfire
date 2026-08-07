from __future__ import annotations

import io
import os
import tempfile
import zipfile
from datetime import date
from urllib.parse import urlencode

import geopandas as gpd
import requests
from PIL import Image, ImageDraw

EFFIS_WMS = "https://maps.effis.emergency.copernicus.eu/effis"
EFFIS_WFS = EFFIS_WMS
EFFIS_FWI_LAYER = "ecmwf007.fwi"
EFFIS_FORECAST_LAYERS = {
    "FWI": "ecmwf007.fwi",
    "FFMC": "ecmwf007.ffmc",
    "DMC": "ecmwf007.dmc",
    "DC": "ecmwf007.dc",
    "ISI": "ecmwf007.isi",
    "BUI": "ecmwf007.bui",
    "ANOMALY": "ecmwf007.anomaly",
    "RANKING": "ecmwf007.rankingfwi",
}
EFFIS_FORECAST_INFO = {
    "FWI": {
        "ro": "Indice meteo general al pericolului de incendiu și al intensității potențiale.",
        "en": "Overall fire-weather danger indicator and proxy for potential fire intensity.",
    },
    "FFMC": {
        "ro": "Fine Fuel Moisture Code: uscarea combustibililor fini de suprafață și ușurința aprinderii.",
        "en": "Fine Fuel Moisture Code: dryness of fine surface fuels and ease of ignition.",
    },
    "DMC": {
        "ro": "Duff Moisture Code: uscarea stratului organic intermediar și a combustibililor moderat adânci.",
        "en": "Duff Moisture Code: drying of the intermediate organic layer and moderately deep fuels.",
    },
    "DC": {
        "ro": "Drought Code: uscarea pe termen lung a stratului organic profund și efectul secetei.",
        "en": "Drought Code: long-term drying of deep organic layers and drought effects.",
    },
    "ISI": {
        "ro": "Initial Spread Index: potențialul de propagare inițială, influențat în special de vânt și FFMC.",
        "en": "Initial Spread Index: initial spread potential, driven especially by wind and FFMC.",
    },
    "BUI": {
        "ro": "Build Up Index: cantitatea de combustibil disponibil pentru ardere, derivată din DMC și DC.",
        "en": "Build Up Index: amount of fuel available for combustion, derived from DMC and DC.",
    },
    "ANOMALY": {
        "ro": "Anomalia FWI: abaterea față de media istorică de aproximativ 40 de ani.",
        "en": "FWI anomaly: departure from the approximately 40-year historical mean.",
    },
    "RANKING": {
        "ro": "Ranking FWI: percentila valorii curente în raport cu seria istorică de aproximativ 40 de ani.",
        "en": "FWI ranking: percentile of the current value relative to the approximately 40-year historical series.",
    },
}

EFFIS_CLASS_THRESHOLDS = [
    {"Class": "Low", "FWI": "< 11.2", "FFMC": "< 82.7", "DMC": "< 15.7", "DC": "< 256.1", "ISI": "< 3.2", "BUI": "< 24.2", "Anomaly": "< 0.0", "Ranking": "< 80.0"},
    {"Class": "Moderate", "FWI": "11.2–21.3", "FFMC": "82.7–86.1", "DMC": "15.7–27.9", "DC": "256.1–334.1", "ISI": "3.2–5.0", "BUI": "24.2–40.7", "Anomaly": "0.0–0.5", "Ranking": "80.0–90.0"},
    {"Class": "High", "FWI": "21.3–38.0", "FFMC": "86.1–89.2", "DMC": "27.9–53.1", "DC": "334.1–450.6", "ISI": "5.0–7.5", "BUI": "40.7–73.3", "Anomaly": "0.5–1.0", "Ranking": "90.0–95.0"},
    {"Class": "Very High", "FWI": "38.0–50.0", "FFMC": "89.2–93.0", "DMC": "53.1–83.6", "DC": "450.6–600.0", "ISI": "7.5–13.4", "BUI": "73.3–133.1", "Anomaly": "1.0–1.5", "Ranking": "95.0–98.0"},
    {"Class": "Extreme", "FWI": "50.0–70.0", "FFMC": "93.0–96.0", "DMC": "83.6–160.7", "DC": "600.0–749.4", "ISI": "13.4–26.8", "BUI": "133.1–193.1", "Anomaly": "1.5–2.5", "Ranking": "98.0–99.0"},
    {"Class": "Very Extreme", "FWI": "> 70.0", "FFMC": "> 96.0", "DMC": "> 160.7", "DC": "> 749.4", "ISI": "> 26.8", "BUI": "> 193.1", "Anomaly": "> 2.5", "Ranking": "> 99.0"},
]



def fwi_wms_options(day: date | str) -> dict:
    day_text = day.isoformat() if hasattr(day, "isoformat") else str(day)
    return {"url": EFFIS_WMS, "layers": EFFIS_FWI_LAYER, "time": day_text}


def fetch_burned_areas(aoi: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    west, south, east, north = aoi.total_bounds
    params = {
        "service": "WFS",
        "version": "1.1.0",
        "request": "GetFeature",
        "typeName": "ms:modis.ba.poly",
        "outputformat": "SHAPEZIP",
        "bbox": f"{west},{south},{east},{north},EPSG:4326",
    }
    r = requests.get(EFFIS_WFS, params=params, timeout=75)
    r.raise_for_status()
    if not r.content.startswith(b"PK"):
        raise RuntimeError("EFFIS did not return a ZIP shapefile for burned areas.")

    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            zf.extractall(td)
        shp = next((os.path.join(td, f) for f in os.listdir(td) if f.lower().endswith(".shp")), None)
        if shp is None:
            raise RuntimeError("No shapefile found in EFFIS response.")
        gdf = gpd.read_file(shp).to_crs(4326)

    if gdf.empty:
        return gdf
    geom = aoi.geometry.iloc[0]
    return gdf[gdf.geometry.intersects(geom)].copy()


def summarize_burned_areas(burned: gpd.GeoDataFrame, aoi: gpd.GeoDataFrame) -> dict:
    if burned.empty:
        return {"burned_area_ha": 0.0, "fire_perimeters": 0}
    clipped = gpd.overlay(burned, aoi[["geometry"]], how="intersection", keep_geom_type=False)
    if clipped.empty:
        return {"burned_area_ha": 0.0, "fire_perimeters": 0}
    area = clipped.to_crs(3035).area.sum() / 10_000.0
    return {"burned_area_ha": float(area), "fire_perimeters": int(len(burned))}


def _context_bounds(aoi: gpd.GeoDataFrame, pad_frac: float = 0.20, min_pad_deg: float = 0.01) -> tuple[float, float, float, float]:
    geom = aoi.to_crs(4326).geometry.iloc[0]
    west, south, east, north = geom.bounds
    dx = max(east - west, min_pad_deg)
    dy = max(north - south, min_pad_deg)
    pad_x = dx * pad_frac + min_pad_deg
    pad_y = dy * pad_frac + min_pad_deg
    return west - pad_x, south - pad_y, east + pad_x, north + pad_y


def _draw_aoi_outline(img: Image.Image, aoi_bounds: tuple[float, float, float, float], ctx_bounds: tuple[float, float, float, float]) -> Image.Image:
    draw = ImageDraw.Draw(img)
    w, s, e, n = ctx_bounds
    aw, as_, ae, an = aoi_bounds
    def px(x):
        return int((x - w) / max(1e-9, e - w) * (img.width - 1))
    def py(y):
        return int((n - y) / max(1e-9, n - s) * (img.height - 1))
    pts = [(px(aw), py(as_)), (px(ae), py(as_)), (px(ae), py(an)), (px(aw), py(an)), (px(aw), py(as_))]
    draw.line(pts, fill=(0, 0, 0, 255), width=3)
    return img


def effis_thumbnail_url(
    aoi: gpd.GeoDataFrame,
    day: date | str,
    layer_name: str,
    size: int = 520,
) -> str:
    """Return a direct WMS GetMap URL for browser-side thumbnail rendering.

    Using a direct <img> URL avoids Streamlit server-side WMS/proxy failures.
    """
    aoi = aoi.to_crs(4326)
    west, south, east, north = _context_bounds(aoi, pad_frac=0.28, min_pad_deg=0.02)
    day_text = day.isoformat() if hasattr(day, "isoformat") else str(day)
    params = {
        "LAYERS": layer_name,
        "FORMAT": "image/png",
        "TRANSPARENT": "false",
        "BGCOLOR": "0xF7F7F7",
        "SINGLETILE": "true",
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "STYLES": "",
        "SRS": "EPSG:4326",
        "BBOX": f"{west},{south},{east},{north}",
        "WIDTH": str(size),
        "HEIGHT": str(size),
        "TIME": day_text,
    }
    return f"{EFFIS_WMS}?{urlencode(params)}"


def effis_thumbnail(aoi: gpd.GeoDataFrame, day: date | str, layer_name: str, size: int = 420) -> bytes:
    aoi = aoi.to_crs(4326)
    ctx_bounds = _context_bounds(aoi)
    aoi_bounds = tuple(aoi.total_bounds)
    west, south, east, north = ctx_bounds
    day_text = day.isoformat() if hasattr(day, "isoformat") else str(day)
    params = {
        "service": "WMS",
        "version": "1.1.1",
        "request": "GetMap",
        "layers": layer_name,
        "styles": "",
        "format": "image/png",
        "transparent": "TRUE",
        "srs": "EPSG:4326",
        "bbox": f"{west},{south},{east},{north}",
        "width": size,
        "height": size,
        "time": day_text,
    }
    r = requests.get(EFFIS_WMS, params=params, timeout=75)
    r.raise_for_status()
    if "image" not in (r.headers.get("content-type") or "").lower():
        raise RuntimeError("EFFIS WMS did not return an image.")
    overlay = Image.open(io.BytesIO(r.content)).convert("RGBA")
    img = Image.alpha_composite(Image.new("RGBA", overlay.size, (255, 255, 255, 255)), overlay)
    img = _draw_aoi_outline(img, aoi_bounds, ctx_bounds)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
