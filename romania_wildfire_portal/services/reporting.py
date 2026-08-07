from __future__ import annotations

from datetime import datetime
import html
import json


def make_html_report(result: dict) -> str:
    def val(v, nd=2):
        if v is None:
            return "not available"
        if isinstance(v, float):
            return f"{v:,.{nd}f}"
        return str(v)

    rows = []
    for section, items in result.items():
        if not isinstance(items, dict):
            continue
        rows.append(f"<h2>{html.escape(section.replace('_',' ').title())}</h2><table>")
        for k, v in items.items():
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            rows.append(f"<tr><th>{html.escape(k.replace('_',' ').title())}</th><td>{html.escape(val(v))}</td></tr>")
        rows.append("</table>")

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html><head><meta charset='utf-8'><title>Romania Wildfire AOI Report</title>
<style>
body{{font-family:Arial,sans-serif;max-width:960px;margin:40px auto;color:#18221c;line-height:1.45}}
h1{{color:#9b2f1f}} h2{{margin-top:26px;border-bottom:2px solid #eee;padding-bottom:6px}}
table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid #ddd;padding:8px;text-align:left;vertical-align:top}} th{{width:38%;background:#f6f7f5}}
.note{{background:#fff4e8;border-left:4px solid #dd7a22;padding:12px;margin:18px 0}}
.source{{background:#f4f7f5;padding:12px;border-radius:8px}}
</style></head><body>
<h1>Romania Forest Wildfire Portal - AOI report</h1>
<p>Generated: {generated} (local application time)</p>
<div class='note'><b>Interpretation:</b> The portal screening hazard score is a transparent decision-support index, not the official Canadian Fire Weather Index. Use the displayed Copernicus EFFIS FWI and competent authorities for operational fire-danger decisions.</div>
{''.join(rows)}
<h2>Data provenance</h2>
<div class='source'>
<p><b>NASA FIRMS:</b> near-real-time VIIRS/MODIS thermal anomalies and Fire Radiative Power.</p>
<p><b>Copernicus EFFIS:</b> official European Fire Weather Index map and burned-area information.</p>
<p><b>Open-Meteo:</b> modelled weather, vapour pressure deficit and soil moisture.</p>
<p><b>NASA GEDI / MAAP / ORNL DAAC:</b> GEDI L4B gridded above-ground biomass density (1 km) accessed online through ORNL OGC services.</p>
<p><b>ESA WorldCover:</b> WorldCover 2021 v200 land-cover map (10 m) accessed directly from public cloud-optimized GeoTIFFs.</p>
</div>
<p><b>Important:</b> GEDI biomass is a statistical 1 km product and WorldCover represents reference-year 2021 land cover. The derived forest-adjusted biomass stock is a screening estimate and should not be substituted for a forest inventory.</p>
</body></html>"""
