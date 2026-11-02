import { afterEach, describe, expect, it } from "vitest";

import "../src/fmi-warnings-card";
import type { FmiWarningsCard } from "../src/fmi-warnings-card";
import type { HomeAssistant } from "../src/hass";
import type { Warning } from "../src/types";

const ENTITY = "sensor.fmi_example_warning_level";

// Made-up warnings with no start or end, so they are in force whenever the tests run.
const WIND: Warning = {
    type: "wind",
    level: "orange",
    event: "Tuulivaroitus maa-alueille",
    onset: null,
    expires: null,
    description: "Puuskat.",
};
const RAIN: Warning = { type: "rain", level: "yellow", event: "Rankkasadevaroitus", onset: null, expires: null };

function hass(warnings: Warning[]): HomeAssistant {
    return {
        locale: { language: "fi", time_zone: "server" },
        config: { time_zone: "Europe/Helsinki" },
        states: {
            [ENTITY]: {
                entity_id: ENTITY,
                state: warnings.length ? "orange" : "none",
                last_changed: "",
                attributes: { warning_types: ["wind", "rain"], active_warnings: warnings.length, warnings },
            },
        },
    } as HomeAssistant;
}

async function card(config: Record<string, unknown> = {}, layout?: string, warnings: Warning[] = [WIND, RAIN]): Promise<FmiWarningsCard> {
    const element = document.createElement("fmi-warnings-card") as FmiWarningsCard;
    element.setConfig({ type: "custom:fmi-warnings-card", entity: ENTITY, ...config } as never);
    element.hass = hass(warnings);
    element.layout = layout;
    document.body.append(element);
    await element.updateComplete;
    return element;
}

function one(element: Element, selector: string): HTMLElement {
    return element.shadowRoot!.querySelector<HTMLElement>(selector)!;
}

// happy-dom lays nothing out, so each part is given the box it would have, measured from the card's top.
function box(target: Element, top: number, bottom: number): void {
    target.getBoundingClientRect = () => ({ top, bottom, height: bottom - top, width: 300 }) as DOMRect;
}

const PARTS = ":scope > .card-title, :scope > .message, :scope > .empty, :scope > .body > .timeline, :scope > .body > .rows > .row";

/** Gives the card a width and its last part a box ending at `end`. */
function laidOut(element: FmiWarningsCard, end: number): void {
    const haCard = one(element, "ha-card");
    Object.defineProperty(haCard, "clientWidth", { value: 300, configurable: true });
    box(haCard, 0, 56);
    const parts = haCard.querySelectorAll(PARTS);
    box(parts[parts.length - 1], end - 32, end);
}

function style(element: FmiWarningsCard): string {
    return one(element, "ha-card").getAttribute("style") ?? "";
}

/** Lays the card out with its last part ending at `end`, fills its rows and returns its style. */
async function filled(element: FmiWarningsCard, end: number): Promise<string> {
    laidOut(element, end);
    (element as unknown as { fillRows(): void }).fillRows();
    await element.updateComplete;
    return style(element);
}

afterEach(() => {
    document.body.innerHTML = "";
});

describe("filling the rows of a sections view", () => {
    // The content ends 11 px of padding under its last part: at 150 px with it ending at 139.
    it.each([
        ["whole rows", {}, "min-height: 184px; --spare: 34px"],
        ["half rows", { row_step: "half" }, "min-height: 152px; --spare: 2px"],
    ])("on automatic rows, ends on %s", async (_name, config, expected) => {
        expect(await filled(await card(config, "grid"), 139)).toBe(expected);
    });

    it.each<[string, Record<string, unknown>, Warning[], string, string]>([
        ["under the title", { title: "Varoitukset" }, [WIND], ".card-title", "padding-bottom"],
        ["under the title with no warnings", { title: "Varoitukset" }, [], ".card-title", "padding-bottom"],
        ["above the timeline and the rows without a title", {}, [WIND], ".body", "padding-top"],
        ["above the line saying there are none without a title", {}, [], ".empty", "padding-top"],
    ])("puts the spare room %s, and doesn't count it again once drawn", async (_name, config, warnings, holder, side) => {
        const element = await card(config, "grid", warnings);
        expect([...element.shadowRoot!.querySelectorAll(".spare, .spare-top")]).toEqual([one(element, holder)]);
        expect(await filled(element, 139)).toBe("min-height: 184px; --spare: 34px");
        one(element, holder).style.setProperty(side, "34px");
        expect(await filled(element, 173)).toBe("min-height: 184px; --spare: 34px");
    });

    it("measures to its last part's end, never an element a theme adds after it", async () => {
        const element = await card({}, "grid");
        const added = document.createElement("div");
        box(added, 0, 900);
        one(element, "ha-card").append(added);
        expect(await filled(element, 139)).toBe("min-height: 184px; --spare: 34px");
    });

    // Each fold counts at its slide's end, whatever its drawn height: open at its details, shut at nothing. The content
    // drawn ends at 150 px, so it comes to 150 plus each fold's end less its drawn height, less the spare room above the
    // body as drawn, which moves with the slide. The first row's details are 80 px, the second's 50.
    it.each<[string, [boolean, number], [boolean, number], number, string]>([
        ["the first opening alone, 150 − 30 + 80 = 200", [true, 30], [false, 0], 0, "min-height: 248px; --spare: 48px"],
        ["the first shutting alone, 150 − 30 = 120", [false, 30], [false, 0], 0, "min-height: 120px; --spare: 0px"],
        ["the first opening as the second shuts, 150 − 30 + 80 − 30 = 170", [true, 30], [false, 30], 0, "min-height: 184px; --spare: 14px"],
        [
            "the first shutting as the second opens, 150 − 30 − 30 + 50 = 140",
            [false, 30],
            [true, 30],
            0,
            "min-height: 184px; --spare: 44px",
        ],
        ["both shutting at once, 150 − 30 − 30 = 90", [false, 30], [false, 30], 0, "min-height: 120px; --spare: 30px"],
        ["the first open at rest and the second shut, 150", [true, 80], [false, 0], 0, "min-height: 184px; --spare: 34px"],
        [
            "the first opening as the spare room is drawn at 20, 150 − 20 − 30 + 80 = 180",
            [true, 30],
            [false, 0],
            20,
            "min-height: 184px; --spare: 4px",
        ],
    ])("counts each row at the end of its slide with %s", async (_name, first, second, spare, expected) => {
        const element = await card({}, "grid");
        const expanders = [...element.shadowRoot!.querySelectorAll<HTMLElement>(".expander")];
        expect(expanders.length).toBe(2);
        [first, second].forEach(([open, drawn], index) => {
            expanders[index].classList.toggle("open", open);
            box(expanders[index], 0, drawn);
            box(expanders[index].querySelector(".details")!, 0, index === 0 ? 80 : 50);
        });
        one(element, ".body").style.paddingTop = `${spare}px`;
        expect(await filled(element, 139)).toBe(expected);
    });

    it.each([
        ["outside a sections view", {}, undefined, ""],
        ["held up to a limit", { max_height: 500 }, "grid", "max-height: 500px"],
        ["on rows set in the layout tab", { grid_options: { rows: 5 } }, "grid", "height: 100%"],
    ])("leaves its rows alone %s", async (_name, config, layout, expected) => {
        expect(await filled(await card(config, layout), 139)).toBe(expected);
    });

    it("lets go of the rows it filled once held to a height, and doesn't bring them back before it is measured again", async () => {
        const element = await card({}, "grid");
        expect(await filled(element, 139)).toBe("min-height: 184px; --spare: 34px");
        element.setConfig({ type: "custom:fmi-warnings-card", entity: ENTITY, height: 300 } as never);
        await element.updateComplete;
        expect(await filled(element, 139)).toBe("height: 300px");
        element.setConfig({ type: "custom:fmi-warnings-card", entity: ENTITY } as never);
        await element.updateComplete;
        expect(style(element)).toBe("");
    });
});
