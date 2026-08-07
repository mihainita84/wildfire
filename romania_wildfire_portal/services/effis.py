from __future__ import annotations

import io
import os
import tempfile
import zipfile
from datetime import date

import geopandas as gpd
import requests
from PIL import Image, ImageDraw

EFFIS_WMS = "https://maps.effis.emergency.copernicus.eu/effis"
EFFIS_WFS = EFFIS_WMS
EFFIS_FWI_LAYER = "ecmwf007.fwi"
EFFIS_FORECAST_LAYERS = {
    "FWI": "ecmwf007.fwi",
    "FFMC": "ecmwf007.ffmc",
    "ISI": "ecmwf007.isi",
    "BUI": "ecmwf007.bui",
    "DMC": "ecmwf007.dmc",
    "DC": "ecmwf007.dc",
}
EFFIS_FORECAST_INFO = {
    "FWI": {
        "ro": "Indicele meteo de incendiu; indicator general al potențialei intensități a incendiului.",
        "en": "Fire Weather Index; overall indicator of potential fire intensity.",
    },
    "FFMC": {
        "ro": "Fine Fuel Moisture Code; arată uscarea combustibililor fini de suprafață.",
        "en": "Fine Fuel Moisture Code; indicates dryness of fine surface fuels.",
    },
    "ISI": {
        "ro": "Initial Spread Index; sugerează viteza inițială de propagare a focului.",
        "en": "Initial Spread Index; suggests the expected initial rate of fire spread.",
    },
    "BUI": {
        "ro": "Build Up Index; exprimă cantitatea de combustibil disponibil pentru ardere.",
        "en": "Build Up Index; expresses the amount of fuel available for combustion.",
    },
    "DMC": {
        "ro": "Duff Moisture Code; reflectă uscarea stratului organic intermediar.",
        "en": "Duff Moisture Code; reflects drying of the intermediate organic layer.",
    },
    "DC": {
        "ro": "Drought Code; reflectă uscarea și seceta în straturile organice profunde.",
        "en": "Drought Code; reflects drought and drying in deep organic layers.",
    },
}


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
