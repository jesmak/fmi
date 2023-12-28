# FMI data for Home Assistant

## What is it?

A custom component that integrates with Finnish Meteorological Institute to retrieve data not typically part of
other weather integrations, such as seawater level, UV-index, snow thickness etc.

## Installation

### Manual

1. Download source code from latest release tag
2. Copy custom_components/fmi folder to your Home Assistant installation's config/custom_components folder.
3. Restart Home Assistant
4. Configure the integration by adding a new integration in settings/integrations page of Home Assistant

### Integration settings

| Name        | Type   | Requirement  | Description                                                           | Default    |
|-------------|--------| ------------ |-----------------------------------------------------------------------|------------|
| label       | string | **Required** | Label used for this configuration                                     | Empty      |
| sensor_type | enum   | **Required** | Sensor type selection                                                 | Waterlevel |
| fmisid      | int    | **Required** | ID of the target location. Check possible values from FMISID section. | 0          |
| step        | int    | **Required** | Time step between two values in minutes                               | 20         |
| overlap     | int    | **Required** | Overlap of forecast and observations in minutes                       | 120        |

### Forecast settings

If you've selected a forecast type sensor, these are the additional options configurable in the next step.

| Name                | Type | Requirement  | Description                              | Default |
|---------------------|------| ------------ |------------------------------------------|---------|
| step                | int  | **Required** | Step between forecast entries in minutes | 30      |
| forecast_hours      | int  | **Required** | Amount of future hours to show           | 48      |
| forecast_past_hours | int  | **Required** | Amount of past hours to show             | 5       |

### State attributes

For observation sensors, this integration returns current observation value as the sensor state. It also returns the following state attributes.

| Name          | Type          | Description                                                                      |
|---------------|---------------|----------------------------------------------------------------------------------|
| sensor_type   | string        | Type of the sensor                                                               |
| latest_update | date          | Date of the latest observation                                                   |
| fmisid        | int           | FMISID of the target location                                                    |

For forecast sensors, this integration returns the next forecast entry as the sensor state. It also returns the following state attributes.  

| Name          | Type          | Description                                                      |
|---------------|---------------|------------------------------------------------------------------|
| sensor_type   | string        | Type of the sensor                                               |
| latest_update | date          | Date of the latest observation                                   |
| fmisid        | int           | FMISID of the target location                                    |
| forecast      | [date, float] | An array of forecasted sensor values for the selected location   |    

### Usage with apexcharts-card

One use case for this integration could be to show waterlevel values with [apexcharts-card](https://github.com/RomRider/apexcharts-card).

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
    name: Observerd
    color: orange
    unit: cm
  - entity: sensor.fmi_waterlevel_forecast_hamina
    data_generator: |
      return entity.attributes.forecast.map((entry) => {
        return [entry[0], entry[1]];
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

### FMISID

Not every location supports every type of observation or forecast. Below is a list of known supported locations and
their IDs by type. FMISID information is spread all around FMI documentation, and it's hard to find info on which
location supports which kind of data. Some information is available for example [here](https://en.ilmatieteenlaitos.fi/open-data-manual-fmi-wfs-services),
but the documentation is not very comprehensive and it doesn't seem to be very up to date. 

Waterlevel observations and forecasts

| Location                    | FMISID |
|-----------------------------|--------|
| Föglö, Degerby              | 134252 |
| Hamina, Pitäjänsaari        | 134254 |
| Hanko, Pikku Kolalahti      | 134253 |
| Helsinki, Kaivopuisto       | 132310 |    
| Kaskinen, Ådskär            | 134251 |
| Kemi, Ajos                  | 100539 |
| Oulu, Toppila               | 134248 |
| Pietarsaari, Leppäluoto     | 134250 |
| Pori, Mäntyluoto Kallo      | 134266 |
| Porvoo, Emäsalo Vaarlahti   | 100669 |
| Raahe, Lapaluoto            | 100540 |
| Rauma, Petäjäs              | 134224 |
| Turku, Ruissalo Saaronniemi | 134225 |
| Vaasa, Vaskiluoto           | 134223 |

UVI observations

| Location                            | FMISID |
|-------------------------------------|--------|
| Helsinki, Kumpula                   | 101004 |
| Jokioinen, Ilmala                   | 101104 |
| Jyväskylä, lentoasema               | 101339 |
| Parainen, Utö                       | 100908 |
| Sodankylä, Tähtelä                  | 101932 |
| Sotkamo, Kuolaniemi                 | 101756 |
| Utsjoki, Kevo                       | 102035 |
| Vantaa, Helsinki-Vantaan lentoasema | 100968 |

Air quality observations

| Location                     | FMISID |
|------------------------------|--------|
| Helsinki, Kumpula            | 101004 |
| Ilomantsi, Pötsönvaara       | 101649 |
| Inari, Raja-Jooseppi         | 102009 |
| Juupajoki, Hyytiälä          | 101317 |
| Kittilä, Matorova            | 101985 |
| Kuopio, Puijo                | 101587 |                
| Kuusamo, Juuma               | 101899 |
| Muonio, Sammaltunturi        | 101983 |
| Parainen, Utö                | 100908 |   
| Sodankylä, Heikinheimo-masto | 101942 |
| Utsjoki, Kevo                | 102035 |
| Virolahti, Koivuniemi Ääpälä | 100656 |

Air quality observations (urban)

| Location                              | FMISID |
|---------------------------------------|--------|
| Espoo, Leppävaara Läkkisepänkuja      | 100691 |
| Espoo, Luukki                         | 100723 |
| Harjavalta, Kaleva                    | 103142 |
| Harjavalta, Pirkkala                  | 103143 |
| Heinola, Tiilitehtaankatu             | 105416 |
| Helsinki, Kallio 2                    | 100662 |
| Helsinki, Mannerheimintie             | 100742 |
| Helsinki, Mäkelänkatu                 | 100762 |
| Helsinki, Tapanila                    | 104074 |
| Helsinki, Vartiokylä Huivipolku       | 100803 |
| Hollola, Kuntotie                     | 107623 |
| Hämeenlinna, Niittykatu               | 103109 |
| Imatra, Mansikkala                    | 103118 |
| Imatra, Pelkolan tulliasema Raja      | 103119 |
| Imatra, Rautionkylä                   | 103121 |
| Imatra, Teppanala                     | 103122 |
| Joensuu, Koskikatu 1                  | 103148 |
| Jyväskylä, Hannikaisenkatu            | 106796 |
| Jyväskylä, Jyskä                      | 107401 |
| Jämsä, Seppolantie                    | 103129 |
| Kaarina, Kaarina                      | 100823 |
| Kauniainen, Kauniaistentie            | 105405 |
| Kemi, Biotuotetehdas                  | 107284 |
| Kokkola, keskusta Pitkänsillankatu    | 103107 |
| Kokkola, Ykspihlaja                   | 103108 |
| Kotka, Kirjastotalo                   | 103105 |
| Kotka, Tiutinen                       | 107622 |
| Kouvola, Kankaan Koulu                | 104078 |
| Kouvola, Kuusankoski Urheilukentäntie | 103112 |
| Kuopio, Haminalahti                   | 100882 |
| Kuopio, Maaherrankatu                 | 103093 |
| Kuopio, Niirala                       | 104098 |
| Kuopio, Savilahti KYS                 | 106954 |
| Kuopio, Sorsasalo                     | 103094 |
| Kuopio, Tasavallankatu                | 103095 |
| Lahti, Laune Pohjoinen Liipolankatu   | 103131 |
| Lahti, Saimaankatu                    | 103132 |
| Lahti, Satulakatu                     | 103133 |
| Lappeenranta, Ihalainen 2             | 107563 |
| Lappeenranta, Joutsenon keskusta      | 103115 |
| Lappeenranta, keskusta 4              | 103116 |
| Lappeenranta, Lauritsala              | 103117 |
| Lappeenranta, Ojala-Tuomela           | 107379 |
| Lappeenranta, Pulp                    | 103120 |
| Lappeenranta, Tirilä Pekkasenkatu     | 103123 |
| Lohja, Harjula                        | 107147 |
| Luoto, Vikarholmen                    | 103153 |
| Naantali, keskusta Asematori          | 100824 |
| Oulu, keskusta 2                      | 103125 |
| Oulu, Nokela                          | 103124 |
| Oulu, Pyykösjärvi                     | 103126 |
| Parainen                              | 104064 |
| Pietarsaari, Bottenviksvägen          | 103152 |
| Pori, Paanakedonkatu                  | 106420 |
| Pori, Pastuskeri                      | 103135 |
| Porvoo, Mustijoki                     | 103139 |
| Porvoo, Nyby                          | 103140 |
| Porvoo, Svartbäck                     | 103141 |
| Raahe, keskusta                       | 103147 |
| Raahe, Lapaluoto                      | 103145 |
| Raisio, Ihala                         | 106630 |
| Rauma, Sinisaari                      | 778578 |
| Rauma, Tarvonsaari Hallikatu          | 103113 |
| Rovaniemi, Rovakatu                   | 103816 |
| Savonlinna, Olavinkatu                | 104045 |
| Seinäjoki, Vapaudentie 6a             | 103110 |
| Siilinjärvi, Sorakuja                 | 104017 |
| Sotkamo, Terrafame Taattola           | 107992 |
| Tampere, Epila 2                      | 103096 |
| Tampere, Kaleva                       | 103097 |
| Tampere, Linja-autoasema              | 103098 |
| Tampere, Pirkankatu                   | 103099 |
| Turku, Kauppatori 2                   | 107569 |
| Turku, Ruissalo Saarontie             | 100845 |
| Vaasa, keskusta Vaasanpuistikko       | 103104 |
| Vaasa, Vesitorni                      | 103103 |
| Vantaa, Hämeenlinnanväylä             | 104083 |
| Vantaa, Tikkurila Neilikkatie         | 100763 |
| Varkaus, Kommila                      | 107382 |
| Varkaus, Psaari 2                     | 103100 |
| Varkaus, Taulumäki (toripaviljonki)   | 103102 |
| Äänekoski, Paloasema                  | 107168 |