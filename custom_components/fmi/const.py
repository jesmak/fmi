DOMAIN = "fmi"
API_DESCRIBE_STORED_QUERIES_URL = "https://opendata.fmi.fi/wfs/${lang}?request=describeStoredQueries"
API_GET_FEATURE_URL = "https://opendata.fmi.fi/wfs/${lang}?request=getFeature"
API_STATIONS_QUERY_ID = "fmi::ef::stations"
# The station-listing queries return nothing without a bounding box; this one
# covers Finland and its sea areas.
API_FINLAND_BBOX = "19,59,32,71"
API_GET_PARAMS_URL = "https://opendata.fmi.fi/meta?observableProperty=${property}&language=${lang}"
# %%20 renders as a literal "%20" once strftime is done with it. FMI accepts a
# space between date and time; an ISO "+00:00" offset would decode as a space
# server-side and be rejected, so timestamps are always formatted, never str()d.
API_TIME_FORMAT = '%Y-%m-%d%%20%H:%M:%S'
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.5249.62 Safari/537.36"
DEFAULT_SCAN_INTERVAL = 5
# A station can stop reporting for a while without being broken, so the no-data
# warning is debounced. Both the switch and the delay are per-sensor settings;
# these are the defaults for sensors that were configured before they existed.
DEFAULT_NO_DATA_ISSUE = True
DEFAULT_NO_DATA_ISSUE_HOURS = 24

LANGUAGES = ["eng", "fin"]

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
CONF_NEGATIVE_AS_ZERO = "negative_as_zero"
CONF_NO_DATA_ISSUE = "no_data_issue"
CONF_NO_DATA_ISSUE_HOURS = "no_data_issue_hours"
