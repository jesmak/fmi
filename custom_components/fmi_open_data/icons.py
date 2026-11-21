"""The kind of a measurement, by its FMI parameter name, for its icon in icons.json.

FMI names its parameters in families (ta_pt1h_avg, ta_p1d_avg, t2m and temperature are all air temperature), in
Finnish and English, so the rules match the start of the lowercased name. The first rule that matches wins, so a rule
comes before any broader one that would also match its names.
"""

import re

# A sensor whose parameter no rule knows keeps the generic weather icon.
KIND_OTHER = "measurement"

_RULES = [
    # STUK: the dose rate, and the air samples' nuclides (Cs-137) and their activity.
    ("radioactivity", r"dr_|drs1_|ac_p7d|[a-z]{1,2}-\d+$"),
    # The urban air quality queries, the forecasts' concentrations and the EMEP filters' compounds (q...).
    ("air_quality", r"aqindex|pm10|pm25|no2|no_|nox|o3|so2|co_|trsc|oztot|ozone|q|(co|no|so2)concentration"),
    ("snow_on_ice", r"sndice"),
    ("ice", r"ice_pt|ict_|icethickness|meanicethickness|iceconcentration|snow_ice"),
    ("snow", r"snow|snd|sns_|swe_"),
    ("water_temperature", r"tw($|_|p)|twater|temperaturesea"),
    ("dew_point", r"td($|_|p)|dewpoint|kastep"),
    ("ground_temperature", r"ts($|_|n)|tg_|tie|trs|trg|maal|minimumgroundtemperature"),
    ("temperature", r"t($|2m)|ta|ilma|temperature|tmax|tmin|tday|tmon|maximumtemperature|minimumtemperature|monthlymeantemperature"),
    ("humidity", r"rh|humidity|relativehumidity|koste"),
    ("pressure", r"p_sea|pressure|pa_|pa0|pap|po$|p0_|ipaine|dipaine"),
    ("wind_gust", r"wg($|_|a_)|windgust|hourlymaximumgust|maximumwind|mtuuli"),
    ("wind_direction", r"wd|winddirection|tsuunt"),
    ("wind_speed", r"ws($|_|\d|a_|c_|p)|windspeed|ktuuli"),
    ("precipitation_intensity", r"pri|rr$|rint|ri_|rain$|precipitationconv|precipitationlarge"),
    ("precipitation", r"pra|precipitation1h|precipitationamount|monthlyprecipitation|rr(\d|day|mon)|r_1h|rsum|ndpr"),
    ("cloud_base", r"ch\d_|clhb|clh\d|cloudheight|cloudceiling|tempocloudceiling"),
    ("cloud_cover", r"n$|n_man|cla|clap|totalcloudcover|lowcloudcover|mediumcloudcover|highcloudcover"),
    ("visibility", r"vis"),
    ("uv", r"uv"),
    ("sunshine", r"sund"),
    ("solar_radiation", r"glob|dir_|diff_|net_|lwin|lwout|refl|par|radiation"),
    ("water_level", r"wlev|wliv|watlev|sealevel"),
    ("waves", r"wave|sigwave|modalwdi|wh(_|d)|wtp|tz_|current|seawatervelocity"),
    ("magnetic_field", r"magn"),
]
_COMPILED = [(kind, re.compile(pattern)) for kind, pattern in _RULES]


def parameter_kind(parameter: str) -> str:
    name = parameter.lower()
    return next((kind for kind, pattern in _COMPILED if pattern.match(name)), KIND_OTHER)
