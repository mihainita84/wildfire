from __future__ import annotations

import io
import os
import tempfile
import zipfile
from datetime import date, timedelta
from urllib.parse import urlencode

import geopandas as gpd
import requests
from PIL import Image, ImageStat

EFFIS_WMS = "https://maps.effis.emergency.copernicus.eu/effis"
EFFIS_WFS = EFFIS_WMS
EFFIS_FWI_LAYER = "ecmwf007.fwi"
ROMANIA_FWI_BOUNDS = [[43.0, 19.5], [49.0, 30.5]]  # [[south, west], [north, east]]


def _fwi_params(day: date, width: int = 1200, height: int = 800) -> dict:
    return {
        "LAYERS": EFFIS_FWI_LAYER,
        "FORMAT": "image/png",
        "TRANSPARENT": "true",
        "SINGLETILE": "false",
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "STYLES": "",
        "SRS": "EPSG:4326",
        "BBOX": "19.5,43.0,30.5,49.0",
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "TIME": day.isoformat(),
    }


def fwi_getmap_url(day: date) -> str:
    return f"{EFFIS_WMS}?{urlencode(_fwi_params(day))}"


def _png_has_visible_data(content: bytes) -> bool:
    """Reject empty/fully transparent WMS responses."""
    try:
        img = Image.open(io.BytesIO(content)).convert("RGBA")
        alpha = img.getchannel("A")
        alpha_extrema = alpha.getextrema()
        if alpha_extrema == (0, 0):
            return False
        # At least a small fraction of non-transparent pixels must exist.
        hist = alpha.histogram()
        nonzero = sum(hist[1:])
        total = max(1, img.width * img.height)
        if nonzero / total < 0.002:
            return False
        # A response with visible pixels but no variation is usually an error/blank tile.
        stat = ImageStat.Stat(img.convert("RGB"))
        return any(v > 0.5 for v in stat.var)
    except Exception:
        return False


def fetch_latest_fwi_image(lookback_days: int = 5) -> tuple[bytes, str]:
    """Return the newest non-empty EFFIS ECMWF FWI PNG over Romania.

    EFFIS FWI is time-dependent. The current calendar date can occasionally be
    unavailable while products are being published, so we test a few dates and
    use the newest valid image.
    """
    headers = {"User-Agent": "Romania-Wildfire-Portal/2.0"}
    today = date.today()
    errors: list[str] = []
    for offset in range(max(1, lookback_days)):
        day = today - timedelta(days=offset)
        try:
            r = requests.get(EFFIS_WMS, params=_fwi_params(day), headers=headers, timeout=35)
            r.raise_for_status()
            if r.headers.get("content-type", "").lower().startswith("image/") and _png_has_visible_data(r.content):
                return r.content, day.isoformat()
            if _png_has_visible_data(r.content):
                return r.content, day.isoformat()
            errors.append(f"{day}: empty image")
        except Exception as exc:
            errors.append(f"{day}: {exc}")
    raise RuntimeError("No non-empty EFFIS FWI image found in recent dates. " + "; ".join(errors[-3:]))


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
