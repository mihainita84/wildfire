# PREPARE | Romania Wildfire Portal v9

Streamlit prototype for **PREPARE – WP4 Forest fires and related risks**.

## v9 change: fire-danger class on every GWIS weather map

The operational GWIS thumbnails are already generated from the exact working layer IDs:

- `ecmwf.fwi`
- `ecmwf.ffmc`
- `ecmwf.dc`
- `ecmwf.isi`
- `ecmwf.bui`
- `ecmwf.nfdrs.ic`
- `ecmwf.nfdrs.ros`

After the WMS image is downloaded, the portal now inspects the **actual rendered GWIS danger colours inside the drawn AOI** before drawing the AOI outline.

For every fire-weather card it reports:

- **dominant danger class in the AOI**
- percentage of classified AOI map pixels belonging to the dominant class
- **maximum danger class intersecting the AOI** when it differs from the dominant class

Example:

`Clasă dominantă: Moderat (78% din AOI) · maxim intersectat: Ridicat`

The six classes are:

1. Low / Scăzut
2. Moderate / Moderat
3. High / Ridicat
4. Very High / Foarte ridicat
5. Extreme / Extrem
6. Very Extreme / Foarte extrem

For FWI, FFMC, DC, ISI and BUI these labels correspond to the EFFIS six-class fire-danger framework. For NFDRS IC and ROS the portal reads the displayed GWIS map class from the map colours rather than applying Canadian-FWI numeric breakpoints.

## Other current features

- maximum AOI: **5,000 ha / 50 km²**
- OpenStreetMap + NASA FIRMS active-fire points on the main map
- ESA WorldCover 2021
- ESA CCI Biomass 2024
- EFFIS `fuel_map`
- GWIS `modis.hs`
- weather and five soil-moisture depths
- EFFIS burned-area intersection
- FIRMS hotspot/FRP analysis
- Romanian / English interface
- local UNITBV and ICAS logo assets

## Run

First Windows run: `setup_and_run.bat`

Later runs: `run.bat`
