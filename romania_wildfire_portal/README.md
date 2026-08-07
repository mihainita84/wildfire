# PREPARE | Romania Wildfire Portal (v5)

Streamlit application for **WP4 – Forest fires and related risks** in the **PREPARE** project.

## What changed in v5

- **Larger interactive map**: the old explanatory side panel next to the map was removed.
- **Only one basemap**: OpenStreetMap.
- **Interactive map kept light**: only **NASA FIRMS active fires** are shown live on the map.
- **AOI limit**: maximum **5 km² (500 ha)** to avoid app crashes and very slow raster processing.
- **Thematic thumbnails are generated after analysis** for:
  - FIRMS active fires inside the AOI
  - ESA WorldCover 2021
  - ESA CCI Biomass 2024
  - EFFIS FWI
  - EFFIS FFMC
  - EFFIS ISI
  - EFFIS BUI
  - EFFIS DMC
  - EFFIS DC
- **Romanian / English interface**.

## Main sources

- NASA FIRMS (embedded API key)
- Copernicus EFFIS
- Open-Meteo
- ESA WorldCover 2021
- ESA CCI Biomass v7.0 (2024)

## Run on Windows

Double-click:

- `setup_and_run.bat` for first install
- `run.bat` for subsequent runs

The project creates and uses its own `.venv`.
