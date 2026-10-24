import { describe, expect, it } from "vitest";

import type { Warning } from "../src/types";
import { moment, startOfDay, timeline, visibleWarnings } from "../src/warnings";

const ZONE = "Europe/Helsinki";
// Monday 19 October 2026, 14.00 in Finland.
const NOW = Date.parse("2026-10-19T14:00:00+03:00");

// Made-up warnings, shaped like the ones the fmi integration writes.
function warning(id: string, extra: Partial<Warning> = {}): Warning {
    return {
        id,
        type: "wind",
        level: "yellow",
        event: "Tuulivaroitus maa-alueille",
        onset: "2026-10-19T12:00:00+03:00",
        expires: "2026-10-20T03:00:00+03:00",
        description: "Lounaistuulen puuskat 20 m/s.",
        ...extra,
    };
}

describe("visibleWarnings", () => {
    it("orders the warnings by their start, those in force having started first", () => {
        const shown = visibleWarnings(
            [
                // The later one is the more severe, so only an order by start puts the sooner one first.
                warning("later", { onset: "2026-10-21T06:00:00+03:00", expires: "2026-10-21T12:00:00+03:00", level: "red" }),
                warning("soon", { onset: "2026-10-20T06:00:00+03:00", expires: "2026-10-20T12:00:00+03:00" }),
                warning("yellow-now", { onset: "2026-10-19T09:00:00+03:00", type: "trafficWeather" }),
                warning("orange-now", { level: "orange" }),
                warning("no-onset", { onset: null }),
            ],
            NOW,
        );
        expect(shown.map(({ warning, active }) => [warning.id, active])).toEqual([
            ["no-onset", true],
            ["yellow-now", true],
            ["orange-now", true],
            ["soon", false],
            ["later", false],
        ]);
    });

    it("puts the more severe first of two starting at once, whichever way round they come", () => {
        const yellow = warning("yellow");
        const orange = warning("orange", { level: "orange" });
        expect(visibleWarnings([yellow, orange], NOW).map(({ warning }) => warning.id)).toEqual(["orange", "yellow"]);
        expect(visibleWarnings([orange, yellow], NOW).map(({ warning }) => warning.id)).toEqual(["orange", "yellow"]);
    });

    it("puts a warning in force before a more severe one coming up, whichever way round they come", () => {
        const now = warning("now");
        const coming = warning("coming", { onset: "2026-10-20T06:00:00+03:00", expires: "2026-10-20T12:00:00+03:00", level: "red" });
        expect(visibleWarnings([now, coming], NOW).map(({ warning }) => warning.id)).toEqual(["now", "coming"]);
        expect(visibleWarnings([coming, now], NOW).map(({ warning }) => warning.id)).toEqual(["now", "coming"]);
    });

    it("drops a warning once it has expired, before the sensor next refreshes", () => {
        const shown = visibleWarnings([warning("over", { expires: "2026-10-19T13:59:00+03:00" }), warning("on", { expires: null })], NOW);
        expect(shown.map(({ warning }) => warning.id)).toEqual(["on"]);
    });

    it("skips what isn't a warning rather than drawing it broken", () => {
        const shown = visibleWarnings(
            [null, "text", warning("no-level", { level: "purple" as never }), warning("bad-time", { onset: "tomorrow" }), warning("ok")],
            NOW,
        );
        expect(shown.map(({ warning }) => warning.id)).toEqual(["ok"]);
        expect(visibleWarnings(undefined, NOW)).toEqual([]);
    });
});

describe("moment", () => {
    it("gives the weekday and the time", () => {
        expect(moment("2026-10-20T03:00:00+03:00", NOW, "fi", ZONE)).toBe("ti 3.00");
        expect(moment("2026-10-19T21:00:00+03:00", NOW, "fi", ZONE)).toBe("ma 21.00");
    });

    it("leaves the clock to the language unless a 12- or 24-hour one is chosen", () => {
        // ICU puts a narrow no-break space before AM, which \s matches.
        expect(moment("2026-10-20T03:00:00+03:00", NOW, "en", ZONE)).toMatch(/^Tue 3:00\sAM$/);
        expect(moment("2026-10-20T03:00:00+03:00", NOW, "en-GB", ZONE)).toMatch(/^Tue 0?3:00$/);
        expect(moment("2026-10-20T03:00:00+03:00", NOW, "en", ZONE, false)).toBe("Tue 03:00");
        expect(moment("2026-10-20T15:00:00+03:00", NOW, "en-GB", ZONE, true)).toMatch(/^Tue 3:00\spm$/i);
    });

    it("gives the date for a week or more away, where a weekday would be ambiguous", () => {
        expect(moment("2026-10-26T12:00:00+02:00", NOW, "fi", ZONE)).toBe("26.10. 12.00");
        // Six days away, across the end of daylight saving time, is still a weekday.
        expect(moment("2026-10-25T12:00:00+02:00", NOW, "fi", ZONE)).toBe("su 12.00");
    });

    it("follows the time zone it is given", () => {
        expect(moment("2026-10-20T03:00:00+03:00", NOW, "fi", "UTC")).toBe("ti 0.00");
    });

    it("counts the days by the zone's own calendar, not the machine's", () => {
        // Late on Monday in Finland. A week later at 1.00 is still Sunday in UTC, six days on by the machine's calendar.
        expect(moment("2026-10-26T01:00:00+02:00", Date.parse("2026-10-19T23:30:00+03:00"), "fi", ZONE)).toBe("26.10. 1.00");
    });
});

describe("startOfDay", () => {
    it("finds midnight across the end of daylight saving time, so that day is 25 hours long", () => {
        const saturday = Date.parse("2026-10-24T12:00:00+03:00");
        expect([0, 1, 2, 3].map((days) => new Date(startOfDay(saturday, days, ZONE)).toISOString())).toEqual([
            "2026-10-23T21:00:00.000Z",
            "2026-10-24T21:00:00.000Z",
            "2026-10-25T22:00:00.000Z",
            "2026-10-26T22:00:00.000Z",
        ]);
    });

    it("finds midnight across the start of daylight saving time, so that day is 23 hours long", () => {
        const saturday = Date.parse("2027-03-27T12:00:00+02:00");
        expect([1, 2].map((days) => new Date(startOfDay(saturday, days, ZONE)).toISOString())).toEqual([
            "2027-03-27T22:00:00.000Z",
            "2027-03-28T21:00:00.000Z",
        ]);
    });

    it("finds midnight where the clocks change after midnight read as UTC, so a second look at the offset is needed", () => {
        // New Zealand leaves daylight saving time at 3.00 on 4 April 2027, 14.00 UTC the day before.
        const saturday = Date.parse("2027-04-03T12:00:00+13:00");
        expect(new Date(startOfDay(saturday, 1, "Pacific/Auckland")).toISOString()).toBe("2027-04-03T11:00:00.000Z");
    });
});

describe("timeline", () => {
    it("spans today and the two days after it, with a bar per warning cut to its ends", () => {
        const shown = visibleWarnings(
            [
                warning("wind"),
                warning("since-yesterday", { onset: "2026-10-18T20:00:00+03:00", expires: "2026-10-19T18:00:00+03:00" }),
                warning("open-ended", { onset: "2026-10-21T12:00:00+03:00", expires: null }),
                warning("beyond", { onset: "2026-10-22T06:00:00+03:00", expires: "2026-10-22T12:00:00+03:00" }),
            ],
            NOW,
        );
        const { days, now, bars } = timeline(shown, NOW, "fi", ZONE);
        expect(days.map(({ label }) => label)).toEqual(["ma", "ti", "ke"]);
        expect(days.map(({ left }) => left.toFixed(2))).toEqual(["0.00", "33.33", "66.67"]);
        expect(now).toBeCloseTo((14 / 72) * 100);
        expect(bars.map(({ warning, left, width }) => [warning.id, left.toFixed(2), width.toFixed(2)])).toEqual([
            ["since-yesterday", "0.00", ((18 / 72) * 100).toFixed(2)],
            ["wind", ((12 / 72) * 100).toFixed(2), ((15 / 72) * 100).toFixed(2)],
            ["open-ended", ((60 / 72) * 100).toFixed(2), ((12 / 72) * 100).toFixed(2)],
        ]);
    });

    it("puts warnings that follow each other in a shared lane, and those that overlap in lanes of their own", () => {
        const shown = visibleWarnings(
            [
                warning("since-yesterday", { onset: "2026-10-18T20:00:00+03:00", expires: "2026-10-19T18:00:00+03:00" }),
                warning("wind"),
                warning("open-ended", { onset: "2026-10-21T12:00:00+03:00", expires: null }),
            ],
            NOW,
        );
        const { bars, lanes } = timeline(shown, NOW, "fi", ZONE);
        expect(bars.map(({ warning, lane }) => [warning.id, lane])).toEqual([
            ["since-yesterday", 0],
            ["wind", 1],
            ["open-ended", 0],
        ]);
        expect(lanes).toBe(2);
    });

    it("packs a short bar as if it were as wide as it is drawn", () => {
        // Two hours each, four hours apart: apart in time, but a short bar is drawn wider than its time on a narrow card.
        const shown = visibleWarnings(
            [
                warning("first", { onset: "2026-10-20T00:00:00+03:00", expires: "2026-10-20T02:00:00+03:00" }),
                warning("second", { onset: "2026-10-20T06:00:00+03:00", expires: "2026-10-20T08:00:00+03:00" }),
                warning("next-day", { onset: "2026-10-21T06:00:00+03:00", expires: "2026-10-21T08:00:00+03:00" }),
            ],
            NOW,
        );
        expect(timeline(shown, NOW, "fi", ZONE).bars.map(({ lane }) => lane)).toEqual([0, 1, 0]);
    });

    it("keeps warnings back to back in lanes of their own, so they don't read as one bar", () => {
        const shown = visibleWarnings(
            [
                warning("yellow", { onset: "2026-10-20T06:00:00+03:00", expires: "2026-10-20T20:00:00+03:00" }),
                warning("orange", { onset: "2026-10-20T20:00:00+03:00", expires: "2026-10-21T06:00:00+03:00", level: "orange" }),
            ],
            NOW,
        );
        expect(timeline(shown, NOW, "fi", ZONE).bars.map(({ lane }) => lane)).toEqual([0, 1]);
    });

    it("packs a short bar at the very end where it is drawn, pulled left to fit", () => {
        // The last one is drawn from 89 % rather than its 97 %, which the first one reaches within the gap.
        const shown = visibleWarnings(
            [
                warning("long", { onset: "2026-10-21T06:00:00+03:00", expires: "2026-10-21T15:30:00+03:00" }),
                warning("last", { onset: "2026-10-21T22:00:00+03:00", expires: "2026-10-21T23:00:00+03:00" }),
            ],
            NOW,
        );
        expect(timeline(shown, NOW, "fi", ZONE).bars.map(({ lane }) => lane)).toEqual([0, 1]);
    });

    it("lays the days out from real midnights when one of them is 25 hours long", () => {
        const { days } = timeline([], Date.parse("2026-10-24T12:00:00+03:00"), "fi", ZONE);
        expect(days.map(({ label }) => label)).toEqual(["la", "su", "ma"]);
        expect(days.map(({ left }) => left.toFixed(2))).toEqual(["0.00", ((24 / 73) * 100).toFixed(2), ((49 / 73) * 100).toFixed(2)]);
    });

    it("names the days by the zone's own calendar, not the machine's", () => {
        // 1.00 on Monday in Finland is still Sunday in UTC.
        expect(timeline([], Date.parse("2026-10-19T01:00:00+03:00"), "fi", ZONE).days.map(({ label }) => label)).toEqual([
            "ma",
            "ti",
            "ke",
        ]);
    });

    it("names the days by the calendar where the clocks jump forward at midnight", () => {
        // Chile starts daylight saving time at midnight on Sunday 6 September 2026, so that day has no midnight.
        const { days } = timeline([], Date.parse("2026-09-05T12:00:00-04:00"), "en", "America/Santiago");
        expect(days.map(({ label }) => label)).toEqual(["Sat", "Sun", "Mon"]);
    });
});
