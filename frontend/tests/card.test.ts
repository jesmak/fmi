import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../src/fmi-warnings-card";
import type { FmiWarningsCard } from "../src/fmi-warnings-card";
import type { HomeAssistant } from "../src/hass";
import type { Warning } from "../src/types";

const ENTITY = "sensor.fmi_example_warning_level";
// Monday 19 October 2026, 14.00 in Finland.
const NOW = Date.parse("2026-10-19T14:00:00+03:00");

// Made-up warnings, shaped like the ones the fmi integration writes.
const WIND: Warning = {
    id: "urn:oid:fmi.example.1",
    type: "wind",
    level: "orange",
    event: "Tuulivaroitus maa-alueille",
    onset: "2026-10-19T12:00:00+03:00",
    expires: "2026-10-20T03:00:00+03:00",
    description: "Lounaistuulen puuskat 20–25 m/s.",
    impacts: "Puita voi kaatua. Sähkökatkot ovat mahdollisia.",
    probability: 60,
};

const PEDESTRIANS: Warning = {
    id: "urn:oid:fmi.example.2",
    type: "pedestrianSafety",
    level: "yellow",
    event: "Jalankulkusäävaroitus",
    onset: "2026-10-20T06:00:00+03:00",
    expires: "2026-10-20T12:00:00+03:00",
    description: "Jalkakäytävät ovat paikoin erittäin liukkaita.",
};

function hass(state: string, warnings: unknown[] = []): HomeAssistant {
    return {
        locale: { language: "fi", time_zone: "server" },
        config: { time_zone: "Europe/Helsinki" },
        states: {
            [ENTITY]: {
                entity_id: ENTITY,
                state,
                last_changed: "2026-10-19T11:00:00+00:00",
                attributes: { warning_types: ["wind", "pedestrianSafety"], active_warnings: 1, warnings },
            },
            "sensor.other": { entity_id: "sensor.other", state: "1", last_changed: "", attributes: {} },
        },
    };
}

async function card(state: HomeAssistant, config: Record<string, unknown> = { entity: ENTITY }): Promise<FmiWarningsCard> {
    const element = document.createElement("fmi-warnings-card") as FmiWarningsCard;
    element.setConfig({ type: "custom:fmi-warnings-card", ...config } as never);
    element.hass = state;
    document.body.append(element);
    await element.updateComplete;
    return element;
}

function text(node: Element | null | undefined): string {
    return (node?.textContent ?? "").replace(/\s+/g, " ").trim();
}

describe("fmi-warnings-card", () => {
    beforeEach(() => {
        vi.useFakeTimers({ now: NOW, toFake: ["Date", "setInterval", "clearInterval"] });
    });

    afterEach(() => {
        vi.useRealTimers();
        document.body.innerHTML = "";
    });

    it("shows a row per warning, the one in force from now and the one coming up from its start", async () => {
        const root = (await card(hass("orange", [PEDESTRIANS, WIND]))).shadowRoot!;
        expect([...root.querySelectorAll(".summary")].map(text)).toEqual([
            "Oranssi varoitus Tuulivaroitus maa-alueille nyt – ti 3.00",
            "Keltainen varoitus Jalankulkusäävaroitus ti 6.00 – ti 12.00",
        ]);
        expect(root.querySelectorAll(".row.upcoming").length).toBe(1);
        expect(root.querySelectorAll(".bar").length).toBe(2);
        // The pedestrian warning starts after the wind warning ends, so the two share a lane.
        expect(root.querySelectorAll(".lane").length).toBe(1);
    });

    it("opens a warning's details on a tap and closes them on another", async () => {
        const element = await card(hass("orange", [WIND]));
        const summary = element.shadowRoot!.querySelector<HTMLButtonElement>(".summary")!;
        const expander = element.shadowRoot!.querySelector(".expander")!;
        expect(expander.hasAttribute("inert")).toBe(true);
        summary.click();
        await element.updateComplete;
        expect(expander.hasAttribute("inert")).toBe(false);
        expect(text(element.shadowRoot!.querySelector(".details"))).toBe(
            "Oranssi varoitus Lounaistuulen puuskat 20–25 m/s. Puita voi kaatua. Sähkökatkot ovat mahdollisia. Todennäköisyys 60 %",
        );
        expect(summary.getAttribute("aria-expanded")).toBe("true");
        summary.click();
        await element.updateComplete;
        expect(expander.hasAttribute("inert")).toBe(true);
    });

    it("keeps an open warning in its own row when one above it ends, without opening or scrolling again", async () => {
        const element = await card(hass("orange", [WIND, PEDESTRIANS]));
        element.shadowRoot!.querySelectorAll<HTMLButtonElement>(".summary")[1].click();
        await element.updateComplete;
        const row = element.shadowRoot!.querySelectorAll<HTMLElement>(".row")[1];
        const expander = row.querySelector(".expander")!;
        // The tapped row has slid open and been shown.
        row.scrollIntoView = vi.fn();
        expander.dispatchEvent(transitionEnd());
        expect(row.scrollIntoView).toHaveBeenCalledTimes(1);
        // The wind warning ends, and the open row moves up into the first place.
        vi.setSystemTime(Date.parse("2026-10-20T03:00:30+03:00"));
        vi.advanceTimersByTime(60_000);
        await element.updateComplete;
        const rows = element.shadowRoot!.querySelectorAll<HTMLElement>(".row");
        expect(rows.length).toBe(1);
        expect(rows[0]).toBe(row);
        expect(expander.classList.contains("open")).toBe(true);
        expander.dispatchEvent(transitionEnd());
        expect(row.scrollIntoView).toHaveBeenCalledTimes(1);
    });

    it("keeps one warning open at a time, closing the previous one when another opens", async () => {
        const element = await card(hass("orange", [WIND, PEDESTRIANS]));
        const [first, second] = element.shadowRoot!.querySelectorAll<HTMLButtonElement>(".summary");
        first.click();
        await element.updateComplete;
        second.click();
        await element.updateComplete;
        expect([first, second].map((button) => button.getAttribute("aria-expanded"))).toEqual(["false", "true"]);
    });

    it("brings an opened row into view once it has opened, and not when it closes", async () => {
        const element = await card(hass("orange", [WIND]));
        const row = element.shadowRoot!.querySelector<HTMLElement>(".row")!;
        const scroll = vi.fn();
        row.scrollIntoView = scroll;
        const end = () => element.shadowRoot!.querySelector(".expander")!.dispatchEvent(transitionEnd());
        element.shadowRoot!.querySelector<HTMLButtonElement>(".summary")!.click();
        await element.updateComplete;
        end();
        expect(scroll).toHaveBeenCalledTimes(1);
        expect(scroll.mock.calls[0][0]).toMatchObject({ block: "nearest" });
        element.shadowRoot!.querySelector<HTMLButtonElement>(".summary")!.click();
        await element.updateComplete;
        end();
        expect(scroll).toHaveBeenCalledTimes(1);
    });

    it("opens a warning's row from its bar on the timeline, or brings it into view if it is open already", async () => {
        const element = await card(hass("orange", [WIND, PEDESTRIANS]));
        const bar = element.shadowRoot!.querySelectorAll<HTMLElement>(".bar")[1];
        const row = element.shadowRoot!.querySelectorAll<HTMLElement>(".row")[1];
        row.scrollIntoView = vi.fn();
        bar.click();
        await element.updateComplete;
        expect(element.shadowRoot!.querySelectorAll(".summary")[1].getAttribute("aria-expanded")).toBe("true");
        row.querySelector(".expander")!.dispatchEvent(transitionEnd());
        expect(row.scrollIntoView).toHaveBeenCalledTimes(1);
        bar.click();
        await element.updateComplete;
        expect(element.shadowRoot!.querySelectorAll(".summary")[1].getAttribute("aria-expanded")).toBe("true");
        expect(row.scrollIntoView).toHaveBeenCalledTimes(2);
    });

    it("moves a warning to in force on the minute it starts, with no change to the sensor", async () => {
        const element = await card(hass("none", [PEDESTRIANS]));
        vi.setSystemTime(Date.parse("2026-10-20T05:59:30+03:00"));
        vi.advanceTimersByTime(60_000);
        await element.updateComplete;
        expect(element.shadowRoot!.querySelector(".row.upcoming")).toBeNull();
        expect(text(element.shadowRoot!.querySelector(".time"))).toBe("nyt – ti 12.00");
    });

    it("doesn't redraw for another entity's change", async () => {
        const state = hass("none", [PEDESTRIANS]);
        const element = await card(state);
        vi.setSystemTime(Date.parse("2026-10-20T07:00:00+03:00"));
        element.hass = { ...state, states: { ...state.states, "sensor.other": { ...state.states["sensor.other"]!, state: "2" } } };
        await element.updateComplete;
        expect(element.shadowRoot!.querySelector(".row.upcoming")).not.toBeNull();
    });

    it("redraws for the time when it is shown again, even when a new hass comes with it", async () => {
        const state = hass("none", [PEDESTRIANS]);
        const element = await card(state);
        element.remove();
        vi.setSystemTime(Date.parse("2026-10-20T07:00:00+03:00"));
        document.body.append(element);
        element.hass = { ...state, states: { ...state.states, "sensor.other": { ...state.states["sensor.other"]!, state: "2" } } };
        await element.updateComplete;
        expect(element.shadowRoot!.querySelector(".row.upcoming")).toBeNull();
    });

    it("opens only the warning tapped when another of the same type starts at the same time", async () => {
        const element = await card(hass("orange", [WIND, { ...WIND, id: "urn:oid:fmi.example.3", level: "yellow" }]));
        element.shadowRoot!.querySelector<HTMLButtonElement>(".summary")!.click();
        await element.updateComplete;
        expect(element.shadowRoot!.querySelectorAll(".expander:not([inert])").length).toBe(1);
    });

    it("counts the timeline in its size for a masonry view only when it is drawn", async () => {
        expect((await card(hass("orange", [WIND]))).getCardSize()).toBe(3);
        expect((await card(hass("orange", [WIND]), { entity: ENTITY, max_height: 600 })).getCardSize()).toBe(3);
        expect((await card(hass("orange", [WIND]), { entity: ENTITY, max_height: 100 })).getCardSize()).toBe(2);
        expect((await card(hass("orange", [WIND]), { entity: ENTITY, show_timeline: false })).getCardSize()).toBe(1);
        const far = { ...PEDESTRIANS, onset: "2026-10-23T06:00:00+03:00", expires: "2026-10-23T12:00:00+03:00" };
        expect((await card(hass("none", [far]))).getCardSize()).toBe(1);
    });

    it("opens only the warning tapped when another is alike in type, level and start, even in its areas", async () => {
        const twin = { ...WIND, id: "urn:oid:fmi.example.4", description: "Toinen merialue." };
        const element = await card(hass("orange", [WIND, twin]));
        element.shadowRoot!.querySelector<HTMLButtonElement>(".summary")!.click();
        await element.updateComplete;
        expect(element.shadowRoot!.querySelectorAll(".expander:not([inert])").length).toBe(1);
    });

    it("keeps twins for two sea areas in their own rows when the first one ends", async () => {
        const first = { ...WIND, areas: ["Merialue A"], expires: "2026-10-19T15:00:00+03:00", description: "Alue A." };
        const second = {
            ...WIND,
            id: "urn:oid:fmi.example.5",
            areas: ["Merialue B"],
            expires: "2026-10-19T20:00:00+03:00",
            description: "Alue B.",
        };
        const element = await card(hass("orange", [first, second]));
        element.shadowRoot!.querySelectorAll<HTMLButtonElement>(".summary")[1].click();
        await element.updateComplete;
        const row = element.shadowRoot!.querySelectorAll<HTMLElement>(".row")[1];
        vi.setSystemTime(Date.parse("2026-10-19T15:00:30+03:00"));
        vi.advanceTimersByTime(60_000);
        await element.updateComplete;
        const rows = element.shadowRoot!.querySelectorAll<HTMLElement>(".row");
        expect(rows.length).toBe(1);
        expect(rows[0]).toBe(row);
        expect(rows[0].querySelector(".summary")!.getAttribute("aria-expanded")).toBe("true");
        expect(text(rows[0].querySelector(".details"))).toContain("Alue B.");
    });

    it("keeps a warning open when its reissue writes the same start with another offset", async () => {
        const element = await card(hass("orange", [WIND]));
        element.shadowRoot!.querySelector<HTMLButtonElement>(".summary")!.click();
        await element.updateComplete;
        element.hass = hass("orange", [{ ...WIND, id: "urn:oid:fmi.example.8", onset: "2026-10-19T09:00:00Z" }]);
        await element.updateComplete;
        expect(element.shadowRoot!.querySelector(".summary")!.getAttribute("aria-expanded")).toBe("true");
    });

    it("draws a warning whose areas aren't a list rather than breaking", async () => {
        const root = (await card(hass("orange", [{ ...WIND, areas: "Merialue" as never }]))).shadowRoot!;
        expect(root.querySelectorAll(".row").length).toBe(1);
    });

    it("brings a row taller than its list's view into view by its top, so its name shows", async () => {
        const element = await card(hass("orange", [WIND]), { entity: ENTITY, max_height: 150 });
        const row = element.shadowRoot!.querySelector<HTMLElement>(".row")!;
        const list = element.shadowRoot!.querySelector<HTMLElement>(".rows")!;
        Object.defineProperty(row, "offsetHeight", { value: 140 });
        Object.defineProperty(list, "clientHeight", { value: 60 });
        // The row's top 80 px above the list's, with the list scrolled 300 px down: its top is at 220.
        row.getBoundingClientRect = () => ({ top: 20 }) as DOMRect;
        list.getBoundingClientRect = () => ({ top: 100 }) as DOMRect;
        list.scrollTop = 300;
        list.scrollTo = vi.fn() as never;
        list.scrollIntoView = vi.fn();
        row.scrollIntoView = vi.fn();
        element.shadowRoot!.querySelector<HTMLButtonElement>(".summary")!.click();
        await element.updateComplete;
        row.querySelector(".expander")!.dispatchEvent(transitionEnd());
        expect(list.scrollTo).toHaveBeenCalledTimes(1);
        expect(list.scrollTo).toHaveBeenCalledWith(expect.objectContaining({ top: 220 }));
        expect(list.scrollIntoView).toHaveBeenCalledTimes(1);
        expect(row.scrollIntoView).not.toHaveBeenCalled();
    });

    it("forgets an opened warning that has gone, so it doesn't come back open by itself", async () => {
        const yellow = { ...WIND, level: "yellow" as const };
        const element = await card(hass("yellow", [yellow]));
        element.shadowRoot!.querySelector<HTMLButtonElement>(".summary")!.click();
        await element.updateComplete;
        element.hass = hass("orange", [{ ...yellow, id: "urn:oid:fmi.example.6", level: "orange" }]);
        await element.updateComplete;
        element.hass = hass("yellow", [{ ...yellow, id: "urn:oid:fmi.example.7" }]);
        await element.updateComplete;
        expect(element.shadowRoot!.querySelector(".summary")!.getAttribute("aria-expanded")).toBe("false");
    });

    it("holds the card to a maximum height when one is set", async () => {
        const element = await card(hass("orange", [WIND]), { entity: ENTITY, max_height: 300 });
        expect(element.shadowRoot!.querySelector<HTMLElement>("ha-card")!.style.maxHeight).toBe("300px");
    });

    it("keeps a warning open when FMI reissues it under a new id", async () => {
        const element = await card(hass("orange", [WIND]));
        element.shadowRoot!.querySelector<HTMLButtonElement>(".summary")!.click();
        await element.updateComplete;
        element.hass = hass("orange", [{ ...WIND, id: "urn:oid:fmi.example.1.reissued" }]);
        await element.updateComplete;
        expect(element.shadowRoot!.querySelector(".expander")!.hasAttribute("inert")).toBe(false);
    });

    it("shows times in the browser's own zone when the profile asks for it", async () => {
        // The tests run in UTC, so the wind warning's end at 3.00 in Finland is 0.00 in the browser.
        const state = { ...hass("orange", [WIND]), locale: { language: "fi", time_zone: "local" } } as HomeAssistant;
        expect(text((await card(state)).shadowRoot!.querySelector(".time"))).toBe("nyt – ti 0.00");
    });

    it("follows the clock chosen in the user's profile", async () => {
        const state = { ...hass("orange", [WIND]), locale: { language: "en", time_zone: "server", time_format: "24" } } as HomeAssistant;
        expect(text((await card(state)).shadowRoot!.querySelector(".time"))).toBe("now – Tue 03:00");
    });

    it("leaves the timeline out when asked to", async () => {
        const root = (await card(hass("orange", [WIND]), { entity: ENTITY, show_timeline: false })).shadowRoot!;
        expect(root.querySelector(".timeline")).toBeNull();
        expect(root.querySelectorAll(".row").length).toBe(1);
    });

    it("says so when there are no warnings, with no timeline", async () => {
        const root = (await card(hass("none"))).shadowRoot!;
        expect(text(root.querySelector(".empty"))).toBe("Ei varoituksia");
        expect(root.querySelector(".timeline")).toBeNull();
    });

    it("tells a missing, unavailable or wrong sensor apart", async () => {
        const missing = await card(hass("none"), { entity: "sensor.fmi_nowhere" });
        expect(text(missing.shadowRoot!.querySelector(".message"))).toBe("Entiteettiä sensor.fmi_nowhere ei löydy");
        const unavailable = await card(hass("unavailable"));
        expect(text(unavailable.shadowRoot!.querySelector(".message"))).toBe("Varoitukset eivät ole juuri nyt saatavilla");
        const other = await card(hass("none"), { entity: "sensor.other" });
        expect(text(other.shadowRoot!.querySelector(".message"))).toBe("sensor.other ei ole fmi-integraation varoitusanturi");
    });

    it("needs an entity", () => {
        const element = document.createElement("fmi-warnings-card") as FmiWarningsCard;
        expect(() => element.setConfig({ type: "custom:fmi-warnings-card" } as never)).toThrow();
    });

    it("refuses a maximum height that isn't a positive number of pixels", () => {
        const element = document.createElement("fmi-warnings-card") as FmiWarningsCard;
        for (const max_height of ["300px", 0, -10]) {
            expect(() => element.setConfig({ type: "custom:fmi-warnings-card", entity: ENTITY, max_height } as never)).toThrow();
        }
        expect(() => element.setConfig({ type: "custom:fmi-warnings-card", entity: ENTITY, max_height: 300 } as never)).not.toThrow();
    });
});

/** The end of a row's slide, as the browser sends it. */
function transitionEnd(): TransitionEvent {
    const event = new Event("transitionend") as TransitionEvent;
    Object.defineProperty(event, "propertyName", { value: "grid-template-rows" });
    return event;
}
