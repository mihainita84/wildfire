from __future__ import annotations

import math
import os
from contextlib import ExitStack

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.mask import mask
from shapely.geometry import mapping, box

WORLDCOVER_WMS = "https://services.terrascope.be/wms/v2"
WORLDCOVER_WMS_LAYER = "WORLDCOVER_2021_MAP"
WORLDCOVER_HTTP_ROOT = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"

CLASSES = {
    10: "Tree cover",
    20: "Shrubland",
    30: "Grassland",
    40: "Cropland",
    50: "Built-up",
    60: "Bare / sparse vegetation",
    70: "Snow and ice",
    80: "Permanent water bodies",
    90: "Herbaceous wetland",
    95: "Mangroves",
    100: "Moss and lichen",
}


def _tile_code(lat0: int, lon0: int) -> str:
    ns = "N" if lat0 >= 0 else "S"
    ew = "E" if lon0 >= 0 else "W"
    return f"{ns}{abs(lat0):02d}{ew}{abs(lon0):03d}"


def _tile_url(lat0: int, lon0: int) -> str:
    code = _tile_code(lat0, lon0)
    return f"{WORLDCOVER_HTTP_ROOT}/ESA_WorldCover_10m_2021_v200_{code}_Map.tif"


def _tile_origins(bounds: tuple[float, float, float, float]):
    west, south, east, north = bounds
    lon_start = math.floor(west / 3) * 3
    lat_start = math.floor(south / 3) * 3
    # subtract epsilon so a boundary exactly on a tile edge does not request an extra tile
    lon_end = math.floor((east - 1e-10) / 3) * 3
    lat_end = math.floor((north - 1e-10) / 3) * 3
    for lat0 in range(lat_start, lat_end + 1, 3):
        for lon0 in range(lon_start, lon_end + 1, 3):
            yield lat0, lon0


def landcover_stats(aoi: gpd.GeoDataFrame, aoi_area_ha: float | None = None) -> dict:
    """Read only intersecting windows from ESA WorldCover public AWS COGs."""
    aoi = aoi.to_crs(4326)
    geom = aoi.geometry.iloc[0]
    if aoi_area_ha is None:
        aoi_area_ha = float(aoi.to_crs(3035).area.iloc[0] / 10_000.0)

    counts: dict[int, int] = {}
    tile_errors: list[str] = []
    valid_pixels = 0

    env_opts = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
        "GDAL_HTTP_MULTIRANGE": "YES",
        "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    }
    with rasterio.Env(**env_opts):
        for lat0, lon0 in _tile_origins(tuple(aoi.total_bounds)):
            tile_geom = box(lon0, lat0, lon0 + 3, lat0 + 3)
            inter = geom.intersection(tile_geom)
            if inter.is_empty:
                continue
            url = _tile_url(lat0, lon0)
            try:
                with rasterio.open(url) as src:
                    data, _ = mask(src, [mapping(inter)], crop=True, all_touched=True, filled=False)
                    arr = data[0]
                    vals = arr.compressed()
                    if src.nodata is not None:
                        vals = vals[vals != src.nodata]
                    vals = vals[vals != 0]
                    if vals.size == 0:
                        continue
                    u, c = np.unique(vals.astype(int), return_counts=True)
                    for klass, n in zip(u, c):
                        counts[int(klass)] = counts.get(int(klass), 0) + int(n)
                    valid_pixels += int(vals.size)
            except Exception as exc:
                tile_errors.append(f"{_tile_code(lat0, lon0)}: {exc}")

    if valid_pixels == 0:
        detail = "; ".join(tile_errors[:3])
        raise RuntimeError("ESA WorldCover online COGs returned no valid pixels." + (f" {detail}" if detail else ""))

    shares = {k: 100.0 * v / valid_pixels for k, v in counts.items()}
    forest_pct = shares.get(10, 0.0)
    class_breakdown = {
        CLASSES.get(k, f"Class {k}"): {
            "class_code": k,
            "percent": round(shares[k], 3),
            "area_ha_est": round(aoi_area_ha * shares[k] / 100.0, 3),
        }
        for k in sorted(shares)
    }
    return {
        "forest_area_ha": float(aoi_area_ha * forest_pct / 100.0),
        "forest_fraction_pct": float(forest_pct),
        "worldcover_valid_pixels": valid_pixels,
        "worldcover_classes": class_breakdown,
        "worldcover_year": 2021,
        "worldcover_resolution_m": 10,
        "worldcover_source": "ESA WorldCover 2021 v200 public AWS COGs",
        "worldcover_tile_warnings": tile_errors[:5],
    }
