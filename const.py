DOMAIN = "fmi"
API_DESCRIBE_STORED_QUERIES_URL = "https://opendata.fmi.fi/wfs/${lang}?request=describeStoredQueries"
API_GET_FEATURE_URL = "https://opendata.fmi.fi/wfs/${lang}?request=getFeature"
API_GET_PARAMS_URL = "https://opendata.fmi.fi/meta?observableProperty=${property}&language=${lang}"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.5249.62 Safari/537.36"
DEFAULT_SCAN_INTERVAL = 5

LANGUAGES = ["eng", "fin"]
TARGET_TYPES = ["fmisid", "place", "geoid", "latlon"]

CONF_LABEL = "label"
CONF_LANG = "language"
CONF_QUERY_LABEL = "query_label"
CONF_QUERY_ID = "query_id"
CONF_PARAMETER = "parameter"
CONF_TARGET_TYPE = "target_type"
CONF_TARGET = "target"
CONF_FORECAST_HOURS = "forecast_hours"
CONF_FORECAST_PAST_HOURS = "forecast_past_hours"
CONF_FORECAST_STEP = "forecast_step"
