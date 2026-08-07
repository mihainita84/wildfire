# PREPARE | Romania Wildfire Portal (v7)

Streamlit prototype for **WP4 – Forest fires and related risks** in PREPARE.

## v7: EFFIS / GWIS WMS fix

The EFFIS gallery no longer uses remote image URLs inside custom Streamlit HTML. The app now:

1. requests the WMS PNG **server-side**;
2. uses the same WMS parameter pattern used by the public EFFIS/GWIS viewer;
3. uses `TIME=start/end` first for time-dependent layers;
4. requests a regional context large enough to make the ~8 km EFFIS fire-weather grid visible;
5. validates that a real, non-empty image was returned;
6. draws the AOI outline locally;
7. displays the validated PNG bytes in the gallery.

### EFFIS/GWIS gallery products

- European Fuel Map 2017: `fuel_map`
- FWI: `ecmwf007.fwi`
- FFMC: `ecmwf007.ffmc`
- DMC: `ecmwf007.dmc`
- DC: `ecmwf007.dc`
- ISI: `ecmwf007.isi`
- BUI: `ecmwf007.bui`
- FWI anomaly: `ecmwf007.anomaly`
- FWI ranking: `ecmwf007.rankingfwi`
- GWIS MODIS hotspots: `modis.hs`, using a season-to-date time interval

The WMS products are downloaded in parallel and cached for 15 minutes to reduce waiting time.

## Other portal features

- Maximum AOI: **5,000 ha / 50 km²**
- OpenStreetMap + NASA FIRMS on the main interactive map
- ESA WorldCover 2021 analysis and thumbnail
- ESA CCI Biomass v7.0 (2024) analysis and thumbnail
- weather, soil moisture, FRP, burned-area intersection and screening hazard score
- Romanian / English interface
- PREPARE WP4 and UNITBV branding

## Windows

First run: `setup_and_run.bat`

Later runs: `run.bat`

The project uses its own `.venv`.
