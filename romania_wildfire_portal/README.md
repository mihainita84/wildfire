# PREPARE | Romania Wildfire Portal (v6)

Streamlit prototype for **WP4 – Forest fires and related risks** in PREPARE.

## v6 changes

- AOI analysis limit increased to **5,000 ha (50 km²)**.
- Main interactive map remains lightweight:
  - OpenStreetMap
  - NASA FIRMS active-fire points
- Cleaner thematic gallery after AOI analysis:
  - FIRMS active fires
  - ESA WorldCover 2021
  - ESA CCI Biomass 2024
  - Copernicus EFFIS FWI
  - EFFIS FFMC
  - EFFIS DMC
  - EFFIS DC
  - EFFIS ISI
  - EFFIS BUI
  - EFFIS FWI Anomaly
  - EFFIS FWI Ranking
- EFFIS thumbnails are now requested **directly by the user's browser from the official WMS**, avoiding the server-side WMS failure seen in v5.
- Added official EFFIS fire-danger class thresholds to the analysis.
- Added PREPARE-WP4 and UNITBV branded wordmark assets for a cleaner portal header.
- Romanian / English interface retained.

## Important EFFIS note

The official EFFIS WMS requires the `TIME` parameter. The portal builds direct `GetMap` image URLs for the selected date and current AOI.

## Windows

First run:

`setup_and_run.bat`

Later runs:

`run.bat`

The project uses its own `.venv` and does not depend on the global `C:\Python312\Scripts`.
