from __future__ import annotations

import io
import numpy as np
import geopandas as gpd
import requests
from pyproj import Transformer
from rasterio.io import MemoryFile
from rasterio.mask import mask
from shapely.geometry import mapping

# GEDI L4B is one of the core biomass products exposed through the MAAP ecosystem.
# ORNL DAAC's public OGC service gives the Streamlit app direct online subset access
# without Google Earth Engine or a local global raster.
ORNL_WCS = "https://webmap.ornl.gov/ogcbroker/wcs"
ORNL_WMS = "https://webmap.ornl.gov/ogcbroker/wms"
GEDI_AGBD_LAYER = "2017_1"       # mean aboveground biomass density, Mg/ha
GEDI_AGBD_SE_LAYER = "2017_2"    # standard error, Mg/ha
GEDI_QUALITY_LAYER = "2017_4"    # quality flag; value 2 meets mission requirement
GEDI_RESOLUTION_M = 1000


def _bbox_6933(aoi: gpd.GeoDataFrame) -> tuple[float, float, float, float]:
    west, south, east, north = aoi.to_crs(4326).total_bounds
    transformer = Transformer.from_crs(4326, 6933, always_xy=True)
    return transformer.transform_bounds(west, south, east, north, densify_pts=21)


def _fetch_wcs_layer(layer: str, bbox: tuple[float, float, float, float]) -> bytes:
    xmin, ymin, xmax, ymax = bbox
    # Give the request at least two cells in each direction so very small AOIs work.
    xmin -= GEDI_RESOLUTION_M
    ymin -= GEDI_RESOLUTION_M
    xmax += GEDI_RESOLUTION_M
    ymax += GEDI_RESOLUTION_M
    params = {
        "service": "WCS",
        "version": "1.0.0",
        "request": "GetCoverage",
        "coverage": layer,
        "bbox": f"{xmin},{ymin},{xmax},{ymax}",
        "crs": "EPSG:6933",
        "response_crs": "EPSG:6933",
        "format": "GeoTIFF_FLOAT32",
        "resx": str(GEDI_RESOLUTION_M),
        "resy": str(GEDI_RESOLUTION_M),
    }
    r = requests.get(ORNL_WCS, params=params, timeout=90, headers={"User-Agent": "Romania-Wildfire-Portal/2.0"})
    r.raise_for_status()
    if r.content[:4] in (b"II*\x00", b"MM\x00*"):
        return r.content
    ctype = r.headers.get("content-type", "")
    if "tiff" in ctype.lower():
        return r.content
    text = r.text[:700] if r.content else "empty response"
    raise RuntimeError(f"ORNL GEDI WCS returned {ctype or 'non-TIFF'}: {text}")


def _masked_values(tiff_bytes: bytes, aoi_6933: gpd.GeoDataFrame) -> np.ndarray:
    with MemoryFile(tiff_bytes) as mem:
        with mem.open() as src:
            arr, _ = mask(src, [mapping(aoi_6933.geometry.iloc[0])], crop=True, all_touched=True, filled=False)
            band = arr[0]
            vals = band.compressed().astype("float64")
            nodata = src.nodata
            if nodata is not None:
                vals = vals[vals != nodata]
            return vals[np.isfinite(vals)]


def biomass_stats(aoi: gpd.GeoDataFrame, aoi_area_ha: float | None = None) -> dict:
    """Subset GEDI L4B online and summarize AGBD for the selected polygon."""
    aoi_4326 = aoi.to_crs(4326)
    aoi_6933 = aoi_4326.to_crs(6933)
    bbox = _bbox_6933(aoi_4326)

    mean_bytes = _fetch_wcs_layer(GEDI_AGBD_LAYER, bbox)
    se_bytes = _fetch_wcs_layer(GEDI_AGBD_SE_LAYER, bbox)
    qf_bytes = _fetch_wcs_layer(GEDI_QUALITY_LAYER, bbox)

    mu = _masked_values(mean_bytes, aoi_6933)
    se = _masked_values(se_bytes, aoi_6933)
    qf = _masked_values(qf_bytes, aoi_6933)

    mu = mu[(mu >= 0) & (mu < 5000)]
    se = se[(se >= 0) & (se < 5000)]
    if mu.size == 0:
        return {
            "agb_mean_mg_ha": None,
            "agb_median_mg_ha": None,
            "agb_standard_error_mean_mg_ha": None,
            "gedi_cells": 0,
            "gedi_quality_pct": None,
            "source": "NASA GEDI L4B v2 via MAAP/ORNL OGC WCS",
            "resolution_m": GEDI_RESOLUTION_M,
        }

    mean_agbd = float(np.mean(mu))
    if aoi_area_ha is None:
        aoi_area_ha = float(aoi_6933.area.iloc[0] / 10_000.0)
    high_quality_pct = float(100.0 * np.mean(qf == 2)) if qf.size else None

    return {
        "agb_mean_mg_ha": mean_agbd,
        "agb_median_mg_ha": float(np.median(mu)),
        "agb_p90_mg_ha": float(np.percentile(mu, 90)),
        "agb_standard_error_mean_mg_ha": float(np.mean(se)) if se.size else None,
        "agb_total_aoi_mg_est": float(mean_agbd * aoi_area_ha),
        "gedi_cells": int(mu.size),
        "gedi_quality_pct": high_quality_pct,
        "source": "NASA GEDI L4B v2 via MAAP/ORNL OGC WCS",
        "observation_period": "2019-04-18 to 2021-08-04",
        "resolution_m": GEDI_RESOLUTION_M,
    }
