from __future__ import annotations

import io
import os
import tempfile
import zipfile
from datetime import date

import geopandas as gpd
import requests

EFFIS_WMS = "https://maps.effis.emergency.copernicus.eu/effis"
EFFIS_WFS = EFFIS_WMS
EFFIS_FWI_LAYER = "ecmwf007.fwi"


def fwi_wms_options(day: date | str) -> dict:
    """Options passed directly to Leaflet WMS.

    Rendering in the browser avoids the previous server-side PNG validation step,
    which could reject legitimate EFFIS responses. TIME is mandatory for FWI.
    """
    day_text = day.isoformat() if hasattr(day, "isoformat") else str(day)
    return {
        "url": EFFIS_WMS,
        "layers": EFFIS_FWI_LAYER,
        "time": day_text,
    }


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
