import type { LovelaceCardConfig } from "./hass";

/** One warning in the `warnings` attribute of the fmi integration's warning level sensor. */
export interface Warning {
    /** Not used by the card: FMI changes it on every reissue. */
    id?: string;
    type: string;
    level: "yellow" | "orange" | "red";
    event: string;
    severity?: string;
    /** ISO 8601. Null when FMI gives none: in force from the start. */
    onset: string | null;
    /** ISO 8601. Null when FMI gives none: in force until further notice. */
    expires: string | null;
    headline?: string;
    description?: string;
    impacts?: string;
    probability?: number | null;
    areas?: string[];
    parameters?: Record<string, unknown>;
}

export interface FmiWarningsCardConfig extends LovelaceCardConfig {
    entity: string;
    title?: string;
    show_timeline?: boolean;
    /** In pixels. A longer list of warnings scrolls. */
    max_height?: number;
}
