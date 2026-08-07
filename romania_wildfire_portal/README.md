# Romania Forest Wildfire Portal - v2

A Streamlit portal for forest-fire situational awareness and polygon-based analysis in Romania.

## Main workflow

1. Start the app.
2. Inspect live/online wildfire layers on the Romania map.
3. Draw a polygon or rectangle.
4. Click **Analyse selected polygon**.
5. The app queries fire, weather, soil moisture, biomass and land-cover sources and builds an AOI report.
6. Export HTML, JSON and GeoJSON.

## What changed in v2

- The supplied NASA FIRMS MAP_KEY is already configured locally in `.env`.
- Google Earth Engine has been removed completely.
- EFFIS Fire Weather Index rendering was rebuilt as a dated Romania image overlay. The app probes recent dates and uses the newest non-empty EFFIS FWI image, avoiding the common blank-current-date WMS problem.
- Biomass now comes from **NASA GEDI L4B** using the online ORNL DAAC OGC service used in MAAP workflows.
- Land cover now comes directly from **ESA WorldCover 2021 v200** public cloud-optimized GeoTIFFs at 10 m.
- Optional map layers were added for GEDI biomass and ESA WorldCover.

## Online data sources

### NASA FIRMS

Used for near-real-time active-fire / thermal-anomaly detections:

- VIIRS Suomi-NPP
- VIIRS NOAA-20
- VIIRS NOAA-21
- MODIS
- Fire Radiative Power (FRP)
- confidence and acquisition time

The supplied key is stored in `.env`. `.gitignore` excludes `.env` so the key is not accidentally committed if the project is later put on GitHub.

### Copernicus EFFIS

The app uses:

- official ECMWF Fire Weather Index (`ecmwf007.fwi`)
- EFFIS burned-area polygons

FWI is time-dependent. Instead of relying on a tiled WMS request that can appear blank, the portal requests a Romania image from EFFIS and automatically checks recent dates until a valid FWI image is found.

### NASA GEDI biomass through MAAP / ORNL

The polygon analyser queries the ORNL DAAC OGC Web Coverage Service online for GEDI L4B:

- mean above-ground biomass density (AGBD), Mg/ha
- median AGBD
- 90th percentile AGBD
- mean AGBD standard error
- number of 1-km GEDI grid cells intersecting the AOI
- percentage of quality-flag cells meeting the GEDI mission criterion
- approximate total AGB over the AOI

The map can also display the GEDI L4B AGBD WMS layer.

**Resolution:** 1 km.

**Dataset used by the public OGC service:** GEDI L4B Version 2, mission weeks 19-138, observations from 2019-04-18 to 2021-08-04.

This is appropriate for landscape-scale wildfire/fuel context. It is not a stand-level forest inventory.

### ESA WorldCover 2021

WorldCover is accessed directly from the ESA public AWS bucket as 10 m Cloud-Optimized GeoTIFFs. The app reads only the tiles/windows intersecting the drawn AOI.

The analyser returns:

- tree-cover area
- tree-cover percentage
- all WorldCover classes present in the polygon
- estimated area and percentage of each class

The optional map layer uses the official Terrascope WorldCover WMS.

### Open-Meteo

Used for current and 72-hour fire-weather context:

- air temperature
- relative humidity
- precipitation
- wind speed
- wind gusts
- vapour pressure deficit
- soil moisture 0-1 cm
- soil moisture 1-3 cm
- soil moisture 3-9 cm
- soil moisture 9-27 cm
- soil moisture 27-81 cm

## Hazard screening score

The app calculates a transparent 0-100 screening score from current meteorological and surface-moisture conditions.

This score is deliberately separate from EFFIS FWI. **EFFIS is the official harmonized European fire-danger product displayed on the map.**

## Windows installation

Double-click:

`setup_and_run.bat`

The script:

- creates `.venv` inside the project
- installs every package inside `.venv`
- runs pip using `.venv\Scripts\python.exe -m pip`
- launches Streamlit using `.venv\Scripts\python.exe -m streamlit run app.py`
- does not rely on `C:\Python312\Scripts`

After the first setup use:

`run.bat`

## Important notes

- FIRMS points are thermal anomalies, not guaranteed wildfire perimeters.
- EFFIS FWI is model-based fire danger.
- Open-Meteo soil moisture is modelled, not an in-situ measurement.
- GEDI L4B is a 1 km statistical biomass product.
- ESA WorldCover represents the 2021 reference year.
- The `forest-adjusted AGB` value simply combines GEDI mean AGBD with WorldCover tree-cover area. Treat it as a screening/fuel-context indicator, not an inventory estimate.

## Good next extensions

- Romanian forest-management-plan compartments and species composition.
- fuel-type models for spruce, beech, fir, oak, pine and shrub/grass fuels.
- drought indices and dead-fuel moisture.
- slope/aspect from a direct Copernicus DEM service.
- lightning detections.
- automatic Sentinel-2 pre/post-fire dNBR severity.
- a continuous event database for Romanian fires.
- county/forest-district dashboards.
- automatic PDF report containing the AOI map and charts.
