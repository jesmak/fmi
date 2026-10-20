"""Writes docs/screenshots.json, the plan for the README's screenshots (see hass-screenshots).

A wet and windy afternoon in late September, with made-up data shaped like real FMI data. Run it after changing the
data, then shoot the images: python3 docs/screenshots.py && npm run shoot -- <this repo> in hass-screenshots.
"""

import json
import math
import random
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

random.seed(20260924)
LOCAL = timezone(timedelta(hours=3))
CLOCK = datetime(2026, 9, 24, 14, 0, tzinfo=LOCAL)
NOW = CLOCK.astimezone(UTC)
ATTR = "Data provided by Finnish Meteorological Institute (FMI)"


def iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def hours(days: float) -> list[datetime]:
    """Hour starts from days ago up to the last full hour."""
    count = int(days * 24)
    return [NOW - timedelta(hours=h) for h in range(count, 0, -1)]


def smooth_noise(n: int, step: float, keep: float = 0.85) -> list[float]:
    """Red noise: each value leans on the one before it."""
    value, out = 0.0, []
    for _ in range(n):
        value = value * keep + random.gauss(0, step)
        out.append(value)
    return out


def local_hour(t: datetime) -> int:
    return t.astimezone(LOCAL).hour


def days_ago(t: datetime) -> float:
    return (NOW - t).total_seconds() / 86400


# --- Rain: which days it rained over the last month, in mm. Today's 6.2 mm so far.
RAIN_DAYS = {
    29: 3.1,
    27: 0.4,
    26: 11.8,
    25: 2.2,
    21: 0.6,
    20: 7.4,
    19: 1.0,
    15: 0.2,
    12: 4.6,
    11: 14.3,
    10: 1.8,
    6: 0.8,
    5: 3.5,
    2: 0.3,
    1: 2.4,
}
TODAY_RAIN = 6.2
RAIN_RATE = 1.4


def rain_statistics() -> list[list]:
    """A daily total that resets at midnight, as hourly rows."""
    rows = []
    for t in hours(31):
        local = t.astimezone(LOCAL)
        day_index = (CLOCK.date() - local.date()).days
        if day_index == 0:
            # Rain since 10 this morning.
            fraction = max(0.0, min(1.0, (local.hour - 9) / 4))
            total = round(TODAY_RAIN * fraction, 1)
        else:
            amount = RAIN_DAYS.get(day_index, 0.0)
            start_hour = 6 + (day_index * 7) % 12
            fraction = max(0.0, min(1.0, (local.hour + 1 - start_hour) / 5))
            total = round(amount * fraction, 1)
        rows.append([iso(t), total])
    return rows


def rained_on(t: datetime) -> bool:
    local = t.astimezone(LOCAL)
    day_index = (CLOCK.date() - local.date()).days
    if day_index == 0:
        return local.hour >= 10
    amount = RAIN_DAYS.get(day_index, 0.0)
    start_hour = 6 + (day_index * 7) % 12
    return amount > 1 and start_hour <= local.hour < start_hour + 5


# --- Air quality: low most of the time, a dusty spell and a smoky one, washed clean by today's rain.
def particles(base: float, episodes: dict[float, float], noise: float) -> list[list]:
    stamps = hours(30)
    wobble = smooth_noise(len(stamps), noise)
    rows = []
    for t, w in zip(stamps, wobble, strict=True):
        traffic = 1 + 0.5 * math.exp(-((local_hour(t) - 8) ** 2) / 4) + 0.4 * math.exp(-((local_hour(t) - 17) ** 2) / 5)
        episode = sum(peak * math.exp(-((days_ago(t) - day) ** 2) / 0.6) for day, peak in episodes.items())
        value = base * traffic + episode + w
        if rained_on(t):
            value *= 0.45
        rows.append([iso(t), round(max(0.3, value), 1)])
    return rows


def dose_rate() -> list[list]:
    stamps = hours(30)
    wobble = smooth_noise(len(stamps), 0.0015, 0.7)
    rows = []
    for t, w in zip(stamps, wobble, strict=True):
        # Rain brings radon's daughters down, and the dose rate rises for a few hours.
        value = 0.108 + w + (0.012 if rained_on(t) else 0)
        rows.append([iso(t), round(value, 3)])
    return rows


# --- The sea: a summer of water temperatures, with an upwelling at Hanko in mid-August.
def sea_temperature(peak: float, end: float, lag: float, upwelling: float = 0.0) -> list[list]:
    stamps = hours(90)
    wobble = smooth_noise(len(stamps), 0.03, 0.99)
    rows = []
    for t, w in zip(stamps, wobble, strict=True):
        d = 90 - days_ago(t)  # days since late June
        season = end + (peak - end) * math.exp(-(((d - 32 - lag) / 38) ** 2)) if d > 32 + lag else 15.2 + (peak - 15.2) * (d / (32 + lag))
        dip = upwelling * math.exp(-(((d - 51) / 3.5) ** 2))
        daily = 0.15 * math.sin((local_hour(t) - 9) / 24 * 2 * math.pi)
        rows.append([iso(t), round(season - dip + daily + w, 1)])
    return rows


def wave_height(calm: float, storm: float) -> list[list]:
    stamps = hours(7)
    wobble = smooth_noise(len(stamps), 0.05, 0.9)
    rows = []
    for t, w in zip(stamps, wobble, strict=True):
        d = days_ago(t)
        swell = calm * (1 + 0.6 * math.sin(d * 1.7)) + storm * math.exp(-((d - 0) ** 2) / 0.25)
        rows.append([iso(t), round(max(0.2, swell + w), 1)])
    return rows


def sea_level() -> tuple[list[list], list[dict]]:
    """Measured in mm for the past two days, and FMI's forecast in cm from six hours back to two days ahead."""

    def level(d: float) -> float:
        # The south-westerly pushes water in, peaking tonight, then a slow seiche.
        return 6 + 4 * math.sin(d * 2.4) + 38 * math.exp(-((d + 0.4) ** 2) / 0.35) - 8 * math.exp(-((d + 1.6) ** 2) / 0.3)

    stamps = hours(2)
    wobble = smooth_noise(len(stamps), 0.7, 0.8)
    measured = [[iso(t), round((level(days_ago(t)) + w) * 10)] for t, w in zip(stamps, wobble, strict=True)]
    forecast = []
    for h in range(-6, 49):
        t = NOW + timedelta(hours=h)
        forecast.append({"time": iso(t), "value": round(level(-h / 24) + 1.5, 1)})
    return measured, forecast


# --- The weather: rain and a strong south-westerly today, clearing towards the weekend.
DAILY = [
    ("rainy", 12.1, 8.4, 9.8, 100, 9.6),
    ("pouring", 10.4, 7.2, 14.6, 95, 11.2),
    ("cloudy", 9.8, 4.9, 0.6, 40, 5.1),
    ("partlycloudy", 11.3, 2.8, 0.0, 10, 3.4),
    ("sunny", 12.7, 1.9, 0.0, 5, 2.8),
]


def daily_forecast() -> list[dict]:
    day0 = CLOCK.replace(hour=0)
    return [
        {
            "datetime": (day0 + timedelta(days=d)).isoformat(),
            "condition": c,
            "temperature": hi,
            "templow": lo,
            "precipitation": p,
            "precipitation_probability": pp,
            "wind_speed": ws,
            "wind_bearing": 225,
        }
        for d, (c, hi, lo, p, pp, ws) in enumerate(DAILY)
    ]


def hourly_forecast() -> list[dict]:
    out = []
    for h in range(1, 25):
        t = CLOCK + timedelta(hours=h)
        hour = t.hour
        rain = 1.6 if h < 8 else (0.4 if h < 12 else 0.0)
        condition = "pouring" if 3 <= h <= 5 else "rainy" if rain else ("cloudy" if hour < 22 or hour > 5 else "night")
        out.append(
            {
                "datetime": t.isoformat(),
                "condition": condition,
                "temperature": round(11.2 - 2.6 * math.sin(min(h, 14) / 14 * math.pi / 2) + (0.8 if hour >= 9 else 0), 1),
                "precipitation": rain,
                "wind_speed": round(9.4 - h * 0.25, 1),
                "wind_bearing": 225,
            }
        )
    return out


def warning(identifier, kind, level, event, onset, expires, headline, description, impacts, parameters):
    return {
        "id": f"urn:oid:fi.fmi.warning.2.1.{identifier}",
        "type": kind,
        "level": level,
        "event": event,
        "severity": {"yellow": "Moderate", "orange": "Severe", "red": "Extreme"}[level],
        "onset": onset,
        "expires": expires,
        "headline": headline,
        "description": description,
        "impacts": impacts,
        "probability": None,
        "areas": ["Pirkanmaa"],
        "parameters": parameters,
    }


WARNINGS = [
    warning(
        "20260924.1102",
        "wind",
        "yellow",
        "Wind warning for land areas",
        "2026-09-24T12:00:00+03:00",
        "2026-09-25T03:00:00+03:00",
        "Yellow wind warning for land areas: Pirkanmaa, Thu 12.00 - Fri 3.00",
        "South-westerly gusts of up to 20 m/s.",
        "Falling trees may cause power cuts and disrupt traffic.",
        {"windIntensity": 20, "windIntensityUom": "m/s", "windDirection": 225},
    ),
    warning(
        "20260924.1131",
        "trafficWeather",
        "yellow",
        "Traffic weather warning",
        "2026-09-25T06:00:00+03:00",
        "2026-09-25T12:00:00+03:00",
        "Yellow traffic weather warning: Pirkanmaa, Fri 6.00 - 12.00",
        "Heavy rain and standing water make driving conditions poor.",
        "Driving conditions may be difficult. Allow more time for the journey.",
        {},
    ),
]

AIR_LINES = {
    "pm25": [(11, "Satisfactory", "#ffdd3a"), (26, "Fair", "#ffa600")],
    "pm10": [(21, "Satisfactory", "#ffdd3a"), (51, "Fair", "#ffa600")],
}


def air_chart(title: str, entity: str, lines, unit: str, top: str) -> dict:
    """A month of daily means, coloured by the air quality class, with the class limits as lines."""
    threshold = [{"value": 0, "color": "#43a047"}]
    previous = "#43a047"
    for value, _, colour in lines:
        threshold += [{"value": value, "color": previous}, {"value": value, "color": colour}]
        previous = colour
    return {
        "type": "custom:apexcharts-card",
        "cache": False,
        "experimental": {"color_threshold": True},
        "graph_span": "30d",
        "header": {"show": True, "show_states": True, "colorize_states": True, "title": title},
        "all_series_config": {"curve": "straight"},
        "apex_config": {
            "chart": {"height": "150px"},
            "legend": {"show": False},
            "annotations": {
                "yaxis": [
                    {
                        "y": value,
                        "borderColor": colour,
                        "strokeDashArray": 4,
                        "label": {
                            "text": f"{name} {value} {unit}",
                            "position": "left",
                            "textAnchor": "start",
                            "offsetX": 4,
                            "style": {"color": "black" if colour == "#ffdd3a" else "white", "background": colour},
                        },
                    }
                    for value, name, colour in lines
                ]
            },
        },
        "series": [
            {
                "entity": entity,
                "name": title,
                "stroke_width": 1.5,
                "float_precision": 1,
                "unit": unit,
                "statistics": {"type": "mean", "period": "day", "align": "middle"},
                "show": {"header_color_threshold": True},
                "color_threshold": threshold,
            }
        ],
        "yaxis": [{"min": 0, "max": top, "apex_config": {"tickAmount": 3}}],
    }


def line_chart(
    title: str,
    span: str,
    series: list[dict],
    unit_format: str,
    period: str = "hour",
    kind: str = "mean",
    yaxis=None,
    xaxis_format=None,
    **extra,
) -> dict:
    return {
        "type": "custom:apexcharts-card",
        "cache": False,
        "graph_span": span,
        "header": {"show": True, "show_states": True, "colorize_states": True, "title": title},
        "all_series_config": {"curve": "smooth", "stroke_width": 1.5, "statistics": {"type": kind, "period": period, "align": "middle"}},
        "apex_config": {
            "chart": {"height": "150px"},
            "legend": {"show": False},
            **({"xaxis": {"labels": {"format": xaxis_format}}} if xaxis_format else {}),
        },
        "series": series,
        "yaxis": [{**(yaxis or {}), "apex_config": {"tickAmount": 4, "forceNiceScale": True, "labels": {"formatter": unit_format}}}],
        **extra,
    }


WARNINGS_MARKDOWN = """{% set warnings = state_attr('sensor.tampere_warning_level', 'warnings') or [] %}
{% set active = state_attr('sensor.tampere_warning_level', 'active_warnings') or 0 %}
{% for w in warnings %}
<ha-alert alert-type="{{ 'error' if w.level == 'red' else 'warning' }}" title="{{ w.event }}">
<b>{{ 'In force now.' if loop.index <= active else 'Coming.' }}</b> {{ w.description }} {{ w.impacts }}<br>
<i>{{ as_timestamp(w.onset) | timestamp_custom('%a %H:%M') }} – {{ as_timestamp(w.expires) | timestamp_custom('%a %H:%M') }}</i>
</ha-alert>
{% else %}
<ha-alert alert-type="success">No warnings</ha-alert>
{% endfor %}"""


def fmt(unit: str, digits: int) -> str:
    """An axis label formatter for apexcharts-card."""
    return f"EVAL:function(value) {{ return value.toFixed({digits}) + ' {unit}'; }}"


def main():
    sea_measured, sea_forecast = sea_level()
    pm25 = particles(2.4, {9.3: 17.0, 21.5: 7.0}, 0.3)
    pm10 = particles(5.0, {9.3: 22.0, 16.0: 38.0, 21.5: 9.0}, 0.5)
    dose = dose_rate()
    temps = {
        "sensor.northern_baltic_water_temperature": sea_temperature(18.4, 13.9, 4),
        "sensor.hanko_water_temperature": sea_temperature(19.6, 12.8, 0, upwelling=5.2),
        "sensor.gulf_of_finland_water_temperature": sea_temperature(18.6, 13.5, 8),
        "sensor.helsinki_water_temperature": sea_temperature(19.9, 13.1, 2),
    }
    waves = {
        "sensor.northern_baltic_wave_height": wave_height(0.9, 1.6),
        "sensor.gulf_of_finland_wave_height": wave_height(0.6, 1.0),
    }
    rain = rain_statistics()

    def measurement(name: str, value, unit: str, **attributes) -> dict:
        return {
            "state": str(value),
            "attributes": {
                "friendly_name": name,
                "unit_of_measurement": unit,
                "state_class": "measurement",
                "attribution": ATTR,
                **attributes,
            },
        }

    states = {
        "sensor.tampere_warning_level": {
            "state": "yellow",
            "attributes": {
                "friendly_name": "Tampere Warning level",
                "device_class": "enum",
                "options": ["none", "yellow", "orange", "red"],
                "attribution": ATTR,
                "label": "Tampere",
                "language": "en",
                "active_warnings": 1,
                "warnings": WARNINGS,
            },
        },
        "sensor.tampere_harmala_precipitation_today": measurement(
            "Tampere Härmälä Precipitation today", TODAY_RAIN, "mm", device_class="precipitation"
        ),
        "sensor.tampere_harmala_precipitation_intensity": measurement(
            "Tampere Härmälä Precipitation intensity", RAIN_RATE, "mm/h", device_class="precipitation_intensity"
        ),
        "sensor.tampere_air_quality_index": measurement("Tampere Air quality index", 1, ""),
        "sensor.tampere_pm2_5": measurement("Tampere PM2.5", pm25[-1][1], "µg/m³"),
        "sensor.tampere_pm10": measurement("Tampere PM10", pm10[-1][1], "µg/m³"),
        "sensor.tampere_dose_rate": measurement("Tampere Dose rate", dose[-1][1], "µSv/h"),
        "sensor.hanko_water_level": measurement("Hanko Water level", sea_measured[-1][1], "mm"),
        "sensor.hanko_sea_level_forecast": measurement(
            "Hanko Sea level forecast", sea_forecast[6]["value"], "cm", forecast=sea_forecast, forecast_hours=48, forecast_past_hours=6
        ),
        **{entity: measurement(entity, rows[-1][1], "°C", device_class="temperature") for entity, rows in temps.items()},
        **{entity: measurement(entity, rows[-1][1], "m") for entity, rows in waves.items()},
    }
    units = {
        "sensor.tampere_harmala_precipitation_today": "mm",
        "sensor.tampere_pm2_5": "µg/m³",
        "sensor.tampere_pm10": "µg/m³",
        "sensor.tampere_dose_rate": "µSv/h",
        "sensor.hanko_water_level": "mm",
        **{entity: "°C" for entity in temps},
        **{entity: "m" for entity in waves},
    }
    series = {
        "sensor.tampere_harmala_precipitation_today": rain,
        "sensor.tampere_pm2_5": pm25,
        "sensor.tampere_pm10": pm10,
        "sensor.tampere_dose_rate": dose,
        "sensor.hanko_water_level": [[t, v] for t, v in [(row[0], row[1]) for row in sea_measured]],
        **temps,
        **waves,
    }
    statistics = {entity: {"unit": units[entity], "mean": rows} for entity, rows in series.items()}

    gauge = {
        "type": "custom:gauge-card-pro",
        "entity": "sensor.tampere_air_quality_index",
        "header": "Air quality, Tampere",
        "needle": True,
        "min": 0,
        "max": 5.5,
        "round": "small",
        "value_texts": {
            "primary": {
                "value": "{{ ['Unknown', 'Good', 'Satisfactory', 'Fair', 'Poor', 'Very poor']"
                "[states('sensor.tampere_air_quality_index') | int(0)] }}"
            },
            "secondary": {"value": "Air quality index"},
        },
        "segments": [
            {"from": 0, "color": "#009AC7"},
            {"from": 0.5, "color": "#43a047"},
            {"from": 1.5, "color": "#ffdd3a"},
            {"from": 2.5, "color": "#ffa600"},
            {"from": 3.5, "color": "#db4437"},
            {"from": 4.5, "color": "#6400e4"},
        ],
    }
    sections = [
        {
            "type": "grid",
            "cards": [
                {"type": "heading", "heading": "Tampere", "icon": "mdi:weather-pouring"},
                {
                    "type": "weather-forecast",
                    "entity": "weather.tampere",
                    "forecast_type": "daily",
                    "show_current": True,
                    "show_forecast": True,
                },
                {
                    "type": "weather-forecast",
                    "entity": "weather.tampere",
                    "forecast_type": "hourly",
                    "show_current": False,
                    "show_forecast": True,
                },
                {"type": "markdown", "title": "Weather warnings", "content": WARNINGS_MARKDOWN},
                {
                    "type": "custom:compact-rain-gauge-card",
                    "entity": "sensor.tampere_harmala_precipitation_today",
                    "hourly_rate_entity": "sensor.tampere_harmala_precipitation_intensity",
                    "max_level": 20,
                    "show_yesterday": True,
                    "show_week": True,
                    "show_month": True,
                    "show_daily_chart": True,
                    "grid_options": {"columns": 12, "rows": "auto"},
                },
            ],
        },
        {
            "type": "grid",
            "cards": [
                {"type": "heading", "heading": "Air", "icon": "mdi:weather-windy"},
                gauge,
                air_chart("PM2.5", "sensor.tampere_pm2_5", AIR_LINES["pm25"], "µg/m³", 30),
                air_chart("PM10", "sensor.tampere_pm10", AIR_LINES["pm10"], "µg/m³", 60),
                line_chart(
                    "Dose rate",
                    "30d",
                    [{"entity": "sensor.tampere_dose_rate", "name": "Dose rate", "float_precision": 3, "color": "#43a047"}],
                    fmt("µSv/h", 2),
                    period="day",
                    yaxis={"min": 0.09, "max": 0.13},
                ),
            ],
        },
        {
            "type": "grid",
            "cards": [
                {"type": "heading", "heading": "Sea", "icon": "mdi:waves"},
                {
                    "type": "custom:apexcharts-card",
                    "cache": False,
                    "graph_span": "4d",
                    "span": {"offset": "+2d"},
                    "now": {"show": True},
                    "header": {"show": True, "title": "Sea level, Hanko", "show_states": True, "colorize_states": True},
                    "all_series_config": {"curve": "smooth", "stroke_width": 1.5},
                    "apex_config": {"chart": {"height": "150px"}, "legend": {"show": False}},
                    "series": [
                        {
                            "entity": "sensor.hanko_water_level",
                            "name": "Measured",
                            "transform": "return x / 10",
                            "unit": "cm",
                            "float_precision": 0,
                            "extend_to": False,
                            "statistics": {"type": "mean", "period": "hour", "align": "middle"},
                        },
                        {
                            "entity": "sensor.hanko_sea_level_forecast",
                            "name": "Forecast",
                            "stroke_dash": 3,
                            "data_generator": (
                                "return entity.attributes.forecast.map((entry) => [new Date(entry.time).getTime(), entry.value]);"
                            ),
                            "show": {"in_header": False},
                        },
                    ],
                    "yaxis": [{"min": -10, "max": 50, "apex_config": {"tickAmount": 3, "labels": {"formatter": fmt("cm", 0)}}}],
                },
                line_chart(
                    "Water temperature",
                    "90d",
                    [
                        {"entity": "sensor.northern_baltic_water_temperature", "name": "Northern Baltic", "color": "orange"},
                        {"entity": "sensor.hanko_water_temperature", "name": "Hanko"},
                        {"entity": "sensor.gulf_of_finland_water_temperature", "name": "Gulf of Finland"},
                        {"entity": "sensor.helsinki_water_temperature", "name": "Helsinki"},
                    ],
                    fmt("°C", 0),
                    period="day",
                    xaxis_format="d MMM",
                    kind="max",
                ),
                line_chart(
                    "Wave height",
                    "7d",
                    [
                        {
                            "entity": "sensor.northern_baltic_wave_height",
                            "name": "Northern Baltic",
                            "color": "orange",
                            "float_precision": 1,
                        },
                        {"entity": "sensor.gulf_of_finland_wave_height", "name": "Gulf of Finland", "float_precision": 1},
                    ],
                    fmt("m", 1),
                    yaxis={"min": 0, "max": 3},
                ),
            ],
        },
    ]
    plan = {
        "resources": [
            "https://github.com/RomRider/apexcharts-card/releases/download/v2.2.3/apexcharts-card.js",
            "https://github.com/benjamin-dcs/gauge-card-pro/releases/download/v2.5.0/gauge-card-pro.js",
            "../../hass-cards/compact-rain-gauge-card/dist/compact-rain-gauge-card.js",
        ],
        "clock": CLOCK.isoformat(),
        "translations": {"fmi_open_data": "custom_components/fmi_open_data/translations"},
        "config": {
            "template": [
                {
                    "weather": [
                        {
                            "name": "Tampere",
                            "unique_id": "tampere_weather",
                            "condition_template": "rainy",
                            "temperature_template": "{{ 11.2 }}",
                            "apparent_temperature_template": "{{ 7.4 }}",
                            "humidity_template": "{{ 94 }}",
                            "pressure_template": "{{ 996 }}",
                            "wind_speed_template": "{{ 9.4 }}",
                            "wind_gust_speed_template": "{{ 18.2 }}",
                            "wind_bearing_template": "{{ 225 }}",
                            "temperature_unit": "°C",
                            "pressure_unit": "hPa",
                            "wind_speed_unit": "m/s",
                            "precipitation_unit": "mm",
                            "attribution_template": ATTR,
                            "forecast_daily_template": "{{ " + json.dumps(daily_forecast()) + " }}",
                            "forecast_hourly_template": "{{ " + json.dumps(hourly_forecast()) + " }}",
                        }
                    ]
                }
            ]
        },
        "entities": {"sensor.tampere_warning_level": {"platform": "fmi_open_data", "translation_key": "warning_level"}},
        "states": states,
        "statistics": statistics,
        "shots": [{"name": "dashboard", "width": 1280, "view": {"type": "sections", "max_columns": 3, "sections": sections}}],
    }
    Path(__file__).with_name("screenshots.json").write_text(json.dumps(plan, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    print(sum(len(s["mean"]) for s in statistics.values()), "rows of statistics")


if __name__ == "__main__":
    main()
