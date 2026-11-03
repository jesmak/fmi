import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../src/fmi-warnings-card";
import type { FmiWarningsCard } from "../src/fmi-warnings-card";
import type { HomeAssistant } from "../src/hass";
import { browserLanguage, translate } from "../src/localize/localize";
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

async function card(state: HomeAssistant, config: Record<string, unknown> = { entity: ENTITY }, layout?: string): Promise<FmiWarningsCard> {
    const element = document.createElement("fmi-warnings-card") as FmiWarningsCard;
    element.setConfig({ type: "custom:fmi-warnings-card", ...config } as never);
    element.hass = state;
    element.layout = layout;
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
        // A limit below the minimum, 120 px, is raised to it.
        expect((await card(hass("orange", [WIND]), { entity: ENTITY, max_height: 100 })).getCardSize()).toBe(2);
        expect((await card(hass("orange", [WIND]), { entity: ENTITY, height: 400 })).getCardSize()).toBe(8);
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

    it.each([
        ["its content", undefined, {}, ""],
        ["a fixed height", undefined, { height_mode: "fixed", height: 240, max_height: 300 }, "height: 240px"],
        ["a maximum height", undefined, { max_height: 300 }, "max-height: 300px"],
        ["grid rows in a sections view, over its mode", "grid", { height: 240, grid_options: { rows: 6 } }, "height: 100%"],
        [
            "its mode rounded down to the rows when the grid rows are automatic",
            "grid",
            { max_height: 300, grid_options: { rows: "auto" } },
            "max-height: 248px",
        ],
    ])("sizes itself by %s", async (_name, layout, extra, style) => {
        const element = await card(hass("orange", [WIND]), { entity: ENTITY, ...extra }, layout);
        expect(element.shadowRoot!.querySelector("ha-card")!.getAttribute("style") ?? "").toBe(style);
    });

    it.each([
        ["held to a height", undefined, { height: 240 }, ["fade-bottom"]],
        ["held up to a limit", undefined, { max_height: 300 }, ["fade-bottom"]],
        ["held by rows in a sections view", "grid", { grid_options: { rows: 4 } }, ["fade-bottom"]],
        [
            "held to a height with automatic rows in a sections view",
            "grid",
            { height: 240, grid_options: { rows: "auto" } },
            ["fade-bottom"],
        ],
        ["held by the older layout options' rows in a sections view", "grid", { layout_options: { grid_rows: 4 } }, ["fade-bottom"]],
        ["never in auto", undefined, {}, []],
        ["never in auto with automatic rows in a sections view", "grid", { grid_options: { rows: "auto" } }, []],
        ["never by grid rows outside a sections view", undefined, { grid_options: { rows: 4 } }, []],
    ])("fades the bottom edge of a body that runs past it when %s", async (_name, layout, extra, expected) => {
        const element = await card(hass("orange", [WIND, PEDESTRIANS]), { entity: ENTITY, ...extra }, layout);
        const body = element.shadowRoot!.querySelector<HTMLElement>(".body")!;
        Object.defineProperty(body, "scrollHeight", { value: 600, configurable: true });
        Object.defineProperty(body, "clientHeight", { value: 200, configurable: true });
        element.requestUpdate();
        await element.updateComplete;
        expect(["fade-top", "fade-bottom"].filter((name) => body.classList.contains(name))).toEqual(expected);
    });

    it("lets go of the body's fade when the card goes from held to auto, and fades it again when held again", async () => {
        const element = await card(hass("orange", [WIND, PEDESTRIANS]), { entity: ENTITY, height: 240 });
        // Held and in auto the body is drawn in another place, so each is a body of its own, made to run past its view.
        async function fades(): Promise<string[]> {
            const body = element.shadowRoot!.querySelector<HTMLElement>(".body")!;
            Object.defineProperty(body, "scrollHeight", { value: 600, configurable: true });
            Object.defineProperty(body, "clientHeight", { value: 200, configurable: true });
            element.requestUpdate();
            await element.updateComplete;
            return [...body.classList].filter((name) => name.startsWith("fade"));
        }
        const held = element.shadowRoot!.querySelector<HTMLElement>(".body")!;
        expect(await fades()).toEqual(["fades", "fade-bottom"]);
        element.setConfig({ type: "custom:fmi-warnings-card", entity: ENTITY } as never);
        await element.updateComplete;
        expect(await fades()).toEqual([]);
        expect([...held.classList].filter((name) => name.startsWith("fade"))).toEqual([]);
        element.setConfig({ type: "custom:fmi-warnings-card", entity: ENTITY, height: 240 } as never);
        await element.updateComplete;
        expect(await fades()).toEqual(["fades", "fade-bottom"]);
    });

    it("is held by its rows once moved into a sections view, even when another entity's change comes with it", async () => {
        const state = hass("orange", [WIND]);
        const element = await card(state, { entity: ENTITY, grid_options: { rows: 4 } });
        expect(element.shadowRoot!.querySelector("ha-card")!.getAttribute("style") ?? "").toBe("");
        element.layout = "grid";
        element.hass = { ...state, states: { ...state.states, "sensor.other": { ...state.states["sensor.other"]!, state: "2" } } };
        await element.updateComplete;
        expect(element.shadowRoot!.querySelector("ha-card")!.getAttribute("style")).toBe("height: 100%");
    });

    // 24 px of padding and border, and on the half-row step a title of 32, a timeline of one lane of 64 and a row of 32.
    it.each([
        ["the default", {}, 2],
        ["a title", { title: "Varoitukset" }, 3],
        ["no timeline", { show_timeline: false }, 1],
        ["a title and no timeline", { title: "Varoitukset", show_timeline: false }, 2],
    ])("keeps to its minimum height in a sections view with %s", async (_name, extra, rows) => {
        const options = (await card(hass("orange", [WIND]), { entity: ENTITY, ...extra })).getGridOptions();
        expect(options).toMatchObject({ columns: 12, rows: "auto", min_columns: 9, min_rows: rows });
    });

    it("raises a fixed height below its minimum to the minimum", async () => {
        const element = await card(hass("orange", [WIND]), { entity: ENTITY, height: 100 });
        expect(element.shadowRoot!.querySelector("ha-card")!.getAttribute("style")).toBe("height: 120px");
    });

    it("puts the title and the timeline's band ahead of the body when held, and only the rows in it", async () => {
        const element = await card(hass("orange", [WIND, PEDESTRIANS]), { entity: ENTITY, title: "Varoitukset", height: 200 });
        const haCard = element.shadowRoot!.querySelector("ha-card")!;
        expect([...haCard.children].map((child) => child.classList[0])).toEqual(["card-title", "band", "body"]);
        expect([...haCard.querySelector(".band")!.children].map((child) => child.className)).toEqual(["timeline"]);
        expect([...haCard.querySelector(".body")!.children].map((child) => child.className)).toEqual(["rows"]);
        expect([...haCard.querySelector(".rows")!.children].map((child) => child.classList.contains("row"))).toEqual([true, true]);
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

    it("refuses a height that isn't a positive number of pixels, and an unknown height mode", () => {
        const element = document.createElement("fmi-warnings-card") as FmiWarningsCard;
        const config = (extra: Record<string, unknown>) => ({ type: "custom:fmi-warnings-card", entity: ENTITY, ...extra }) as never;
        const error = translate(browserLanguage(), "common.invalid_height");
        for (const value of ["300px", 0, -10]) {
            expect(() => element.setConfig(config({ max_height: value }))).toThrow(error);
            expect(() => element.setConfig(config({ height: value }))).toThrow(error);
        }
        expect(() => element.setConfig(config({ height_mode: "tall" }))).toThrow(error);
        expect(() => element.setConfig(config({ height_mode: "fixed", height: 240, max_height: 300 }))).not.toThrow();
        // Left empty in YAML, each is unset.
        expect(() => element.setConfig(config({ height_mode: null, height: null, max_height: null }))).not.toThrow();
    });

    it("refuses a rounding other than whole or half rows", () => {
        const element = document.createElement("fmi-warnings-card") as FmiWarningsCard;
        const config = (row_step: unknown) => ({ type: "custom:fmi-warnings-card", entity: ENTITY, row_step }) as never;
        const error = translate(browserLanguage(), "common.invalid_row_step");
        expect(() => element.setConfig(config("quarter"))).toThrow(error);
        for (const row_step of [undefined, null, "full", "half"]) {
            expect(() => element.setConfig(config(row_step))).not.toThrow();
        }
    });

    it("carries the whole title and each warning's name as a tooltip, as either may be cut short", async () => {
        const element = await card(hass("orange", [WIND, PEDESTRIANS]), { entity: ENTITY, title: "Varoitukset", height: 300 });
        const root = element.shadowRoot!;
        expect(root.querySelector("ha-card")!.classList.contains("held")).toBe(true);
        expect(root.querySelector(".card-title")!.getAttribute("title")).toBe("Varoitukset");
        expect([...root.querySelectorAll(".name")].map((name) => name.getAttribute("title"))).toEqual([WIND.event, PEDESTRIANS.event]);
        const free = await card(hass("orange", [WIND]), { entity: ENTITY });
        expect(free.shadowRoot!.querySelector("ha-card")!.classList.contains("held")).toBe(false);
    });

    it("follows a row's slide with its height, from the tap to the slide's end", async () => {
        const element = await card(hass("orange", [WIND]), { entity: ENTITY });
        const haCard = () => element.shadowRoot!.querySelector("ha-card")!;
        element.shadowRoot!.querySelector<HTMLButtonElement>(".summary")!.click();
        await element.updateComplete;
        expect(haCard().classList.contains("sliding")).toBe(true);
        element.shadowRoot!.querySelector(".expander")!.dispatchEvent(transitionEnd());
        await element.updateComplete;
        expect(haCard().classList.contains("sliding")).toBe(false);
    });

    it.each<[string, (element: FmiWarningsCard) => Promise<void>, boolean]>([
        [
            "the end of another property's transition",
            async (element) => {
                const event = new Event("transitionend") as TransitionEvent;
                Object.defineProperty(event, "propertyName", { value: "opacity" });
                element.shadowRoot!.querySelector(".expander")!.dispatchEvent(event);
            },
            true,
        ],
        [
            "the end of a transition inside the details, bubbling up",
            async (element) => {
                const event = new Event("transitionend", { bubbles: true }) as TransitionEvent;
                Object.defineProperty(event, "propertyName", { value: "grid-template-rows" });
                element.shadowRoot!.querySelector(".details")!.dispatchEvent(event);
            },
            true,
        ],
        [
            "the end of its slide while another row still slides",
            async (element) => {
                const other = element.shadowRoot!.querySelectorAll<HTMLElement>(".expander")[1]!;
                other.getAnimations = () => [{}] as Animation[];
                element.shadowRoot!.querySelector(".expander")!.dispatchEvent(transitionEnd());
            },
            true,
        ],
        [
            "the other row's own end once its slide was waited for",
            async (element) => {
                const [first, other] = element.shadowRoot!.querySelectorAll<HTMLElement>(".expander");
                other!.getAnimations = () => [{}] as Animation[];
                first!.dispatchEvent(transitionEnd());
                other!.getAnimations = () => [];
                other!.dispatchEvent(transitionEnd());
            },
            false,
        ],
        [
            "its own end while only its own fold still reports an animation",
            async (element) => {
                const first = element.shadowRoot!.querySelector<HTMLElement>(".expander")!;
                first.getAnimations = () => [{}] as Animation[];
                first.dispatchEvent(transitionEnd());
            },
            false,
        ],
        [
            "a second with no transition to end",
            async () => {
                vi.advanceTimersByTime(1000);
            },
            false,
        ],
        [
            "a second from the first tap when a second tap restarted the slide halfway",
            async (element) => {
                vi.advanceTimersByTime(600);
                element.shadowRoot!.querySelector<HTMLButtonElement>(".summary")!.click();
                await element.updateComplete;
                vi.advanceTimersByTime(600);
            },
            true,
        ],
        [
            "a second from the second tap that restarted the slide halfway",
            async (element) => {
                vi.advanceTimersByTime(600);
                element.shadowRoot!.querySelector<HTMLButtonElement>(".summary")!.click();
                await element.updateComplete;
                vi.advanceTimersByTime(1000);
            },
            false,
        ],
        [
            "a second with no transition to end while another row still reports an animation",
            async (element) => {
                element.shadowRoot!.querySelectorAll<HTMLElement>(".expander")[1]!.getAnimations = () => [{}] as Animation[];
                vi.advanceTimersByTime(1000);
            },
            false,
        ],
        [
            "leaving the page mid-slide and coming back",
            async (element) => {
                element.remove();
                document.body.append(element);
            },
            false,
        ],
    ])("after a tap keeps or lifts its slide on %s", async (_name, then, still) => {
        // The slide's own timer too, from before the tap that starts it.
        vi.useFakeTimers({ now: NOW, toFake: ["Date", "setInterval", "clearInterval", "setTimeout", "clearTimeout"] });
        const element = await card(hass("orange", [WIND, PEDESTRIANS]), { entity: ENTITY });
        element.shadowRoot!.querySelector<HTMLButtonElement>(".summary")!.click();
        await element.updateComplete;
        await then(element);
        await element.updateComplete;
        expect(element.shadowRoot!.querySelector("ha-card")!.classList.contains("sliding")).toBe(still);
    });
});

describe("the editor's rounding", () => {
    type Form = HTMLElement & { data: Record<string, unknown>; schema: Array<{ name: string }> };

    async function editor(config: Record<string, unknown>): Promise<{ form: Form; saved: unknown[] }> {
        const element = document.createElement("fmi-warnings-card-editor");
        element.hass = hass("orange", [WIND]);
        element.setConfig({ type: "custom:fmi-warnings-card", entity: ENTITY, ...config } as never);
        document.body.append(element);
        await element.updateComplete;
        const saved: unknown[] = [];
        element.addEventListener("config-changed", (event) => saved.push((event as CustomEvent<{ config: unknown }>).detail.config));
        return { form: element.shadowRoot!.querySelector<Form>("ha-form")!, saved };
    }

    it("is offered last while the card fits its content, the height mode being set in YAML only, and only half rows are saved", async () => {
        const { form, saved } = await editor({});
        const names = form.schema.map((entry) => entry.name);
        expect(names.at(-1)).toBe("row_step");
        expect(names.filter((name) => name.includes("height"))).toEqual([]);
        expect(form.data).toMatchObject({ row_step: "full" });
        for (const row_step of ["half", "full"]) {
            form.dispatchEvent(new CustomEvent("value-changed", { detail: { value: { ...form.data, row_step } } }));
        }
        expect(saved).toEqual([
            { type: "custom:fmi-warnings-card", entity: ENTITY, row_step: "half" },
            { type: "custom:fmi-warnings-card", entity: ENTITY },
        ]);
    });

    it("is offered for a card that grows up to a limit, which keeps its limit", async () => {
        const { form, saved } = await editor({ max_height: 400 });
        expect(form.schema.map((entry) => entry.name)).toContain("row_step");
        form.dispatchEvent(new CustomEvent("value-changed", { detail: { value: { ...form.data, row_step: "half" } } }));
        expect(saved).toEqual([{ type: "custom:fmi-warnings-card", entity: ENTITY, max_height: 400, row_step: "half" }]);
    });

    it("is neither offered nor saved for a card held to a height", async () => {
        const { form, saved } = await editor({ height: 300 });
        expect(form.schema.map((entry) => entry.name)).not.toContain("row_step");
        form.dispatchEvent(new CustomEvent("value-changed", { detail: { value: { ...form.data, row_step: "half" } } }));
        expect(saved).toEqual([{ type: "custom:fmi-warnings-card", entity: ENTITY, height: 300 }]);
    });
});

/** The end of a row's slide, as the browser sends it. */
function transitionEnd(): TransitionEvent {
    const event = new Event("transitionend") as TransitionEvent;
    Object.defineProperty(event, "propertyName", { value: "grid-template-rows" });
    return event;
}

describe("redrawing for a new hass", () => {
    afterEach(() => {
        vi.restoreAllMocks();
        document.body.innerHTML = "";
    });

    // Home Assistant hands the card every change in the house. Its own sensors, the language and the locale (the time
    // format and time zone with it) are what change what the card shows.
    it.each<[string, (state: HomeAssistant) => HomeAssistant, number]>([
        [
            "another entity's change",
            (state) => ({
                ...state,
                states: {
                    ...state.states,
                    "sensor.elsewhere": { entity_id: "sensor.elsewhere", state: "2", last_changed: "", attributes: {} },
                },
            }),
            0,
        ],
        ["a new language", (state) => ({ ...state, locale: { ...state.locale!, language: "en" }, language: "en" }), 1],
        ["a new locale alone, as a new time format", (state) => ({ ...state, locale: { ...state.locale!, time_format: "12" } }), 1],
        ["a new language in the older field alone", (state) => ({ ...state, language: "sv" }), 1],
    ])("redraws as it should for %s", async (_name, change, renders) => {
        const element = await card(hass("none", [PEDESTRIANS]));
        const render = vi.spyOn(element as unknown as { render(): unknown }, "render");
        element.hass = change(element.hass!);
        await element.updateComplete;
        expect(render).toHaveBeenCalledTimes(renders);
    });
});

describe("the warnings that have ended", () => {
    const EVENT = "event.fmi_example_warning";
    const DEVICE = "device-example";

    beforeEach(() => {
        vi.useFakeTimers({ now: NOW, toFake: ["Date", "setInterval", "clearInterval"] });
    });

    afterEach(() => {
        vi.useRealTimers();
        document.body.innerHTML = "";
    });

    // The sensor and the event entity on the place's device, and the event entity's history as the recorder gives it.
    function withHistory(state: HomeAssistant, rows: unknown[]): HomeAssistant {
        return {
            ...state,
            states: {
                ...state.states,
                [EVENT]: { entity_id: EVENT, state: "2026-10-17T09:00:00.000+00:00", last_changed: "", attributes: {} },
            },
            entities: {
                [ENTITY]: { entity_id: ENTITY, device_id: DEVICE, platform: "fmi_open_data", translation_key: "warning_level" },
                [EVENT]: { entity_id: EVENT, device_id: DEVICE, platform: "fmi_open_data", translation_key: "warning" },
            },
            callWS: vi.fn(async () => ({ [EVENT]: rows })) as never,
        };
    }
    const ENDED = {
        s: "2026-10-16T21:00:00+03:00",
        a: { event_type: "issued", ...PEDESTRIANS, onset: "2026-10-17T06:00:00+03:00", expires: "2026-10-17T12:00:00+03:00" },
    };
    const CANCELLED = {
        s: "2026-10-18T10:00:00+03:00",
        a: { event_type: "cancelled", ...WIND, onset: "2026-10-21T05:00:00+03:00", expires: "2026-10-21T11:00:00+03:00" },
    };

    async function settled(element: FmiWarningsCard): Promise<void> {
        await Promise.resolve();
        await element.updateComplete;
    }

    it("lists them under the check when nothing is in force, the cancelled one with its start", async () => {
        const state = withHistory(hass("none", []), [ENDED, CANCELLED]);
        const element = await card(state);
        await settled(element);
        const root = element.shadowRoot!;
        expect(state.callWS).toHaveBeenCalledWith(expect.objectContaining({ type: "history/history_during_period", entity_ids: [EVENT] }));
        expect(text(root.querySelector(".past-label"))).toBe("Päättyneet");
        expect([...root.querySelectorAll(".past .time")].map(text)).toEqual(["peruttu, ke 5.00", "päättyi la 12.00"]);
        expect(root.querySelector(".empty")).not.toBeNull();
    });

    it("lists them after those in force too", async () => {
        const element = await card(withHistory(hass("orange", [WIND]), [ENDED]));
        await settled(element);
        const rows = [...element.shadowRoot!.querySelectorAll(".row")];
        expect(rows.map((row) => row.closest(".rows")!.classList.contains("past"))).toEqual([false, true]);
    });

    it("isn't read at all when turned off", async () => {
        const state = withHistory(hass("none", []), [ENDED]);
        const element = await card(state, { entity: ENTITY, show_past: false });
        await settled(element);
        expect(state.callWS).not.toHaveBeenCalled();
        expect(element.shadowRoot!.querySelector(".past-label")).toBeNull();
    });

    it("is read again only after a new event", async () => {
        const state = withHistory(hass("none", []), [ENDED]);
        const element = await card(state);
        await settled(element);
        element.hass = { ...state, states: { ...state.states, [ENTITY]: { ...state.states[ENTITY]!, state: "none" } } };
        await settled(element);
        expect(state.callWS).toHaveBeenCalledTimes(1);
        element.hass = {
            ...state,
            states: { ...state.states, [EVENT]: { ...state.states[EVENT]!, state: "2026-10-19T10:00:00.000+00:00" } },
        };
        await settled(element);
        expect(state.callWS).toHaveBeenCalledTimes(2);
    });

    // The event entity with a warning just cancelled as its state, which the history read may not have yet.
    function withLatest(state: HomeAssistant, at: string, data: Record<string, unknown>): HomeAssistant {
        return { ...state, states: { ...state.states, [EVENT]: { entity_id: EVENT, state: at, last_changed: "", attributes: data } } };
    }

    it("shows the latest event from the event entity itself, though the history read doesn't have it yet", async () => {
        const element = await card(withLatest(withHistory(hass("none", []), [ENDED]), CANCELLED.s, CANCELLED.a));
        await settled(element);
        expect([...element.shadowRoot!.querySelectorAll(".past .time")].map(text)).toEqual(["peruttu, ke 5.00", "päättyi la 12.00"]);
    });

    it("ignores a read that comes back after a newer one has started", async () => {
        const answers: ((value: unknown) => void)[] = [];
        const state = {
            ...withHistory(hass("none", []), []),
            callWS: vi.fn(() => new Promise((resolve) => answers.push(resolve))) as never,
        };
        const element = await card(state);
        element.hass = {
            ...state,
            states: { ...state.states, [EVENT]: { ...state.states[EVENT]!, state: "2026-10-19T10:00:00.000+00:00" } },
        };
        await element.updateComplete;
        answers[1]({ [EVENT]: [] });
        await settled(element);
        answers[0]({ [EVENT]: [ENDED] });
        await settled(element);
        expect(element.shadowRoot!.querySelector(".past-label")).toBeNull();
    });

    it("shows none when the history can't be read, says so once, and tries again at the next update", async () => {
        const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
        const state = {
            ...withHistory(hass("none", []), []),
            callWS: vi.fn(async () => Promise.reject(new Error("Unknown command"))) as never,
        };
        const element = await card(state);
        await settled(element);
        expect(element.shadowRoot!.querySelector(".past-label")).toBeNull();
        vi.advanceTimersByTime(60_000);
        await settled(element);
        expect(state.callWS).toHaveBeenCalledTimes(2);
        expect(warn).toHaveBeenCalledTimes(1);
        warn.mockRestore();
    });

    it("lets go of another place's warnings at once when the card moves to a place of its own", async () => {
        const state = withHistory(hass("none", []), [ENDED]);
        const element = await card(state);
        await settled(element);
        expect(element.shadowRoot!.querySelectorAll(".past .row").length).toBe(1);
        const OTHER = "event.fmi_other_warning";
        const moved: HomeAssistant = {
            ...state,
            callWS: vi.fn(() => new Promise(() => undefined)) as never,
            states: {
                ...state.states,
                [OTHER]: { entity_id: OTHER, state: "2026-10-18T09:00:00.000+00:00", last_changed: "", attributes: {} },
            },
            entities: {
                ...state.entities,
                [ENTITY]: { entity_id: ENTITY, device_id: "device-other", platform: "fmi_open_data", translation_key: "warning_level" },
                [OTHER]: { entity_id: OTHER, device_id: "device-other", platform: "fmi_open_data", translation_key: "warning" },
            },
        };
        element.hass = moved;
        await element.updateComplete;
        expect(element.shadowRoot!.querySelector(".past-label")).toBeNull();
    });

    it("opens one over a held card, saying when it was cancelled, with the rows under it out of reach", async () => {
        const element = await card(withHistory(hass("orange", [WIND]), [CANCELLED]), { entity: ENTITY, height: 248 });
        await settled(element);
        const root = element.shadowRoot!;
        root.querySelector<HTMLButtonElement>(".past .summary")!.click();
        await element.updateComplete;
        expect(text(root.querySelector(".overlay .time"))).toBe("peruttu, ke 5.00");
        expect(root.querySelector(".body")!.hasAttribute("inert")).toBe(true);
    });

    it("redraws for a new event, and not for another entity's change", async () => {
        const state = withHistory(hass("none", []), []);
        const element = await card(state);
        await settled(element);
        const render = vi.spyOn(element as unknown as { render(): unknown }, "render");
        element.hass = { ...state, states: { ...state.states, "sensor.other": { ...state.states["sensor.other"]!, state: "2" } } };
        await element.updateComplete;
        expect(render).toHaveBeenCalledTimes(0);
        element.hass = withLatest(state, CANCELLED.s, CANCELLED.a);
        await element.updateComplete;
        expect(render).toHaveBeenCalledTimes(1);
    });
});

describe("a held card", () => {
    beforeEach(() => {
        vi.useFakeTimers({ now: NOW, toFake: ["Date", "setInterval", "clearInterval"] });
    });

    afterEach(() => {
        vi.useRealTimers();
        document.body.innerHTML = "";
    });

    it("opens a warning over itself, and gives the focus back to its row when Escape closes it", async () => {
        const element = await card(hass("orange", [WIND, PEDESTRIANS]), { entity: ENTITY, height: 248 });
        const root = element.shadowRoot!;
        expect(root.querySelector(".expander")).toBeNull();
        root.querySelectorAll<HTMLButtonElement>(".summary")[1].click();
        await element.updateComplete;
        const overlay = root.querySelector<HTMLElement>(".overlay")!;
        expect(overlay.getAttribute("role")).toBe("dialog");
        expect(text(overlay.querySelector(".overlay-title"))).toBe("Jalankulkusäävaroitus ti 6.00 – ti 12.00");
        expect(text(overlay.querySelector(".details"))).toContain("Jalkakäytävät ovat paikoin erittäin liukkaita.");
        expect(root.activeElement).toBe(overlay.querySelector(".close"));
        overlay.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
        await element.updateComplete;
        await element.updateComplete;
        expect(root.querySelector(".overlay")).toBeNull();
        expect(root.activeElement).toBe(root.querySelectorAll(".summary")[1]);
    });

    it("closes a warning open over it when the warning goes, the rows back in reach", async () => {
        const element = await card(hass("orange", [WIND, PEDESTRIANS]), { entity: ENTITY, height: 248 });
        const root = element.shadowRoot!;
        root.querySelectorAll<HTMLButtonElement>(".summary")[1].click();
        await element.updateComplete;
        element.hass = hass("orange", [WIND]);
        await element.updateComplete;
        expect(root.querySelector(".overlay")).toBeNull();
        expect(root.querySelector(".body")!.hasAttribute("inert")).toBe(false);
    });

    it("opens a warning over itself from its bar too, and closes it from its button", async () => {
        const element = await card(hass("orange", [WIND, PEDESTRIANS]), { entity: ENTITY, height: 248 });
        const root = element.shadowRoot!;
        root.querySelectorAll<HTMLElement>(".bar")[0].click();
        await element.updateComplete;
        expect(text(root.querySelector(".overlay .name"))).toBe("Tuulivaroitus maa-alueille");
        root.querySelector<HTMLButtonElement>(".overlay .close")!.click();
        await element.updateComplete;
        expect(root.querySelector(".overlay")).toBeNull();
    });

    it.each([
        ["one lane, as in auto", [WIND], ""],
        ["two lanes, sharing one's step", [WIND, { ...PEDESTRIANS, onset: "2026-10-19T18:00:00+03:00" }], "packed"],
        [
            "three lanes, thin",
            [
                WIND,
                { ...PEDESTRIANS, onset: "2026-10-19T18:00:00+03:00" },
                { ...PEDESTRIANS, id: "3", type: "rain", onset: "2026-10-19T19:00:00+03:00" },
            ],
            "packed thin",
        ],
    ])("marks the band's lanes packed or thin by their count, with %s", async (_name, warnings, packed) => {
        const element = await card(hass("orange", warnings), { entity: ENTITY, height: 248 });
        const lanes = element.shadowRoot!.querySelector(".band .lanes")!;
        expect([...lanes.classList].filter((name) => name !== "lanes").join(" ")).toBe(packed);
    });
});
