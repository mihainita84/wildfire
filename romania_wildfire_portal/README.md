# PREPARE | Romania Wildfire Portal (v8)

Streamlit decision-support prototype for **PREPARE – WP4 Forest fires and related risks**.

## v8 changes

The EFFIS/GWIS fire-weather gallery now uses the **exact operational WMS endpoint and layer names supplied by the EFFIS/GWIS viewer**.

### EFFIS / GWIS WMS routing

| Product | Endpoint | Layer | TIME pattern |
|---|---|---|---|
| European Fuel Map | `/effis` | `fuel_map` | `previous-day/selected-day` (with no-TIME fallback) |
| MODIS hotspots | `/gwis` | `modis.hs` | `YYYY-01-01/selected-day` |
| FWI | `/gwis` | `ecmwf.fwi` | `YYYY-MM-DD` |
| FFMC | `/gwis` | `ecmwf.ffmc` | `YYYY-MM-DD` |
| DC | `/gwis` | `ecmwf.dc` | `YYYY-MM-DD` |
| ISI | `/gwis` | `ecmwf.isi` | `YYYY-MM-DD` |
| BUI | `/gwis` | `ecmwf.bui` | `YYYY-MM-DD` |
| NFDRS Ignition Component | `/gwis` | `ecmwf.nfdrs.ic` | `YYYY-MM-DD` |
| NFDRS Rate of Spread | `/gwis` | `ecmwf.nfdrs.ros` | `YYYY-MM-DD` |

For the daily GWIS products the selected date is tried first, then the previous two days as availability fallbacks. The date actually returned is shown on each thumbnail card.

The app still requests a regional context around the selected AOI, validates that the WMS response is a non-empty image, draws the AOI outline locally, and then displays the PNG in Streamlit.

## Other portal behaviour

- AOI limit: **5,000 ha (50 km²)**
- Main map: OpenStreetMap + NASA FIRMS active fires only
- AOI analysis:
  - FIRMS active fires and FRP
  - ESA WorldCover 2021
  - ESA CCI Biomass 2024
  - EFFIS/GWIS products above
  - weather, VPD and multi-depth soil moisture
  - EFFIS burned-area intersection
  - 72-hour forecast context
- Romanian / English interface

## Logos

The packaged header now uses the UNITBV and ICAS image files supplied for the portal.

## Windows

First run:

`setup_and_run.bat`

Subsequent runs:

`run.bat`

The application uses its own `.venv`.
