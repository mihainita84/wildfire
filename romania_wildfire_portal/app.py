from __future__ import annotations

import base64
import json
import os

import folium
from folium.plugins import Draw, Fullscreen, MeasureControl, MousePosition
import geopandas as gpd
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium
from dotenv import load_dotenv

from services.geometry import geojson_to_gdf, area_ha, bounds_csv, centroid_lonlat
from services.firms import fetch_firms, filter_to_aoi, summarize_fires
from services.effis import ROMANIA_FWI_BOUNDS, fetch_latest_fwi_image, fetch_burned_areas, summarize_burned_areas
from services.openmeteo import fetch_weather, portal_hazard_score
from services.biomass_maap import ORNL_WMS, GEDI_AGBD_LAYER, biomass_stats
from services.worldcover import WORLDCOVER_WMS, WORLDCOVER_WMS_LAYER, landcover_stats
from services.reporting import make_html_report

load_dotenv()

# The user's FIRMS MAP_KEY is stored in .env in the distributed project. This
# fallback keeps the supplied project functional even if Windows hides .env
# during copy/extract. For a public deployment, move it to Streamlit Secrets.
DEFAULT_FIRMS_MAP_KEY = "87f35b3f6f3784bd1eba380d16e0198b"
FIRMS_MAP_KEY = os.getenv("FIRMS_MAP_KEY", DEFAULT_FIRMS_MAP_KEY).strip() or DEFAULT_FIRMS_MAP_KEY

st.set_page_config(page_title="Romania Wildfire Portal", page_icon="🔥", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.2rem;}
[data-testid="stMetric"] {background:#f7f7f4;border:1px solid #e2e2dd;padding:10px 14px;border-radius:12px;}
.small-note {font-size:.88rem;color:#5d665f}
.hero {padding:14px 18px;border-radius:16px;background:linear-gradient(90deg,#3d211b,#8f2f1f);color:white;margin-bottom:12px}
.hero h1 {margin:0;font-size:2rem}.hero p{margin:.25rem 0 0 0;opacity:.9}
</style>
<div class="hero"><h1>🔥 Romania Forest Wildfire Portal</h1><p>Active fires • EFFIS fire danger • burned areas • GEDI biomass • ESA WorldCover • soil moisture • weather • polygon reports</p></div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("Live data layers")
    st.success("NASA FIRMS key embedded")
    source = st.selectbox("FIRMS sensor", ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "MODIS_NRT"], index=0)
    day_range = st.slider("Recent fire window (days)", 1, 5, 2)
    show_fwi = st.checkbox("EFFIS official Fire Weather Index", True)
    show_firms_romania = st.checkbox("NASA FIRMS hotspots", True)
    show_worldcover = st.checkbox("ESA WorldCover 2021", False)
    show_biomass = st.checkbox("NASA GEDI biomass (MAAP/ORNL)", False)

    st.divider()
    st.caption("No Google Earth Engine account is required. Biomass is queried online from the GEDI L4B OGC service used in the MAAP ecosystem; land cover is read directly from ESA WorldCover public cloud data.")
    st.caption("Draw a polygon or rectangle. The most recent drawing is analysed.")


@st.cache_data(ttl=900, show_spinner=False)
def cached_firms(sensor: str, bbox: str, days: int):
    return fetch_firms(FIRMS_MAP_KEY, sensor, bbox, days)


@st.cache_data(ttl=10800, show_spinner=False)
def cached_fwi():
    return fetch_latest_fwi_image(lookback_days=5)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_effis_burned(geojson_str: str):
    aoi = geojson_to_gdf(json.loads(geojson_str))
    return fetch_burned_areas(aoi)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_biomass(geojson_str: str, aoi_area: float):
    aoi = geojson_to_gdf(json.loads(geojson_str))
    return biomass_stats(aoi, aoi_area_ha=aoi_area)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_worldcover(geojson_str: str, aoi_area: float):
    aoi = geojson_to_gdf(json.loads(geojson_str))
    return landcover_stats(aoi, aoi_area_ha=aoi_area)


def build_map():
    m = folium.Map(location=[45.9, 24.9], zoom_start=7, tiles="CartoDB positron", control_scale=True)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name="Satellite", overlay=False
    ).add_to(m)

    if show_fwi:
        try:
            png, fwi_day = cached_fwi()
            data_uri = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
            folium.raster_layers.ImageOverlay(
                image=data_uri,
                bounds=ROMANIA_FWI_BOUNDS,
                name=f"EFFIS FWI official ({fwi_day})",
                opacity=0.62,
                interactive=False,
                cross_origin=False,
                zindex=2,
            ).add_to(m)
            st.sidebar.caption(f"EFFIS FWI date: {fwi_day}")
        except Exception as exc:
            st.sidebar.warning(f"EFFIS FWI unavailable: {exc}")

    if show_worldcover:
        folium.raster_layers.WmsTileLayer(
            url=WORLDCOVER_WMS,
            layers=WORLDCOVER_WMS_LAYER,
            name="ESA WorldCover 2021 (10 m)",
            fmt="image/png",
            transparent=True,
            version="1.1.1",
            opacity=0.65,
            show=True,
            attr="© ESA WorldCover 2021",
        ).add_to(m)

    if show_biomass:
        folium.raster_layers.WmsTileLayer(
            url=ORNL_WMS,
            layers=GEDI_AGBD_LAYER,
            name="GEDI L4B mean AGBD (1 km)",
            fmt="image/png",
            transparent=True,
            version="1.1.1",
            opacity=0.62,
            show=True,
            attr="NASA GEDI / ORNL DAAC / MAAP ecosystem",
        ).add_to(m)

    if show_firms_romania:
        try:
            fires = cached_firms(source, "20.0,43.4,30.2,48.4", day_range)
            for _, r in fires.iterrows():
                popup = (
                    f"{source}<br>{r.get('acq_date','')} {r.get('acq_time','')}"
                    f"<br>FRP: {r.get('frp','n/a')} MW<br>Confidence: {r.get('confidence','n/a')}"
                )
                folium.CircleMarker(
                    [r.geometry.y, r.geometry.x], radius=3.5, color="#d63a24", fill=True,
                    fill_color="#ff5a36", fill_opacity=.78, weight=1, popup=popup
                ).add_to(m)
        except Exception as exc:
            st.sidebar.warning(f"FIRMS map layer unavailable: {exc}")

    Draw(
        export=False,
        draw_options={
            "polyline": False, "rectangle": True, "circle": False,
            "circlemarker": False, "marker": False,
            "polygon": {"allowIntersection": False, "showArea": True},
        },
        edit_options={"edit": True, "remove": True},
    ).add_to(m)
    Fullscreen().add_to(m)
    MeasureControl(primary_length_unit="kilometers", primary_area_unit="hectares").add_to(m)
    MousePosition(position="bottomright", separator=" | ", prefix="Lat/Lon:").add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    return m


map_col, info_col = st.columns([2.25, 1], gap="large")
with map_col:
    out = st_folium(build_map(), height=675, width=None, returned_objects=["all_drawings", "last_active_drawing"])

with info_col:
    st.subheader("Polygon report")
    st.markdown("""
- AOI area and ESA WorldCover class composition
- forest area and forest-cover percentage at 10 m
- NASA GEDI L4B mean above-ground biomass density
- GEDI uncertainty and quality coverage
- recent VIIRS/MODIS hotspots and Fire Radiative Power (FRP)
- EFFIS burned-area intersection
- temperature, humidity, wind, gusts, VPD and precipitation
- soil moisture at five depths
- transparent 0-100 screening hazard score
""")
    st.info("The coloured EFFIS layer is the official European FWI product. The portal's 0-100 score is a separate screening index and is not an operational FWI replacement.")

last = out.get("last_active_drawing") if out else None
if not last or not last.get("geometry"):
    st.warning("Draw a polygon or rectangle on the map to activate the AOI analyser.")
    st.stop()

try:
    aoi = geojson_to_gdf(last["geometry"])
except Exception as exc:
    st.error(str(exc))
    st.stop()

aoi_area = area_ha(aoi)
lon, lat = centroid_lonlat(aoi)
bbox = bounds_csv(aoi)
geojson_str = json.dumps(last["geometry"], sort_keys=True)
aoi_signature = geojson_str

st.divider()
st.header("AOI analyser")
run = st.button("▶ Analyse selected polygon", type="primary", use_container_width=True)

previous_signature = st.session_state.get("analysis_aoi_signature")
if previous_signature != aoi_signature and not run:
    st.caption(f"Selected AOI: {aoi_area:,.1f} ha. Click **Analyse selected polygon** to query the online datasets.")
    st.stop()

if run:
    result = {
        "aoi": {"area_ha": aoi_area, "centroid_lat": lat, "centroid_lon": lon},
        "active_fire": {},
        "burned_area": {},
        "weather_soil": {},
        "forest_biomass": {},
        "hazard": {},
        "warnings": {},
    }

    with st.spinner("Querying weather, soil moisture, fires, EFFIS, GEDI biomass and ESA WorldCover…"):
        # Weather + soil moisture
        try:
            current, hourly = fetch_weather(lat, lon, forecast_days=3)
            result["weather_soil"] = current
            st.session_state["hourly"] = hourly
        except Exception as exc:
            current, hourly = {}, pd.DataFrame()
            result["warnings"]["weather"] = str(exc)

        # FIRMS
        try:
            fires = cached_firms(source, bbox, day_range)
            fires_aoi = filter_to_aoi(fires, aoi)
            result["active_fire"] = summarize_fires(fires_aoi)
            st.session_state["fires_aoi"] = fires_aoi
        except Exception as exc:
            result["warnings"]["firms"] = str(exc)

        # EFFIS burned area
        try:
            burned = cached_effis_burned(geojson_str)
            result["burned_area"] = summarize_burned_areas(burned, aoi)
            st.session_state["burned"] = burned
        except Exception as exc:
            result["warnings"]["effis_burned_area"] = str(exc)

        # ESA WorldCover direct online COG analysis
        try:
            wc = cached_worldcover(geojson_str, aoi_area)
            result["forest_biomass"].update(wc)
            if wc.get("worldcover_tile_warnings"):
                result["warnings"]["worldcover_partial"] = "; ".join(wc["worldcover_tile_warnings"])
        except Exception as exc:
            result["warnings"]["worldcover"] = str(exc)

        # MAAP/ORNL GEDI L4B online WCS analysis
        try:
            bio = cached_biomass(geojson_str, aoi_area)
            result["forest_biomass"].update(bio)
        except Exception as exc:
            result["warnings"]["gedi_biomass"] = str(exc)

        # Forest-adjusted stock indicator. This is intentionally labelled as an estimate.
        fb = result["forest_biomass"]
        if fb.get("agb_mean_mg_ha") is not None and fb.get("forest_area_ha") is not None:
            fb["forest_adjusted_agb_mg_est"] = float(fb["agb_mean_mg_ha"] * fb["forest_area_ha"])

        if current:
            score, label, components = portal_hazard_score(current, ndmi=None)
            result["hazard"] = {
                "portal_screening_score_0_100": score,
                "screening_class": label,
                "components": components,
                "official_fwi_note": "Use the EFFIS FWI map layer for the official harmonized European fire-danger product.",
            }
        else:
            result["hazard"] = {
                "portal_screening_score_0_100": None,
                "screening_class": "Unavailable",
                "components": {},
                "official_fwi_note": "Weather data were unavailable; use the EFFIS FWI map layer.",
            }

    st.session_state["analysis"] = result
    st.session_state["analysis_aoi_signature"] = aoi_signature

result = st.session_state.get("analysis")
if not result:
    st.stop()

fire = result.get("active_fire", {})
burn = result.get("burned_area", {})
weather = result.get("weather_soil", {})
fb = result.get("forest_biomass", {})
haz = result.get("hazard", {})

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("AOI", f"{result['aoi']['area_ha']:,.1f} ha")
m2.metric("Forest cover", f"{fb.get('forest_fraction_pct', float('nan')):.1f}%" if fb.get("forest_fraction_pct") is not None else "n/a")
m3.metric("Mean AGBD", f"{fb.get('agb_mean_mg_ha', float('nan')):.1f} Mg/ha" if fb.get("agb_mean_mg_ha") is not None else "n/a")
m4.metric("Recent hotspots", fire.get("hotspots", "n/a"))
m5.metric("Burned area", f"{burn.get('burned_area_ha', 0):,.1f} ha")
m6.metric("Hazard screening", f"{haz.get('portal_screening_score_0_100','n/a')} / 100", haz.get("screening_class"))

left, right = st.columns([1.05, 1.15], gap="large")
with left:
    st.subheader("Weather and fuel-moisture context")
    weather_table = pd.DataFrame([
        ["Temperature", weather.get("temperature_2m"), "°C"],
        ["Relative humidity", weather.get("relative_humidity_2m"), "%"],
        ["Wind speed", weather.get("wind_speed_10m"), "km/h"],
        ["Wind gust", weather.get("wind_gusts_10m"), "km/h"],
        ["Vapour pressure deficit", weather.get("vapour_pressure_deficit"), "kPa"],
        ["Precipitation", weather.get("precipitation"), "mm"],
        ["Soil moisture 0-1 cm", weather.get("soil_moisture_0_to_1cm"), "m³/m³"],
        ["Soil moisture 1-3 cm", weather.get("soil_moisture_1_to_3cm"), "m³/m³"],
        ["Soil moisture 3-9 cm", weather.get("soil_moisture_3_to_9cm"), "m³/m³"],
        ["Soil moisture 9-27 cm", weather.get("soil_moisture_9_to_27cm"), "m³/m³"],
        ["Soil moisture 27-81 cm", weather.get("soil_moisture_27_to_81cm"), "m³/m³"],
    ], columns=["Indicator", "Value", "Unit"])
    st.dataframe(weather_table, hide_index=True, use_container_width=True)

with right:
    st.subheader("Forest cover and biomass")
    forest_table = pd.DataFrame([
        ["Forest area (WorldCover tree-cover class)", fb.get("forest_area_ha"), "ha"],
        ["Forest fraction", fb.get("forest_fraction_pct"), "%"],
        ["Mean GEDI above-ground biomass density", fb.get("agb_mean_mg_ha"), "Mg/ha"],
        ["Median GEDI AGBD", fb.get("agb_median_mg_ha"), "Mg/ha"],
        ["90th percentile GEDI AGBD", fb.get("agb_p90_mg_ha"), "Mg/ha"],
        ["Mean GEDI standard error", fb.get("agb_standard_error_mean_mg_ha"), "Mg/ha"],
        ["GEDI cells sampled", fb.get("gedi_cells"), "1-km cells"],
        ["GEDI cells meeting quality criterion", fb.get("gedi_quality_pct"), "%"],
        ["Estimated AGB over whole AOI", fb.get("agb_total_aoi_mg_est"), "Mg"],
        ["Forest-adjusted AGB indicator", fb.get("forest_adjusted_agb_mg_est"), "Mg"],
    ], columns=["Indicator", "Value", "Unit"])
    st.dataframe(forest_table, hide_index=True, use_container_width=True)
    st.caption("GEDI L4B is a 1 km statistical biomass product. The forest-adjusted stock multiplies mean GEDI AGBD by ESA WorldCover tree-cover area and should be interpreted as an AOI screening estimate, not an inventory estimate.")

classes = fb.get("worldcover_classes") or {}
if classes:
    st.subheader("ESA WorldCover composition")
    class_rows = [
        {"Land-cover class": name, "Code": d.get("class_code"), "Area (ha, estimated)": d.get("area_ha_est"), "AOI (%)": d.get("percent")}
        for name, d in classes.items()
    ]
    st.dataframe(pd.DataFrame(class_rows).sort_values("AOI (%)", ascending=False), hide_index=True, use_container_width=True)

hourly = st.session_state.get("hourly", pd.DataFrame())
if not hourly.empty:
    st.subheader("Next 72 hours")
    chart_df = hourly[[c for c in ["time", "temperature_2m", "relative_humidity_2m", "wind_speed_10m", "soil_moisture_0_to_1cm"] if c in hourly.columns]].copy()
    melted = chart_df.melt(id_vars="time", var_name="indicator", value_name="value")
    fig = px.line(melted, x="time", y="value", color="indicator", facet_row="indicator", height=620)
    fig.update_yaxes(matches=None)
    fig.update_layout(showlegend=False, margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Fire detections in selected polygon")
fires_aoi = st.session_state.get("fires_aoi")
if isinstance(fires_aoi, gpd.GeoDataFrame) and not fires_aoi.empty:
    cols = [c for c in ["acq_date", "acq_time", "satellite", "instrument", "confidence", "frp", "bright_ti4", "latitude", "longitude"] if c in fires_aoi.columns]
    st.dataframe(fires_aoi[cols], hide_index=True, use_container_width=True)
else:
    st.caption("No FIRMS detections were returned for this AOI/window.")

if result.get("warnings"):
    with st.expander("Data-source warnings / unavailable modules"):
        for k, v in result["warnings"].items():
            st.warning(f"{k}: {v}")

st.subheader("Download report and AOI")
html_report = make_html_report(result)
geojson_bytes = aoi.to_json().encode("utf-8")
json_bytes = json.dumps(result, ensure_ascii=False, indent=2, default=str).encode("utf-8")

b1, b2, b3 = st.columns(3)
b1.download_button("⬇ HTML report", html_report.encode("utf-8"), "wildfire_AOI_report.html", "text/html", use_container_width=True)
b2.download_button("⬇ Analysis JSON", json_bytes, "wildfire_AOI_analysis.json", "application/json", use_container_width=True)
b3.download_button("⬇ AOI GeoJSON", geojson_bytes, "wildfire_AOI.geojson", "application/geo+json", use_container_width=True)

st.caption("Operational note: FIRMS detections are satellite thermal anomalies and can include non-wildfire heat sources; Open-Meteo soil moisture is modelled; GEDI and WorldCover have spatial/temporal uncertainty. This portal is for screening, research and situational awareness, not emergency command decisions.")
