/** Reading the fmi integration's warning level sensor, and the order, times and timeline the card shows for it. */
import { LEVELS, TIMELINE_DAYS } from "./const";
import type { HassEntity, HomeAssistant } from "./hass";
import type { Warning } from "./types";

const DAY_MS = 86_400_000;
/** A bar is drawn at least 22 px wide, about 11 % of the narrowest timeline, so lanes are packed as if it were. */
const MIN_BAR = 11;
/** Room between two bars sharing a lane, in percent. */
const BAR_GAP = 1;

/** A warning the card shows, and whether it is in force or still coming up. */
export interface Shown {
    warning: Warning;
    active: boolean;
}

export interface Timeline {
    /** Each day's weekday and where it starts, in percent of the timeline's width. */
    days: { label: string; left: number }[];
    /** Where the current moment is, in percent. */
    now: number;
    /** A bar per warning that falls inside the timeline, in the order of the rows, each in a lane of its own or shared. */
    bars: { warning: Warning; left: number; width: number; lane: number }[];
    lanes: number;
}

/** Whether an entity is the fmi integration's warning level sensor: the only one with both of these attributes. */
export function isWarningsSensor(entity: HassEntity | undefined): entity is HassEntity {
    return Array.isArray(entity?.attributes?.warnings) && Array.isArray(entity?.attributes?.warning_types);
}

/** The warning level sensors, for the card picker and the editor. */
export function warningsSensors(hass: HomeAssistant): string[] {
    return Object.keys(hass.states)
        .filter((id) => isWarningsSensor(hass.states[id]))
        .sort();
}

/**
 * The warnings to show, by when they start, the most severe first of those starting at once. Those in force come first,
 * having started already.
 *
 * The sensor drops a warning that has expired only when it next refreshes, so the card drops it on time itself.
 */
export function visibleWarnings(value: unknown, now: number): Shown[] {
    const warnings = Array.isArray(value) ? value.filter(isWarning) : [];
    return warnings
        .filter((warning) => warning.expires === null || Date.parse(warning.expires) > now)
        .map((warning) => ({ warning, active: warning.onset === null || Date.parse(warning.onset) <= now }))
        .sort((a, b) => onset(a.warning) - onset(b.warning) || LEVELS.indexOf(b.warning.level) - LEVELS.indexOf(a.warning.level));
}

function onset(warning: Warning): number {
    return warning.onset === null ? -Infinity : Date.parse(warning.onset);
}

/** The attribute is read as it comes, so a warning missing what the card needs is skipped rather than drawn broken. */
function isWarning(value: unknown): value is Warning {
    const warning = value as Warning;
    const time = (text: unknown) => text === null || (typeof text === "string" && !Number.isNaN(Date.parse(text)));
    return (
        typeof warning === "object" &&
        warning !== null &&
        typeof warning.event === "string" &&
        (LEVELS as readonly string[]).includes(warning.level) &&
        time(warning.onset) &&
        time(warning.expires)
    );
}

/**
 * A moment as the card shows it: its weekday and time, "ti 3.00", or its date when it is a week or more away.
 *
 * `hour12` is Home Assistant's choice of a 12- or 24-hour clock. Left out, the language decides.
 */
export function moment(time: string, now: number, language: string, timeZone?: string, hour12?: boolean): string {
    const at = Date.parse(time);
    const [then, today] = [clock(at, timeZone), clock(now, timeZone)];
    const days = (Date.UTC(then.year, then.month - 1, then.day) - Date.UTC(today.year, today.month - 1, today.day)) / DAY_MS;
    const day = new Intl.DateTimeFormat(language, {
        ...(days < 7 ? { weekday: "short" } : { day: "numeric", month: "numeric" }),
        timeZone,
    }).format(at);
    // hourCycle rather than hour12: false, which some engines turn into a clock that reads 24.00 at midnight.
    const cycle = hour12 === undefined ? {} : hour12 ? { hour12: true } : { hourCycle: "h23" as const };
    const hours = new Intl.DateTimeFormat(language, { hour: "numeric", minute: "2-digit", ...cycle, timeZone }).format(at);
    return `${day} ${hours}`;
}

/** Today and the days after it, with a bar for each warning, cut to the timeline's ends. */
export function timeline(shown: Shown[], now: number, language: string, timeZone?: string): Timeline {
    // Midnights rather than 24-hour steps, as a day is 23 or 25 hours long when daylight saving time starts or ends.
    const starts = Array.from({ length: TIMELINE_DAYS + 1 }, (_, day) => startOfDay(now, day, timeZone));
    const first = starts[0];
    const last = starts[TIMELINE_DAYS];
    const at = (time: number) => ((time - first) / (last - first)) * 100;
    // Named by the calendar date, not the moment the day starts, which is still the day before where clocks jump at midnight.
    const today = clock(now, timeZone);
    const weekday = new Intl.DateTimeFormat(language, { weekday: "short", timeZone: "UTC" });
    return {
        days: starts.slice(0, -1).map((start, day) => ({
            label: weekday.format(Date.UTC(today.year, today.month - 1, today.day + day)),
            left: at(start),
        })),
        now: at(now),
        ...pack(
            shown.flatMap(({ warning }) => {
                const start = Math.max(warning.onset === null ? first : Date.parse(warning.onset), first);
                const end = Math.min(warning.expires === null ? last : Date.parse(warning.expires), last);
                return end > start ? [{ warning, left: at(start), width: at(end) - at(start) }] : [];
            }),
        ),
    };
}

/** Puts each bar in the first lane where it clears the bar before it, so warnings that follow each other share a lane. */
function pack(bars: { warning: Warning; left: number; width: number }[]): Pick<Timeline, "bars" | "lanes"> {
    const ends: number[] = [];
    const packed = bars.map((bar) => {
        // Drawn no narrower than MIN_BAR, and a bar near the end is pulled left to fit.
        const left = Math.min(bar.left, 100 - MIN_BAR);
        const right = left + Math.max(bar.width, MIN_BAR);
        let lane = ends.findIndex((end) => left >= end + BAR_GAP);
        if (lane === -1) {
            lane = ends.length;
        }
        ends[lane] = right;
        return { ...bar, lane };
    });
    return { bars: packed, lanes: ends.length };
}

/** The moment a day starts in a time zone (the browser's when none is given), `days` after the day `time` falls on. */
export function startOfDay(time: number, days: number, timeZone?: string): number {
    const { year, month, day } = clock(time, timeZone);
    const midnight = Date.UTC(year, month - 1, day + days);
    // The offset at midnight's UTC reading can differ from the one at midnight itself on the day the clocks change.
    const guess = midnight - offset(midnight, timeZone);
    return midnight - offset(guess, timeZone);
}

/** How far a time zone's clock is ahead of UTC at a moment, in milliseconds. */
function offset(time: number, timeZone?: string): number {
    const { year, month, day, hour, minute, second } = clock(time, timeZone);
    return Date.UTC(year, month - 1, day, hour, minute, second) - Math.floor(time / 1000) * 1000;
}

/** What a time zone's clock and calendar read at a moment, by their parts rather than a formatted string's layout. */
function clock(time: number, timeZone?: string): Record<"year" | "month" | "day" | "hour" | "minute" | "second", number> {
    const parts = new Intl.DateTimeFormat("en-US", {
        timeZone,
        hourCycle: "h23",
        year: "numeric",
        month: "numeric",
        day: "numeric",
        hour: "numeric",
        minute: "numeric",
        second: "numeric",
    }).formatToParts(time);
    const part = (type: Intl.DateTimeFormatPartTypes) => Number(parts.find((item) => item.type === type)?.value);
    return {
        year: part("year"),
        month: part("month"),
        day: part("day"),
        hour: part("hour"),
        minute: part("minute"),
        second: part("second"),
    };
}
