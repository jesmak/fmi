/** Replaced at build time with the integration's version from manifest.json. */
declare const __CARD_VERSION__: string;

export const CARD_VERSION = __CARD_VERSION__;

/** How often the card redraws between the sensor's updates, so a warning moves from coming up to in force on time. */
export const TICK_MS = 60_000;

/** The timeline shows today and the two days after it. */
export const TIMELINE_DAYS = 3;

/** The levels in rising order, as the fmi integration writes them. */
export const LEVELS = ["yellow", "orange", "red"] as const;

/** A level's colour, and the text colour that reads on it. Each can be changed in a theme. */
export const LEVEL_COLORS: Record<string, { background: string; text: string }> = {
    yellow: { background: "var(--fmi-warnings-yellow-color, var(--amber-color, #ffc107))", text: "#000000" },
    orange: { background: "var(--fmi-warnings-orange-color, var(--orange-color, #ff9800))", text: "#000000" },
    red: { background: "var(--fmi-warnings-red-color, var(--red-color, #f44336))", text: "#000000" },
};

/** An icon per warning type of FMI's CAP profile. The sea's wind and thunderstorms share the land's. */
export const TYPE_ICONS: Record<string, string> = {
    wind: "mdi:weather-windy",
    seaWind: "mdi:weather-windy",
    thunderstorm: "mdi:weather-lightning",
    seaThunderstorm: "mdi:weather-lightning",
    rain: "mdi:weather-pouring",
    trafficWeather: "mdi:car-traction-control",
    pedestrianSafety: "mdi:walk",
    forestFireWeather: "mdi:pine-tree-fire",
    hotWeather: "mdi:thermometer-high",
    coldWeather: "mdi:snowflake-thermometer",
    uvNote: "mdi:sun-wireless",
    seaWaveHeight: "mdi:waves",
    seaWaterHeight: "mdi:waves-arrow-up",
    seaIcing: "mdi:snowflake-alert",
};

/** For a type FMI adds after this card was written. */
export const FALLBACK_ICON = "mdi:alert-outline";
