DOMAIN = "fmi"
API_BASE_URL = "https://opendata.fmi.fi/wfs?service=WFS&version=2.0.0&request=getFeature"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.5249.62 Safari/537.36"
DEFAULT_SCAN_INTERVAL = 5

SENSOR_CONFIGS = [{"id": "Waterlevel", "query": "fmi::observations::mareograph::instant::simple",
                   "is_forecast": False, "param": "WLEVN2K_PT1S_INSTANT", "icon": "mdi:waves-arrow-up", "unit": "mm"},
                  {"id": "Waterlevel forecast", "query": "fmi::forecast::sealevel::point::simple", "param": "SeaLevelN2000",
                   "is_forecast": True, "icon": "mdi:waves-arrow-up", "unit": "cm"},
                  {"id": "UVI", "query": "fmi::observations::radiation::simple", "param": "UVB_U",
                   "is_forecast": False, "icon": "mdi:sun-wireless", "unit": "UVI"}]

SENSOR_TYPES = ["Waterlevel", "Waterlevel forecast", "UVI"]

CONF_LABEL = "label"
CONF_SENSOR_TYPE = "sensor_type"
CONF_FMISID = "fmisid"
CONF_STEP = "step"
CONF_FORECAST_HOURS = "forecast_hours"
CONF_FORECAST_PAST_HOURS = "forecast_past_hours"
