# PREPARE WP4 – Romania Forest Wildfire Portal

Bilingual (Romanian/English) Streamlit prototype for wildfire situational awareness and polygon-based analysis in Romania.

## Project context

The portal is developed as a prototype supporting **PREPARE – Proactive Resilience and Emergency Preparedness for Adaptive Response and Efficiency**, **WP4 – Forest fires / Incendii de pădure**.

Official project page:
https://utcb.ro/cercetare/programe-uefiscdi/pn-iv-pro-coex-2024-1-prepare/

## Online data

- NASA FIRMS VIIRS/MODIS active-fire detections (MAP_KEY embedded in the private project copy)
- Copernicus EFFIS Fire Weather Index and burned areas
- ESA WorldCover 2021 v200, 10 m
- ESA CCI Biomass v7.0, 2024, 100 m, public CEDA GeoTIFF tiles
- Open-Meteo weather and multi-depth soil moisture

Google Earth Engine is not required.

## Start on Windows

Double-click:

`setup_and_run.bat`

The launcher creates an isolated `.venv`, installs all packages inside it and launches Streamlit through:

`.venv\Scripts\python.exe -m streamlit run app.py`

It does not depend on `C:\Python312\Scripts`.

Later starts can use:

`run.bat`

## Important map changes in v3

- Thematic rasters use explicit z-index values above all basemaps.
- ESA WorldCover uses the current Terrascope WMS endpoint and layer identifier: `esa-worldcover-map-10m-2021-v2_map`.
- EFFIS FWI is rendered directly by Leaflet as a time-dependent WMS layer. A date selector is provided because `TIME` is mandatory.
- GEDI/MAAP was removed.
- Biomass now uses ESA CCI Biomass v7.0, year 2024, at 100 m. The CEDA source tile is downloaded and cached only when needed.

## Biomass cache

The first CCI biomass request may take longer because the relevant CEDA GeoTIFF tile is downloaded. It is cached in the system temporary directory under `romania_wildfire_portal_cache/biomass_cci`.

For Romania, most AOIs fall in the `N40E020` 10-degree CCI tile.

## Security

This private package contains the FIRMS key supplied for the project. `.env` is ignored by Git, but the fallback key is also embedded in `app.py` to survive Windows hidden-file copying. Before publishing the repository publicly, replace the key with Streamlit Secrets or another server-side secret store.


## v4 map/biomass fix

- OpenStreetMap is now the single basemap.
- WorldCover, ESA CCI Biomass, EFFIS FWI and FIRMS are placed in separate Leaflet panes above the basemap.
- WorldCover WMS uses the current Terrascope layer `esa-worldcover-map-10m-2021-v2_map` and `TIME=2021-01-01`.
- ESA CCI Biomass v7.0 tile naming is corrected: Romania is in `N50E020` (40-50 N, 20-30 E). The previous version requested `N40E020`, which caused empty biomass results.
- Biomass is enabled by default. The first run downloads the public 2024 AGB tile from CEDA and caches it; subsequent map rendering and AOI analyses reuse the cached file.
