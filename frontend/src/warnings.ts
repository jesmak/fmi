/** Reading the fmi integration's warning level sensor, and the order, times and timeline the card shows for it. */
import { LEVELS, PAST_DAYS, TIMELINE_DAYS } from "./const";
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

/** The event entity of the sensor's place, on the same device: the one that fires each warning issued, updated or cancelled. */
export function eventEntity(hass: HomeAssistant, sensor: string): string | undefined {
    const device = hass.entities?.[sensor]?.device_id;
    if (!device) {
        return undefined;
    }
    return Object.values(hass.entities ?? {}).find(
        (entry) =>
            entry?.device_id === device &&
            entry.platform === "fmi_open_data" &&
            entry.translation_key === "warning" &&
            entry.entity_id.startsWith("event."),
    )?.entity_id;
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
        ...(Math.abs(days) < 7 ? { weekday: "short" } : { day: "numeric", month: "numeric" }),
        timeZone,
    }).format(at);
    // hourCycle rather than hour12: false, which some engines turn into a clock that reads 24.00 at midnight.
    const cycle = hour12 === undefined ? {} : hour12 ? { hour12: true } : { hourCycle: "h23" as const };
    const hours = new Intl.DateTimeFormat(language, { hour: "numeric", minute: "2-digit", ...cycle, timeZone }).format(at);
    return `${day} ${hours}`;
}

/** A warning that has ended or was cancelled, as its last version in the event entity's history. */
export interface Past {
    warning: Warning;
    cancelled: boolean;
}

/** A row of `history/history_during_period`: the event entity's state, the moment of an event, and its attributes. */
export interface HistoryRow {
    s: string;
    a?: Record<string, unknown>;
}

/**
 * The warnings that have ended or were cancelled in the last `PAST_DAYS` days, newest first, from the history of the
 * place's event entity, which fires each warning issued, updated or cancelled with the whole warning as its data.
 *
 * A warning's versions are told apart from other warnings by their type, level and areas and by overlapping in time, as
 * FMI changes a warning's id with every reissue and moves its start to the moment of an update made while it is in
 * force. The history repeats an event whenever the entity's state is written again, and has rows without one from
 * restarts, which both drop out.
 */
export function pastWarnings(rows: HistoryRow[], now: number, count: number): Past[] {
    const events = rows
        .map((row) => ({ at: Date.parse(row.s), type: row.a?.event_type, warning: row.a }))
        .filter((event): event is { at: number; type: string; warning: Warning & Record<string, unknown> } => {
            return !Number.isNaN(event.at) && typeof event.type === "string" && isWarning(event.warning);
        })
        .sort((a, b) => a.at - b.at);
    const versions: { identity: string; past: Past; ended: number }[] = [];
    for (const event of events) {
        const identity = `${event.warning.type}|${event.warning.level}|${areas(event.warning).join(",")}`;
        const cancelled = event.type === "cancelled";
        const past = { warning: event.warning, cancelled };
        const ended = cancelled ? event.at : event.warning.expires === null ? NaN : Date.parse(event.warning.expires);
        const earlier = versions.find((version) => version.identity === identity && overlaps(version.past.warning, event.warning));
        if (earlier) {
            earlier.past = past;
            earlier.ended = ended;
        } else {
            versions.push({ identity, past, ended });
        }
    }
    // The history starts with the state before its window, an event of any age, so the window is applied here too.
    const since = now - PAST_DAYS * DAY_MS;
    return versions
        .filter(({ ended }) => ended <= now && ended >= since)
        .map((version) => version.past)
        .sort((a, b) => onset(b.warning) - onset(a.warning))
        .slice(0, count);
}

/** Sorted, as FMI may list a warning's areas in either order. */
function areas(warning: Warning): string[] {
    return Array.isArray(warning.areas) ? [...warning.areas].sort() : [];
}

/** Whether two warnings' times overlap or meet, a missing start or end reaching as far as it can. */
function overlaps(a: Warning, b: Warning): boolean {
    const end = (warning: Warning) => (warning.expires === null ? Infinity : Date.parse(warning.expires));
    return onset(a) <= end(b) && onset(b) <= end(a);
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
