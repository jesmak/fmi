# FMI data for Home Assistant

## What is it?

A custom component that integrates with Finnish Meteorological Institute to retrieve data not typically part of
other weather integrations, such as seawater level, UV-index, snow thickness etc. Radiation data published by
STUK through the same API is also available.

Each sensor is one parameter from one observation station or forecast point. Add the integration once per value
you want to follow.

## Installation

### With HACS

1. Add this repository to HACS custom repositories
2. Search for FMI in HACS and install with type integration
3. Restart Home Assistant
4. Add the integration from the settings/integrations page of Home Assistant

### Manual

1. Download source code from latest release tag
2. Copy custom_components/fmi folder to your Home Assistant installation's config/custom_components folder.
3. Restart Home Assistant
4. Add the integration from the settings/integrations page of Home Assistant

No account or API key is needed. FMI's open data service is used anonymously.

## Configuration

The wizard discovers what is available at each step, so you do not need to look anything up by hand.

### Step 1 - language

| Name     | Type | Requirement  | Description                  | Default |
|----------|------|--------------|------------------------------|---------|
| language | enum | **Required** | Language used in API calls   | `eng`   |

The language affects the query titles and parameter descriptions returned by FMI.

### Step 2 - query

| Name        | Type | Requirement  | Description                                  | Default |
|-------------|------|--------------|----------------------------------------------|---------|
| query_label | enum | **Required** | Query type, listed from FMI's stored queries |         |

### Step 3 - location

| Name   | Type | Requirement  | Description                  | Default |
|--------|------|--------------|------------------------------|---------|
| target | enum | **Required** | Observation station or place |         |

For observation queries, only the stations that actually serve the query you chose are offered, so you cannot
pick one that will never return data for it. Forecast queries are interpolated to a point rather than tied to a
station, so all stations are offered for those. Either way they are ordered by distance from your Home
Assistant location:

```
Helsinki Mannerheimintie (100742) - 0 km
Helsinki Kaisaniemi (100971) - 1 km
Helsinki Katajanokka 2 (104053) - 2 km
```

You can also type a place name, or coordinates as `latitude,longitude`. The identifier type is worked out from
what you enter, so there is nothing to choose: digits are treated as an FMISID, a pair of numbers as
coordinates, and anything else as a place name. This works for STUK queries too, which have their own stations.


### Step 4 - parameter

| Name                | Type   | Requirement  | Description                                                               | Default |
|---------------------|--------|--------------|---------------------------------------------------------------------------|---------|
| parameter           | enum   | **Required** | Which parameter from the query data to use                                |         |
| negative_as_zero    | bool   | **Required** | Report -1 as 0                                                            | `false` |
| forecast_step       | int    | **Required** | Step between two values in minutes. Only shown for forecast type queries. | 30      |
| forecast_hours      | int    | **Required** | How many hours of forecasts to retrieve (starting from current time)      | 36      |
| forecast_past_hours | int    | **Required** | How many past hours of forecasts to retrieve (starting from current time) | 5       |

Only the parameters the chosen station actually reports are offered, with their descriptions and units:

```
rrday - Precipitation amount (mm)
tday - Air temperature (°C)
TG_PT12H_min - Ground minimum temperature (°C)
```

If a parameter you need is missing from the list you can still type its name.

Some parameters use `-1` to mean "no measurable value" rather than `0`. Daily precipitation is the common
case: a dry day reads `-1`, which distorts graphs and long term statistics. Enable **negative_as_zero** to
report those as `0`. Only exactly `-1` is affected, so a genuine `-1` degree temperature is left alone.

### Step 5 - name

| Name  | Type   | Requirement  | Description                                 | Default                     |
|-------|--------|--------------|---------------------------------------------|-----------------------------|
| label | string | **Required** | Name for the created sensor                 | station and parameter names |

A name is suggested from your choices, for example `Helsinki Kaisaniemi Air temperature`. The sensor can be
renamed later without losing its history.

## Changing a sensor later

Use **Reconfigure** from the sensor's menu to point an existing sensor at a different query, station or
parameter, and to change the -1 handling and forecast settings. The entity keeps its identity and history, so
this is the way to repair a sensor whose station has been decommissioned or whose parameter is no longer
published.

To rename a sensor, use Home Assistant's own entity settings. The name is not part of the sensor's identity, so
renaming does not affect its history.

## Upgrading from 1.x

Version 2 stops identifying sensors by their name, so that they can be renamed and repointed. Existing config
entries are migrated automatically on first start and keep their entities, history and statistics. Nothing
needs to be reconfigured.

## When a station or parameter stops working

FMI removes parameters from stations, and stations are occasionally decommissioned or renumbered. Neither shows
up as an error: the query simply returns nothing.

If a sensor gets no data for about an hour, the integration reports a repair issue in Home Assistant telling you whether the station returns nothing at all, or whether it is still reporting but no longer publishes your parameter, in which case the parameters it does publish are listed. Use Reconfigure to move the sensor to a
working station or parameter, and the issue clears itself.

## State attributes

All sensors return the following extra attributes.

| Name          | Type   | Description                                                 |
|---------------|--------|-------------------------------------------------------------|
| latitude      | float  | Latitude of the observation station                         |
| longitude     | float  | Longitude of the observation station                        |
| label         | string | Name given to the sensor                                    |
| language      | string | Language used in API calls                                  |
| query_id      | string | Query ID set when configuring the sensor                    |
| query_name    | string | Human readable name of the query                            |
| parameter     | string | Name of the returned parameter                              |
| location_type | string | Type of identifier used (fmisid/place/latlon)                |
| location_id   | string | Identifier value                                            |

Additionally, observation type sensors return the following extra attributes.
Observation type sensors return the latest known value as sensor state.

| Name   | Type     | Description                     |
|--------|----------|---------------------------------|
| time   | datetime | Time of the latest observation  |
| value  | string   | Value of the latest observation |

Additionally, forecast type sensors return the following extra attributes.
Forecast type sensors return the next known forecast value as sensor state.

| Name                | Type             | Description                                                       |
|---------------------|------------------|-------------------------------------------------------------------|
| forecast            | [{date, string}] | List of forecast values as objects containing time and value keys |
| forecast_hours      | int              | Configured number of forecast hours                               |
| forecast_past_hours | int              | Configured number of past forecast hours                          |
| forecast_step       | int              | Configured step between two values in minutes                     |

### Usage with apexcharts-card

One example use case for this integration could be to show waterlevel values with [apexcharts-card](https://github.com/RomRider/apexcharts-card).

Below is an example configuration for showing waterlevels (2 days of observations and 2 days of forecasts, 2 hour overlap).
Same kind of configuration could of course be used for other observation/forecast types aswell.

![fmi_waterlevel](fmi_waterlevel.png)

```
type: custom:apexcharts-card
graph_span: 4d
span:
  offset: +2d
now:
  show: true
header:
  show: true
  title: Waterlevel, Hamina
  show_states: true
  colorize_states: true
all_series_config:
  curve: straight
apex_config:
  chart:
    height: 150px
  legend:
    show: false
  xaxis:
    labels:
      format: dd.MM.
series:
  - entity: sensor.fmi_waterlevel_hamina
    transform: return x/10
    stroke_width: 1
    float_precision: 3
    yaxis_id: waterlevel
    name: Mitattu
    color: orange
    unit: cm
    extend_to: now
  - entity: sensor.fmi_waterlevel_forecast_hamina
    data_generator: |
      return entity.attributes.forecast.map((entry) => {
        return [entry["time"], entry["value"]];
      });
    stroke_width: 1
    float_precision: 3
    yaxis_id: waterlevel
    show:
      in_header: false
yaxis:
  - id: waterlevel
    min: ~-20
    max: ~100
    apex_config:
      tickAmount: 4
      labels:
        style:
          fontSize: 8px
        formatter: |
          EVAL:function(value) {
            return value.toFixed(1) + ' cm'; 
          }
```