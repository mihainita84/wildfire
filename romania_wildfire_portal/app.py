from __future__ import annotations

import base64
import json
import os
from datetime import date, timedelta

import folium
from branca.colormap import LinearColormap
from folium.plugins import Draw, Fullscreen, MeasureControl, MousePosition
import geopandas as gpd
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium
from dotenv import load_dotenv

from services.geometry import geojson_to_gdf, area_ha, bounds_csv, centroid_lonlat
from services.firms import fetch_firms, filter_to_aoi, summarize_fires
from services.effis import EFFIS_WMS, EFFIS_FWI_LAYER, fetch_burned_areas, summarize_burned_areas
from services.openmeteo import fetch_weather, portal_hazard_score
from services.biomass_cci import biomass_stats, biomass_overlay_png, CCI_YEAR, CCI_VERSION
from services.worldcover import WORLDCOVER_WMS, WORLDCOVER_WMS_LAYER, landcover_stats
from services.reporting import make_html_report

load_dotenv()

DEFAULT_FIRMS_MAP_KEY = "87f35b3f6f3784bd1eba380d16e0198b"
FIRMS_MAP_KEY = os.getenv("FIRMS_MAP_KEY", DEFAULT_FIRMS_MAP_KEY).strip() or DEFAULT_FIRMS_MAP_KEY
PROJECT_URL = "https://utcb.ro/cercetare/programe-uefiscdi/pn-iv-pro-coex-2024-1-prepare/"

st.set_page_config(page_title="PREPARE | Romania Wildfire Portal", page_icon="🔥", layout="wide")

language = st.sidebar.selectbox("Limbă / Language", ["Română", "English"], index=0)
RO = language == "Română"


def t(ro: str, en: str) -> str:
    return ro if RO else en


st.markdown("""
<style>
.block-container {padding-top: 1.0rem;}
[data-testid="stMetric"] {background:rgba(247,247,244,.07);border:1px solid rgba(150,150,150,.25);padding:10px 14px;border-radius:12px;}
.hero {padding:16px 20px;border-radius:16px;background:linear-gradient(90deg,#3d211b,#8f2f1f);color:white;margin-bottom:10px}
.hero h1 {margin:0;font-size:2rem}.hero p{margin:.30rem 0 0 0;opacity:.92}
.project-card {border:1px solid rgba(150,150,150,.25);border-radius:14px;padding:12px 15px;margin:7px 0 14px 0;background:rgba(120,120,120,.05)}
.project-card b {color:#ef8b68}
</style>
""", unsafe_allow_html=True)

hero_sub = t(
    "PREPARE • WP4 Incendii de pădure și riscuri asociate • focare active • pericol de incendiu • biomasă • umiditatea solului • rapoarte pe poligon",
    "PREPARE • WP4 Forest fires and related risks • active fires • fire danger • biomass • soil moisture • polygon reports",
)
st.markdown(
    f'<div class="hero"><h1>🔥 {t("Portal pentru incendiile de pădure din România", "Romania Forest Wildfire Portal")}</h1><p>{hero_sub}</p></div>',
    unsafe_allow_html=True,
)

project_text = t(
    "Portalul este dezvoltat ca prototip de suport pentru <b>WP4 – Incendii de pădure</b> din cadrul Centrului de Excelență <b>PREPARE</b> (PN-IV-P6-6.1-CoEx-2024-0102, 2026–2030). WP4 urmărește modelarea, monitorizarea, prevenția și evaluarea efectelor asociate incendiilor de pădure.",
    "This portal is developed as a decision-support prototype for <b>WP4 – Forest fires</b> within the <b>PREPARE</b> Centre of Excellence (PN-IV-P6-6.1-CoEx-2024-0102, 2026–2030). WP4 addresses modelling, monitoring, prevention and assessment of wildfire-related effects.",
)
st.markdown(
    f'<div class="project-card">{project_text} &nbsp; <a href="{PROJECT_URL}" target="_blank">{t("Pagina oficială PREPARE", "Official PREPARE page")} ↗</a></div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header(t("Straturi de date", "Live data layers"))
    st.success(t("Cheia NASA FIRMS este integrată", "NASA FIRMS key embedded"))
    source = st.selectbox(t("Senzor FIRMS", "FIRMS sensor"), ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "MODIS_NRT"], index=0)
    day_range = st.slider(t("Fereastra focarelor recente (zile)", "Recent fire window (days)"), 1, 5, 2)

    st.markdown(f"**{t('Straturi tematice', 'Thematic layers')}**")
    show_fwi = st.checkbox(t("EFFIS – Fire Weather Index oficial", "EFFIS official Fire Weather Index"), True)
    fwi_day = st.date_input(
        t("Data FWI", "FWI date"),
        value=date.today(),
        min_value=date.today() - timedelta(days=5),
        max_value=date.today() + timedelta(days=8),
        disabled=not show_fwi,
        help=t("EFFIS necesită parametrul TIME. Puteți schimba data dacă o zi nu este încă publicată.", "EFFIS requires the TIME parameter. Change the date if a product day is not yet published."),
    )
    show_firms_romania = st.checkbox(t("NASA FIRMS – focare termice", "NASA FIRMS hotspots"), True)
    show_worldcover = st.checkbox("ESA WorldCover 2021 (10 m)", True)
    show_biomass = st.checkbox(f"ESA CCI Biomass {CCI_YEAR} (100 m)", False)
    raster_opacity = st.slider(t("Opacitatea straturilor raster", "Raster layer opacity"), 0.25, 0.90, 0.68, 0.05)

    st.divider()
    with st.expander(t("Clasele oficiale EFFIS FWI", "Official EFFIS FWI classes")):
        st.markdown("**Low / Scăzut:** < 11.2  \n**Moderate / Moderat:** 11.2–21.3  \n**High / Ridicat:** 21.3–38.0  \n**Very high / Foarte ridicat:** 38.0–50.0  \n**Extreme / Extrem:** 50.0–70.0  \n**Very extreme / Foarte extrem:** > 70.0")
        st.caption("Source / Sursa: Copernicus EFFIS")

    st.caption(t(
        "Straturile tematice sunt forțate deasupra hărții de bază. WorldCover folosește serviciul public Terrascope curent, iar biomasa este ESA CCI Biomass v7.0 de la CEDA. Nu este necesar Google Earth Engine.",
        "Thematic rasters are forced above the basemap. WorldCover uses the current public Terrascope service and biomass is ESA CCI Biomass v7.0 from CEDA. Google Earth Engine is not required.",
    ))
    st.caption(t("Desenați un poligon sau dreptunghi. Ultima geometrie desenată este analizată.", "Draw a polygon or rectangle. The most recent drawing is analysed."))
    with st.expander(t("Despre PREPARE", "About PREPARE")):
        st.markdown(t(
            "**PREPARE – Proactive Resilience and Emergency Preparedness for Adaptive Response and Efficiency** este un Centru național de Excelență pentru managementul riscului de dezastre și reziliență. Proiectul are 15 instituții partenere, 8 pachete de lucru și o perioadă de implementare 2026–2030. Acest portal sprijină activitățile WP4 privind incendiile de pădure.",
            "**PREPARE – Proactive Resilience and Emergency Preparedness for Adaptive Response and Efficiency** is a national Centre of Excellence for disaster-risk management and resilience. The project brings together 15 partner institutions, 8 work packages and runs from 2026 to 2030. This portal supports WP4 wildfire activities.",
        ))
        st.markdown(f"[{t('Pagina proiectului', 'Project page')}]({PROJECT_URL})")


@st.cache_data(ttl=900, show_spinner=False)
def cached_firms(sensor: str, bbox: str, days: int):
    return fetch_firms(FIRMS_MAP_KEY, sensor, bbox, days)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_effis_burned(geojson_str: str):
    aoi = geojson_to_gdf(json.loads(geojson_str))
    return fetch_burned_areas(aoi)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_biomass(geojson_str: str, aoi_area: float):
    aoi = geojson_to_gdf(json.loads(geojson_str))
    return biomass_stats(aoi, aoi_area_ha=aoi_area)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_biomass_overlay():
    return biomass_overlay_png()


@st.cache_data(ttl=86400, show_spinner=False)
def cached_worldcover(geojson_str: str, aoi_area: float):
    aoi = geojson_to_gdf(json.loads(geojson_str))
    return landcover_stats(aoi, aoi_area_ha=aoi_area)


def add_worldcover_legend(m: folium.Map):
    items = [
        (10, "#006400", t("Arbori", "Tree cover")),
        (20, "#ffbb22", t("Tufăriș", "Shrubland")),
        (30, "#ffff4c", t("Pajiști", "Grassland")),
        (40, "#f096ff", t("Teren agricol", "Cropland")),
        (50, "#fa0000", t("Construit", "Built-up")),
        (60, "#b4b4b4", t("Sol rar/neacoperit", "Bare/sparse")),
        (80, "#0064c8", t("Apă", "Water")),
        (90, "#0096a0", t("Zonă umedă", "Wetland")),
    ]
    rows = "".join(f'<span style="display:inline-block;width:10px;height:10px;background:{c};margin-right:5px"></span>{label}<br>' for _, c, label in items)
    html = f"""
    <div style="position: fixed; bottom: 32px; left: 54px; z-index: 9998; background: rgba(255,255,255,.92); color:#222;
                padding:8px 10px; border:1px solid #777; border-radius:6px; font-size:11px; line-height:1.35;">
      <b>ESA WorldCover 2021</b><br>{rows}
    </div>
    """
    m.get_root().html.add_child(folium.Element(html))


def build_map():
    # tiles=None gives us full control over basemap and thematic layer stacking.
    m = folium.Map(location=[45.9, 24.9], zoom_start=7, tiles=None, control_scale=True)
    folium.TileLayer("CartoDB positron", name="CartoDB Positron", overlay=False, show=True, z_index=100).add_to(m)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap", overlay=False, show=False, z_index=100).add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name=t("Satelit", "Satellite"), overlay=False, show=False, z_index=100
    ).add_to(m)

    if show_worldcover:
        folium.raster_layers.WmsTileLayer(
            url=WORLDCOVER_WMS,
            layers=WORLDCOVER_WMS_LAYER,
            name="ESA WorldCover 2021 (10 m)",
            fmt="image/png",
            transparent=True,
            version="1.3.0",
            opacity=raster_opacity,
            show=True,
            z_index=410,
            attr="© ESA WorldCover project 2021 / Terrascope",
        ).add_to(m)
        add_worldcover_legend(m)

    if show_biomass:
        try:
            png, bio_bounds = cached_biomass_overlay()
            data_uri = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
            folium.raster_layers.ImageOverlay(
                image=data_uri,
                bounds=bio_bounds,
                name=f"ESA CCI Biomass {CCI_YEAR} AGB (100 m)",
                opacity=raster_opacity,
                interactive=False,
                cross_origin=False,
                zindex=430,
                show=True,
            ).add_to(m)
            LinearColormap(
                ["#fff7bc", "#addd8e", "#31a354", "#005a32"],
                vmin=0, vmax=300,
                caption=f"ESA CCI Biomass {CCI_YEAR} AGB (Mg/ha)",
            ).add_to(m)
        except Exception as exc:
            st.sidebar.warning(t(f"Biomasa CCI nu poate fi afișată: {exc}", f"CCI Biomass display unavailable: {exc}"))

    if show_fwi:
        # Direct browser-side WMS. This is intentionally not pre-validated as a
        # server-side PNG because that rejected valid/late-published EFFIS layers.
        folium.raster_layers.WmsTileLayer(
            url=EFFIS_WMS,
            layers=EFFIS_FWI_LAYER,
            name=f"EFFIS FWI ({fwi_day.isoformat()})",
            styles="",
            fmt="image/png",
            transparent=True,
            version="1.1.1",
            opacity=raster_opacity,
            show=True,
            time=fwi_day.isoformat(),
            z_index=460,
            attr="Copernicus EFFIS / European Commission JRC",
        ).add_to(m)

    if show_firms_romania:
        try:
            fires = cached_firms(source, "20.0,43.4,30.0,48.5", day_range)
            fg = folium.FeatureGroup(name=f"NASA FIRMS – {source}", overlay=True, show=True)
            for _, r in fires.iterrows():
                popup = (
                    f"{source}<br>{r.get('acq_date','')} {r.get('acq_time','')}"
                    f"<br>FRP: {r.get('frp','n/a')} MW<br>Confidence: {r.get('confidence','n/a')}"
                )
                folium.CircleMarker(
                    [r.geometry.y, r.geometry.x], radius=3.7, color="#9e2619", fill=True,
                    fill_color="#ff5a36", fill_opacity=.86, weight=1, popup=popup
                ).add_to(fg)
            fg.add_to(m)
        except Exception as exc:
            st.sidebar.warning(t(f"Stratul FIRMS nu este disponibil: {exc}", f"FIRMS map layer unavailable: {exc}"))

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
    out = st_folium(build_map(), height=690, width=None, returned_objects=["all_drawings", "last_active_drawing"])

with info_col:
    st.subheader(t("Raport pentru poligon", "Polygon report"))
    st.markdown(t(
        """
- suprafața AOI și compoziția ESA WorldCover
- suprafața forestieră și procentul de acoperire cu arbori la 10 m
- biomasa supraterană ESA CCI la 100 m și incertitudinea asociată
- focare recente VIIRS/MODIS și Fire Radiative Power (FRP)
- suprafața arsă intersectată din EFFIS
- temperatură, umiditate, vânt, rafale, VPD și precipitații
- umiditatea solului la cinci adâncimi
- scor transparent 0–100 pentru screening-ul hazardului
""",
        """
- AOI area and ESA WorldCover class composition
- forest area and tree-cover percentage at 10 m
- ESA CCI above-ground biomass at 100 m and associated uncertainty
- recent VIIRS/MODIS hotspots and Fire Radiative Power (FRP)
- EFFIS burned-area intersection
- temperature, humidity, wind, gusts, VPD and precipitation
- soil moisture at five depths
- transparent 0–100 hazard-screening score
""",
    ))
    st.info(t(
        "Stratul colorat EFFIS este produsul european oficial FWI. Scorul 0–100 al portalului este un indicator separat de screening și nu înlocuiește FWI operațional.",
        "The coloured EFFIS layer is the official European FWI product. The portal's 0–100 score is a separate screening index and is not an operational FWI replacement.",
    ))
    st.caption(t(
        "Biomasa provine din ESA CCI Biomass v7.0, anul 2024, la 100 m. WorldCover 2021 este utilizat pentru structura acoperirii terenului la 10 m.",
        "Biomass comes from ESA CCI Biomass v7.0 for 2024 at 100 m. WorldCover 2021 provides the 10 m land-cover context.",
    ))

last = out.get("last_active_drawing") if out else None
if not last or not last.get("geometry"):
    st.warning(t("Desenați un poligon sau dreptunghi pe hartă pentru a activa analizorul AOI.", "Draw a polygon or rectangle on the map to activate the AOI analyser."))
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
st.header(t("Analizor AOI", "AOI analyser"))
run = st.button(t("▶ Analizează poligonul selectat", "▶ Analyse selected polygon"), type="primary", use_container_width=True)

previous_signature = st.session_state.get("analysis_aoi_signature")
if previous_signature != aoi_signature and not run:
    st.caption(t(
        f"AOI selectat: {aoi_area:,.1f} ha. Apăsați **Analizează poligonul selectat** pentru interogarea seturilor de date online.",
        f"Selected AOI: {aoi_area:,.1f} ha. Click **Analyse selected polygon** to query the online datasets.",
    ))
    st.stop()

if run:
    result = {
        "project": {
            "name": "PREPARE – Proactive Resilience and Emergency Preparedness for Adaptive Response and Efficiency",
            "work_package": "WP4 – Forest fires / Incendii de pădure",
            "project_code": "PN-IV-P6-6.1-CoEx-2024-0102",
            "period": "2026–2030",
            "url": PROJECT_URL,
        },
        "aoi": {"area_ha": aoi_area, "centroid_lat": lat, "centroid_lon": lon},
        "active_fire": {},
        "burned_area": {},
        "weather_soil": {},
        "forest_biomass": {},
        "hazard": {},
        "warnings": {},
    }

    with st.spinner(t(
        "Interogare meteo, umiditatea solului, FIRMS, EFFIS, ESA CCI Biomass și ESA WorldCover…",
        "Querying weather, soil moisture, FIRMS, EFFIS, ESA CCI Biomass and ESA WorldCover…",
    )):
        try:
            current, hourly = fetch_weather(lat, lon, forecast_days=3)
            result["weather_soil"] = current
            st.session_state["hourly"] = hourly
        except Exception as exc:
            current, hourly = {}, pd.DataFrame()
            result["warnings"]["weather"] = str(exc)

        try:
            fires = cached_firms(source, bbox, day_range)
            fires_aoi = filter_to_aoi(fires, aoi)
            result["active_fire"] = summarize_fires(fires_aoi)
            st.session_state["fires_aoi"] = fires_aoi
        except Exception as exc:
            result["warnings"]["firms"] = str(exc)

        try:
            burned = cached_effis_burned(geojson_str)
            result["burned_area"] = summarize_burned_areas(burned, aoi)
            st.session_state["burned"] = burned
        except Exception as exc:
            result["warnings"]["effis_burned_area"] = str(exc)

        try:
            wc = cached_worldcover(geojson_str, aoi_area)
            result["forest_biomass"].update(wc)
            if wc.get("worldcover_tile_warnings"):
                result["warnings"]["worldcover_partial"] = "; ".join(wc["worldcover_tile_warnings"])
        except Exception as exc:
            result["warnings"]["worldcover"] = str(exc)

        try:
            bio = cached_biomass(geojson_str, aoi_area)
            result["forest_biomass"].update(bio)
            if bio.get("biomass_tile_warnings"):
                result["warnings"]["biomass_partial"] = "; ".join(bio["biomass_tile_warnings"])
        except Exception as exc:
            result["warnings"]["cci_biomass"] = str(exc)

        if current:
            score, label, components = portal_hazard_score(current, ndmi=None)
            result["hazard"] = {
                "portal_screening_score_0_100": score,
                "screening_class": label,
                "components": components,
                "official_fwi_date": fwi_day.isoformat(),
                "official_fwi_note": "Use the Copernicus EFFIS FWI map layer for the official harmonized European fire-danger product.",
            }
        else:
            result["hazard"] = {
                "portal_screening_score_0_100": None,
                "screening_class": "Unavailable",
                "components": {},
                "official_fwi_date": fwi_day.isoformat(),
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

hazard_labels_ro = {"Low": "Scăzut", "Moderate": "Moderat", "High": "Ridicat", "Very high": "Foarte ridicat", "Extreme": "Extrem", "Unavailable": "Indisponibil"}
hazard_label = hazard_labels_ro.get(haz.get("screening_class"), haz.get("screening_class")) if RO else haz.get("screening_class")

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("AOI", f"{result['aoi']['area_ha']:,.1f} ha")
m2.metric(t("Acoperire forestieră", "Forest cover"), f"{fb.get('forest_fraction_pct', float('nan')):.1f}%" if fb.get("forest_fraction_pct") is not None else "n/a")
m3.metric(t("Biomasă medie AGB", "Mean AGBD"), f"{fb.get('agb_mean_mg_ha', float('nan')):.1f} Mg/ha" if fb.get("agb_mean_mg_ha") is not None else "n/a")
m4.metric(t("Focare recente", "Recent hotspots"), fire.get("hotspots", "n/a"))
m5.metric(t("Suprafață arsă", "Burned area"), f"{burn.get('burned_area_ha', 0):,.1f} ha")
m6.metric(t("Screening hazard", "Hazard screening"), f"{haz.get('portal_screening_score_0_100','n/a')} / 100", hazard_label)

left, right = st.columns([1.05, 1.15], gap="large")
with left:
    st.subheader(t("Context meteo și umiditatea solului", "Weather and soil-moisture context"))
    weather_rows = [
        [t("Temperatură", "Temperature"), weather.get("temperature_2m"), "°C"],
        [t("Umiditate relativă", "Relative humidity"), weather.get("relative_humidity_2m"), "%"],
        [t("Viteza vântului", "Wind speed"), weather.get("wind_speed_10m"), "km/h"],
        [t("Rafala de vânt", "Wind gust"), weather.get("wind_gusts_10m"), "km/h"],
        [t("Deficit de presiune a vaporilor", "Vapour pressure deficit"), weather.get("vapour_pressure_deficit"), "kPa"],
        [t("Precipitații", "Precipitation"), weather.get("precipitation"), "mm"],
        [t("Umiditatea solului 0–1 cm", "Soil moisture 0–1 cm"), weather.get("soil_moisture_0_to_1cm"), "m³/m³"],
        [t("Umiditatea solului 1–3 cm", "Soil moisture 1–3 cm"), weather.get("soil_moisture_1_to_3cm"), "m³/m³"],
        [t("Umiditatea solului 3–9 cm", "Soil moisture 3–9 cm"), weather.get("soil_moisture_3_to_9cm"), "m³/m³"],
        [t("Umiditatea solului 9–27 cm", "Soil moisture 9–27 cm"), weather.get("soil_moisture_9_to_27cm"), "m³/m³"],
        [t("Umiditatea solului 27–81 cm", "Soil moisture 27–81 cm"), weather.get("soil_moisture_27_to_81cm"), "m³/m³"],
    ]
    st.dataframe(pd.DataFrame(weather_rows, columns=[t("Indicator", "Indicator"), t("Valoare", "Value"), t("Unitate", "Unit")]), hide_index=True, use_container_width=True)

with right:
    st.subheader(t("Acoperirea forestieră și biomasa", "Forest cover and biomass"))
    forest_rows = [
        [t("Suprafață cu arbori (WorldCover)", "Tree-cover area (WorldCover)"), fb.get("forest_area_ha"), "ha"],
        [t("Fracție cu acoperire arborată", "Tree-cover fraction"), fb.get("forest_fraction_pct"), "%"],
        [t("Biomasă supraterană medie ESA CCI", "Mean ESA CCI above-ground biomass density"), fb.get("agb_mean_mg_ha"), "Mg/ha"],
        [t("Biomasă mediană ESA CCI", "Median ESA CCI AGB"), fb.get("agb_median_mg_ha"), "Mg/ha"],
        [t("Percentila 90 ESA CCI AGB", "90th percentile ESA CCI AGB"), fb.get("agb_p90_mg_ha"), "Mg/ha"],
        [t("AGB medie pentru pixelii cu biomasă > 0", "Mean AGB for biomass-positive pixels"), fb.get("agb_mean_positive_mg_ha"), "Mg/ha"],
        [t("Incertitudine medie AGB (deviație standard)", "Mean AGB uncertainty (standard deviation)"), fb.get("agb_standard_deviation_mean_mg_ha"), "Mg/ha"],
        [t("Pixeli CCI analizați", "CCI pixels sampled"), fb.get("agb_pixels"), "100-m cells"],
        [t("Biomasă supraterană totală estimată în AOI", "Estimated total AGB over AOI"), fb.get("agb_total_aoi_mg_est"), "Mg"],
    ]
    st.dataframe(pd.DataFrame(forest_rows, columns=[t("Indicator", "Indicator"), t("Valoare", "Value"), t("Unitate", "Unit")]), hide_index=True, use_container_width=True)
    st.caption(t(
        f"ESA CCI Biomass v{CCI_VERSION} pentru {CCI_YEAR} are rezoluție de 100 m. AGB este masa uscată a componentelor lemnoase supraterane pe hectar. Valorile din portal sunt estimări de teledetecție pentru screening, nu inventar forestier de teren.",
        f"ESA CCI Biomass v{CCI_VERSION} for {CCI_YEAR} has 100 m grid spacing. AGB is oven-dry above-ground woody biomass per hectare. Portal values are remote-sensing screening estimates, not a field forest inventory.",
    ))

classes = fb.get("worldcover_classes") or {}
if classes:
    st.subheader(t("Compoziția ESA WorldCover", "ESA WorldCover composition"))
    wc_ro = {10:"Acoperire arborată",20:"Tufăriș",30:"Pajiști",40:"Teren agricol",50:"Suprafață construită",60:"Vegetație rară / sol neacoperit",70:"Zăpadă și gheață",80:"Corpuri de apă permanente",90:"Zonă umedă erbacee",95:"Mangrove",100:"Mușchi și licheni"}
    class_rows = []
    for name, d in classes.items():
        code = d.get("class_code")
        class_rows.append({
            t("Clasa de acoperire", "Land-cover class"): wc_ro.get(code, name) if RO else name,
            t("Cod", "Code"): code,
            t("Suprafață estimată (ha)", "Area (ha, estimated)"): d.get("area_ha_est"),
            "AOI (%)": d.get("percent"),
        })
    df_classes = pd.DataFrame(class_rows)
    st.dataframe(df_classes.sort_values("AOI (%)", ascending=False), hide_index=True, use_container_width=True)

hourly = st.session_state.get("hourly", pd.DataFrame())
if not hourly.empty:
    st.subheader(t("Următoarele 72 de ore", "Next 72 hours"))
    chart_df = hourly[[c for c in ["time", "temperature_2m", "relative_humidity_2m", "wind_speed_10m", "soil_moisture_0_to_1cm"] if c in hourly.columns]].copy()
    melted = chart_df.melt(id_vars="time", var_name="indicator", value_name="value")
    fig = px.line(melted, x="time", y="value", color="indicator", facet_row="indicator", height=620)
    fig.update_yaxes(matches=None)
    fig.update_layout(showlegend=False, margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig, use_container_width=True)

st.subheader(t("Detecții de incendiu în poligonul selectat", "Fire detections in selected polygon"))
fires_aoi = st.session_state.get("fires_aoi")
if isinstance(fires_aoi, gpd.GeoDataFrame) and not fires_aoi.empty:
    cols = [c for c in ["acq_date", "acq_time", "satellite", "instrument", "confidence", "frp", "bright_ti4", "latitude", "longitude"] if c in fires_aoi.columns]
    st.dataframe(fires_aoi[cols], hide_index=True, use_container_width=True)
else:
    st.caption(t("Nu au fost returnate detecții FIRMS pentru acest AOI și interval.", "No FIRMS detections were returned for this AOI/window."))

if result.get("warnings"):
    with st.expander(t("Avertismente privind sursele de date / module indisponibile", "Data-source warnings / unavailable modules")):
        for k, v in result["warnings"].items():
            st.warning(f"{k}: {v}")

st.subheader(t("Descărcare raport și AOI", "Download report and AOI"))
html_report = make_html_report(result, language="ro" if RO else "en")
geojson_bytes = aoi.to_json().encode("utf-8")
json_bytes = json.dumps(result, ensure_ascii=False, indent=2, default=str).encode("utf-8")

b1, b2, b3 = st.columns(3)
b1.download_button(t("⬇ Raport HTML", "⬇ HTML report"), html_report.encode("utf-8"), "PREPARE_WP4_wildfire_AOI_report.html", "text/html", use_container_width=True)
b2.download_button(t("⬇ Analiză JSON", "⬇ Analysis JSON"), json_bytes, "PREPARE_WP4_wildfire_AOI_analysis.json", "application/json", use_container_width=True)
b3.download_button(t("⬇ AOI GeoJSON", "⬇ AOI GeoJSON"), geojson_bytes, "PREPARE_WP4_wildfire_AOI.geojson", "application/geo+json", use_container_width=True)

st.caption(t(
    "Notă operațională: detecțiile FIRMS sunt anomalii termice satelitare și pot include surse de căldură care nu sunt incendii de vegetație; umiditatea solului Open-Meteo este modelată; ESA CCI Biomass și WorldCover au incertitudini spațiale și temporale. Portalul este pentru cercetare, screening și conștientizare situațională, nu pentru comandă operativă în situații de urgență.",
    "Operational note: FIRMS detections are satellite thermal anomalies and can include non-wildfire heat sources; Open-Meteo soil moisture is modelled; ESA CCI Biomass and WorldCover have spatial/temporal uncertainty. This portal is for research, screening and situational awareness, not emergency command decisions.",
))
