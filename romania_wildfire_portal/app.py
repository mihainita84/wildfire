from __future__ import annotations

import io
import json
import os
from datetime import date, timedelta

import folium
import geopandas as gpd
import pandas as pd
import plotly.express as px
import streamlit as st
from PIL import Image, ImageDraw
from dotenv import load_dotenv
from folium.plugins import Draw, Fullscreen, MeasureControl, MousePosition
from streamlit_folium import st_folium

from services.geometry import geojson_to_gdf, area_ha, bounds_csv, centroid_lonlat
from services.firms import fetch_firms, filter_to_aoi, summarize_fires
from services.effis import (
    EFFIS_FORECAST_INFO,
    EFFIS_FORECAST_LAYERS,
    fetch_burned_areas,
    summarize_burned_areas,
    effis_thumbnail,
)
from services.openmeteo import fetch_weather, portal_hazard_score
from services.biomass_cci import biomass_stats, CCI_YEAR, CCI_VERSION, biomass_thumbnail
from services.worldcover import landcover_stats, worldcover_thumbnail
from services.reporting import make_html_report

load_dotenv()

DEFAULT_FIRMS_MAP_KEY = "87f35b3f6f3784bd1eba380d16e0198b"
FIRMS_MAP_KEY = os.getenv("FIRMS_MAP_KEY", DEFAULT_FIRMS_MAP_KEY).strip() or DEFAULT_FIRMS_MAP_KEY
PROJECT_URL = "https://utcb.ro/cercetare/programe-uefiscdi/pn-iv-pro-coex-2024-1-prepare/"
MAX_AOI_HA = 500.0  # 5 km²

st.set_page_config(page_title="PREPARE | Romania Wildfire Portal", page_icon="🔥", layout="wide")

language = st.sidebar.selectbox("Limbă / Language", ["Română", "English"], index=0)
RO = language == "Română"


def t(ro: str, en: str) -> str:
    return ro if RO else en


st.markdown(
    """
<style>
.block-container {padding-top: 1rem; max-width: 98rem;}
[data-testid="stMetric"] {background:rgba(247,247,244,.07);border:1px solid rgba(150,150,150,.25);padding:10px 14px;border-radius:12px;}
.hero {padding:16px 20px;border-radius:16px;background:linear-gradient(90deg,#3d211b,#8f2f1f);color:white;margin-bottom:10px}
.hero h1 {margin:0;font-size:2rem}.hero p{margin:.30rem 0 0 0;opacity:.92}
.project-card {border:1px solid rgba(150,150,150,.25);border-radius:14px;padding:12px 15px;margin:7px 0 12px 0;background:rgba(120,120,120,.05)}
.project-card b {color:#ef8b68}
.map-help {margin:0 0 0.5rem 0; opacity:0.82;}
</style>
""",
    unsafe_allow_html=True,
)

hero_sub = t(
    "PREPARE • WP4 Incendii de pădure și riscuri asociate • focare active • pericol de incendiu • biomasă • umiditatea solului • analize pe poligon",
    "PREPARE • WP4 Forest fires and related risks • active fires • fire danger • biomass • soil moisture • polygon analyses",
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
    st.header(t("Setări portal", "Portal settings"))
    st.success(t("Cheia NASA FIRMS este integrată", "NASA FIRMS key embedded"))
    source = st.selectbox(
        t("Senzor FIRMS", "FIRMS sensor"),
        ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "MODIS_NRT"],
        index=0,
    )
    day_range = st.slider(t("Fereastra focarelor recente (zile)", "Recent fire window (days)"), 1, 5, 2)
    fwi_day = st.date_input(
        t("Data straturilor EFFIS", "EFFIS layer date"),
        value=date.today(),
        min_value=date.today() - timedelta(days=5),
        max_value=date.today() + timedelta(days=8),
        help=t("Folosită pentru miniaturile EFFIS FWI și indicii derivați.", "Used for EFFIS FWI and derived-index thumbnails."),
    )
    st.divider()
    st.caption(t("Harta interactivă folosește doar OpenStreetMap și focarele active FIRMS, pentru performanță și stabilitate.", "The interactive map uses only OpenStreetMap and active FIRMS hotspots, for performance and stability."))
    st.caption(t("După analiză, portalul generează miniaturi separate pentru WorldCover, ESA CCI Biomass și indicii EFFIS de pericol de incendiu.", "After analysis, the portal generates separate thumbnails for WorldCover, ESA CCI Biomass and EFFIS fire-danger indices."))
    st.warning(t("Limita AOI: maximum 5 km² (500 ha). AOI mai mari sunt blocate pentru a evita căderi de performanță.", "AOI limit: maximum 5 km² (500 ha). Larger AOIs are blocked to avoid crashes or severe slowdown."))
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
def cached_worldcover(geojson_str: str, aoi_area: float):
    aoi = geojson_to_gdf(json.loads(geojson_str))
    return landcover_stats(aoi, aoi_area_ha=aoi_area)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_worldcover_thumb(geojson_str: str):
    aoi = geojson_to_gdf(json.loads(geojson_str))
    return worldcover_thumbnail(aoi)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_biomass_thumb(geojson_str: str):
    aoi = geojson_to_gdf(json.loads(geojson_str))
    return biomass_thumbnail(aoi)


@st.cache_data(ttl=86400, show_spinner=False)
def cached_effis_thumb(geojson_str: str, day_text: str, layer_name: str):
    aoi = geojson_to_gdf(json.loads(geojson_str))
    return effis_thumbnail(aoi, day_text, layer_name)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_active_fires_thumb(geojson_str: str, sensor: str, bbox: str, days: int):
    aoi = geojson_to_gdf(json.loads(geojson_str))
    fires = cached_firms(sensor, bbox, days)
    fires_aoi = filter_to_aoi(fires, aoi)
    return active_fires_thumbnail(aoi, fires_aoi)


def build_map():
    m = folium.Map(location=[45.9, 24.9], zoom_start=7, tiles="OpenStreetMap", control_scale=True, prefer_canvas=True)
    try:
        fires = cached_firms(source, "20.0,43.4,30.0,48.5", day_range)
        fg = folium.FeatureGroup(name=f"NASA FIRMS – {source}", overlay=True, show=True)
        for _, r in fires.iterrows():
            popup = (
                f"{source}<br>{r.get('acq_date','')} {r.get('acq_time','')}"
                f"<br>FRP: {r.get('frp','n/a')} MW<br>Confidence: {r.get('confidence','n/a')}"
            )
            folium.CircleMarker(
                [r.geometry.y, r.geometry.x], radius=3.8, color="#9e2619", fill=True,
                fill_color="#ff5a36", fill_opacity=.88, weight=1, popup=popup,
            ).add_to(fg)
        fg.add_to(m)
    except Exception as exc:
        st.sidebar.warning(t(f"Stratul FIRMS nu este disponibil: {exc}", f"FIRMS map layer unavailable: {exc}"))

    Draw(
        export=False,
        draw_options={
            "polyline": False,
            "rectangle": True,
            "circle": False,
            "circlemarker": False,
            "marker": False,
            "polygon": {"allowIntersection": False, "showArea": True},
        },
        edit_options={"edit": True, "remove": True},
    ).add_to(m)
    Fullscreen().add_to(m)
    MeasureControl(primary_length_unit="kilometers", primary_area_unit="hectares").add_to(m)
    MousePosition(position="bottomright", separator=" | ", prefix="Lat/Lon:").add_to(m)
    folium.LayerControl(collapsed=False, position="topright").add_to(m)
    return m


def active_fires_thumbnail(aoi: gpd.GeoDataFrame, fires_aoi: gpd.GeoDataFrame | None, size: int = 420) -> bytes:
    aoi = aoi.to_crs(4326)
    geom = aoi.geometry.iloc[0]
    west, south, east, north = geom.bounds
    dx = max(east - west, 0.01)
    dy = max(north - south, 0.01)
    pad_x = dx * 0.2 + 0.01
    pad_y = dy * 0.2 + 0.01
    west, south, east, north = west - pad_x, south - pad_y, east + pad_x, north + pad_y

    img = Image.new("RGBA", (size, size), (247, 247, 247, 255))
    draw = ImageDraw.Draw(img)

    def px(x):
        return int((x - west) / max(1e-9, east - west) * (size - 1))

    def py(y):
        return int((north - y) / max(1e-9, north - south) * (size - 1))

    draw.rectangle([0, 0, size - 1, size - 1], outline=(180, 180, 180, 255), width=1)
    a_w, a_s, a_e, a_n = geom.bounds
    pts = [(px(a_w), py(a_s)), (px(a_e), py(a_s)), (px(a_e), py(a_n)), (px(a_w), py(a_n)), (px(a_w), py(a_s))]
    draw.line(pts, fill=(0, 0, 0, 255), width=3)

    if isinstance(fires_aoi, gpd.GeoDataFrame) and not fires_aoi.empty:
        for _, row in fires_aoi.iterrows():
            x, y = px(row.geometry.x), py(row.geometry.y)
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(255, 90, 54, 220), outline=(140, 32, 16, 255), width=1)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


st.markdown(f"<p class='map-help'>{t('Desenați un poligon sau un dreptunghi. Harta interactivă a fost simplificată pentru a rămâne rapidă, iar miniaturile tematice sunt generate după analiză.', 'Draw a polygon or rectangle. The interactive map was simplified to stay fast, and thematic thumbnails are generated after analysis.')}</p>", unsafe_allow_html=True)
out = st_folium(build_map(), height=820, width=None, returned_objects=["all_drawings", "last_active_drawing"])

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

if aoi_area > MAX_AOI_HA:
    st.error(t(
        f"AOI-ul are {aoi_area:,.1f} ha și depășește limita admisă de {MAX_AOI_HA:.0f} ha (5 km²). Redesenati un poligon mai mic pentru a evita blocarea aplicației.",
        f"The AOI is {aoi_area:,.1f} ha and exceeds the allowed limit of {MAX_AOI_HA:.0f} ha (5 km²). Please redraw a smaller polygon to avoid app crashes.",
    ))
    st.stop()

run = st.button(t("▶ Analizează poligonul selectat", "▶ Analyse selected polygon"), type="primary", use_container_width=True)

previous_signature = st.session_state.get("analysis_aoi_signature")
if previous_signature != aoi_signature and not run:
    st.caption(t(
        f"AOI selectat: {aoi_area:,.1f} ha din maximum {MAX_AOI_HA:.0f} ha. Apăsați **Analizează poligonul selectat** pentru interogarea seturilor de date online și generarea miniaturilor tematice.",
        f"Selected AOI: {aoi_area:,.1f} ha out of the maximum {MAX_AOI_HA:.0f} ha. Click **Analyse selected polygon** to query the online datasets and generate thematic thumbnails.",
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
        "effis_fire_danger": {
            "forecast_date": fwi_day.isoformat(),
            "layers": {k: (EFFIS_FORECAST_INFO[k]["ro"] if RO else EFFIS_FORECAST_INFO[k]["en"]) for k in EFFIS_FORECAST_LAYERS}
        },
        "warnings": {},
    }

    thumbs: dict[str, bytes] = {}

    with st.spinner(t(
        "Interogare meteo, umiditatea solului, FIRMS, EFFIS, ESA CCI Biomass, ESA WorldCover și generare miniaturi…",
        "Querying weather, soil moisture, FIRMS, EFFIS, ESA CCI Biomass, ESA WorldCover and generating thumbnails…",
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
            thumbs[t("Focare active FIRMS", "FIRMS active fires")] = active_fires_thumbnail(aoi, fires_aoi)
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
            thumbs["ESA WorldCover 2021"] = cached_worldcover_thumb(geojson_str)
            if wc.get("worldcover_tile_warnings"):
                result["warnings"]["worldcover_partial"] = "; ".join(wc["worldcover_tile_warnings"])
        except Exception as exc:
            result["warnings"]["worldcover"] = str(exc)

        try:
            bio = cached_biomass(geojson_str, aoi_area)
            result["forest_biomass"].update(bio)
            thumbs[f"ESA CCI Biomass {CCI_YEAR}"] = cached_biomass_thumb(geojson_str)
            if bio.get("biomass_tile_warnings"):
                result["warnings"]["biomass_partial"] = "; ".join(bio["biomass_tile_warnings"])
        except Exception as exc:
            result["warnings"]["cci_biomass"] = str(exc)

        for short_name, layer_name in EFFIS_FORECAST_LAYERS.items():
            try:
                thumbs[f"EFFIS {short_name}"] = cached_effis_thumb(geojson_str, fwi_day.isoformat(), layer_name)
            except Exception as exc:
                result["warnings"][f"effis_{short_name.lower()}"] = str(exc)

        if current:
            score, label, components = portal_hazard_score(current, ndmi=None)
            result["hazard"] = {
                "portal_screening_score_0_100": score,
                "screening_class": label,
                "components": components,
                "official_fwi_date": fwi_day.isoformat(),
                "official_fwi_note": "Use the generated EFFIS thumbnail maps for the official harmonized European fire-danger context.",
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
    st.session_state["thumbnails"] = thumbs

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
m3.metric(t("Biomasă medie AGB", "Mean AGB"), f"{fb.get('agb_mean_mg_ha', float('nan')):.1f} Mg/ha" if fb.get("agb_mean_mg_ha") is not None else "n/a")
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

st.subheader(t("Context EFFIS pentru pericolul de incendiu", "EFFIS fire-danger context"))
effis_rows = []
for short_name in ["FWI", "FFMC", "ISI", "BUI", "DMC", "DC"]:
    effis_rows.append({
        t("Indice", "Index"): short_name,
        t("Descriere", "Description"): EFFIS_FORECAST_INFO[short_name]["ro"] if RO else EFFIS_FORECAST_INFO[short_name]["en"],
        t("Data", "Date"): result.get("effis_fire_danger", {}).get("forecast_date"),
    })
st.dataframe(pd.DataFrame(effis_rows), hide_index=True, use_container_width=True)
st.caption(t(
    "Aceste straturi provin din lanțul EFFIS/Canadian Fire Weather Index și completează scorul de screening al portalului. FWI este indicatorul general; FFMC, DMC și DC descriu uscarea combustibililor, iar ISI și BUI descriu propagarea și disponibilitatea combustibilului.",
    "These layers come from the EFFIS/Canadian Fire Weather Index chain and complement the portal screening score. FWI is the overall indicator; FFMC, DMC and DC describe fuel drying, while ISI and BUI describe spread potential and fuel availability.",
))

thumbs = st.session_state.get("thumbnails", {})
if thumbs:
    st.subheader(t("Miniaturi tematice generate pentru AOI", "Generated thematic thumbnails for the AOI"))
    items = list(thumbs.items())
    for i in range(0, len(items), 3):
        cols = st.columns(3)
        for col, (label, img_bytes) in zip(cols, items[i:i+3]):
            with col:
                st.image(img_bytes, caption=label, use_container_width=True)

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
    "Notă operațională: detecțiile FIRMS sunt anomalii termice satelitare și pot include surse de căldură care nu sunt incendii de vegetație; umiditatea solului Open-Meteo este modelată; ESA CCI Biomass și WorldCover au incertitudini spațiale și temporale; miniaturile EFFIS sunt destinate suportului de cercetare și screening. Portalul este pentru cercetare, screening și conștientizare situațională, nu pentru comandă operativă în situații de urgență.",
    "Operational note: FIRMS detections are satellite thermal anomalies and can include non-wildfire heat sources; Open-Meteo soil moisture is modelled; ESA CCI Biomass and WorldCover have spatial/temporal uncertainty; EFFIS thumbnails are meant for research support and screening. This portal is for research, screening and situational awareness, not emergency command decisions.",
))
