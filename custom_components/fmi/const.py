import re

DOMAIN = "fmi"
ATTRIBUTION = "Data provided by Finnish Meteorological Institute (FMI)"
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
API_TIME_FORMAT = "%Y-%m-%d%%20%H:%M:%S"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.5249.62 Safari/537.36"
DEFAULT_SCAN_INTERVAL = 5

# A station can stop reporting for a while without being broken, so data only
# counts as stale after a generous delay. Both settings apply to every sensor.
DEFAULT_NO_DATA_ISSUE = True
DEFAULT_NO_DATA_ISSUE_HOURS = 24
# Aggregate queries report a period only once it is over, so their newest value
# can legitimately be a whole period old. The stale data limit never goes below these.
MINIMUM_STALE_HOURS = {
    "::daily": 3 * 24,
    "::monthly": 62 * 24,
    "::yearly": 2 * 366 * 24,
}

# Every warning in force, 0-5 days ahead. The feed lists CAP documents; each one
# has its texts in Finnish, Swedish and English, so one feed serves every language.
API_WARNINGS_FEED_URL = "https://alerts.fmi.fi/cap/feed/atom_fi-FI.xml"
WARNINGS_SCAN_INTERVAL = 10

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
CONF_LOCATION = "location"
CONF_WARNING_TYPES = "warning_types"

# Config subentry types: one subentry per sensor, and one per place whose warnings are followed.
SUBENTRY_SENSOR = "sensor"
SUBENTRY_WARNINGS = "warnings"

# Before 3.0 every sensor was a config entry of its own, and warnings entries were
# told apart by this key. Only the migration still reads it.
CONF_ENTRY_TYPE = "entry_type"
ENTRY_TYPE_WARNINGS = "warnings"

# The warning types of FMI's CAP profile, https://alerts.fmi.fi/cap/profile/v1.1.0
WARNING_TYPES = [
    "wind",
    "seaWind",
    "thunderstorm",
    "seaThunderstorm",
    "rain",
    "trafficWeather",
    "pedestrianSafety",
    "forestFireWeather",
    "hotWeather",
    "coldWeather",
    "uvNote",
    "seaWaveHeight",
    "seaWaterHeight",
    "seaIcing",
]
# The same types as translation keys, which must be lower case: "seaWind" is "sea_wind" in the warnings form.
# Subentries store FMI's own names.
WARNING_TYPE_KEYS = {warning_type: re.sub(r"(?<!^)(?=[A-Z])", "_", warning_type).lower() for warning_type in WARNING_TYPES}
# In rising order. "none" is the state when no warning is in force.
WARNING_LEVELS = ["none", "yellow", "orange", "red"]
DEFAULT_WARNINGS_RADIUS = 1000
DEFAULT_WARNINGS_LABEL = {"eng": "Warnings", "fin": "Varoitukset"}

# Name suffix of the diagnostic stale data sensor, in the sensor's language.
STALE_DATA_SUFFIX = {"eng": "stale data", "fin": "vanhentunut data"}
