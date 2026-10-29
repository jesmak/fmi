/**
 * A dashboard card for the weather warnings of one place, from the fmi integration's warning level sensor.
 *
 * A row per warning, those in force first, with its description, impacts and probability a tap away. Above the rows, a
 * timeline of today and the two days after it shows when each warning starts and ends.
 */
import { LitElement, css, html, nothing } from "lit";
import type { CSSResultGroup, PropertyValues, TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import { repeat } from "lit/directives/repeat.js";

import { CARD_VERSION, FALLBACK_ICON, LEVEL_COLORS, TICK_MS, TYPE_ICONS } from "./const";
import "./editor";
import { ScrollFade, fadeStyles } from "./fade";
import type { HomeAssistant } from "./hass";
import { gridMinRows, heightCardSize, heightStyle, validHeight } from "./height";
import { browserLanguage, translate } from "./localize/localize";
import type { FmiWarningsCardConfig, Warning } from "./types";
import { isWarningsSensor, moment, timeline, visibleWarnings, warningsSensors } from "./warnings";
import type { Shown } from "./warnings";

export class FmiWarningsCard extends LitElement {
    @property({ attribute: false }) public hass?: HomeAssistant;
    @property({ attribute: false }) public layout?: string;
    @state() private config?: FmiWarningsCardConfig;
    /** The one warning opened to show its details, by its key from `rowKeys`. Opening another closes it. */
    @state() private opened?: string;
    /** The row just opened by a tap, to be brought into view once it has opened, and only then. */
    private revealing?: string;
    /** The warnings to draw and their rows' keys, worked out once per update. */
    private list: { now: number; shown: Shown[]; keys: Map<Warning, string> } = { now: 0, shown: [], keys: new Map() };
    /** Counts the minutes, so the card redraws for the time even when its sensor hasn't changed. */
    @state() private tick = 0;
    private ticker?: ReturnType<typeof setInterval>;

    constructor() {
        super();
        // Fades the body's edges while the card is held to a height, through the card's own lifecycle.
        new ScrollFade(this, () => (this.heightStyle() ? this.renderRoot.querySelectorAll<HTMLElement>(".body") : []));
    }

    public static getConfigElement(): HTMLElement {
        return document.createElement("fmi-warnings-card-editor");
    }

    /** Offers the first warnings sensor there is when the card is added from the picker. */
    public static getStubConfig(hass?: HomeAssistant): Record<string, unknown> {
        return { entity: hass ? (warningsSensors(hass)[0] ?? "") : "" };
    }

    public setConfig(config: FmiWarningsCardConfig): void {
        if (!config || typeof config.entity !== "string" || config.entity === "") {
            throw new Error(translate(browserLanguage(), "common.invalid_configuration"));
        }
        if (!validHeight(config)) {
            throw new Error(translate(browserLanguage(), "common.invalid_height"));
        }
        this.config = config;
    }

    /** In units of 50 px, for a masonry view: the title, the timeline and a row per warning, or the height it is held to. */
    public getCardSize(): number {
        const now = Date.now();
        const shown = visibleWarnings(this.hass?.states[this.config?.entity ?? ""]?.attributes.warnings, now);
        const drawn = this.config?.show_timeline !== false && timeline(shown, now, this.language(), this.timeZone()).bars.length > 0;
        const size = (this.config?.title ? 1 : 0) + (drawn ? 2 : 0) + Math.max(1, shown.length);
        return heightCardSize(this.config ?? {}, size, this.minimumHeight());
    }

    /**
     * In a sections view the card takes a whole section by default and is never narrower than two thirds of one, nor
     * lower than its minimum height.
     */
    public getGridOptions(): Record<string, unknown> {
        return { columns: 12, min_columns: 8, rows: "auto", min_rows: gridMinRows(this.minimumHeight()) };
    }

    /** A warning moves from coming up to in force, and one that has expired goes, between the sensor's updates. */
    public connectedCallback(): void {
        super.connectedCallback();
        this.tick++;
        this.ticker = setInterval(() => this.tick++, TICK_MS);
    }

    public disconnectedCallback(): void {
        super.disconnectedCallback();
        clearInterval(this.ticker);
    }

    protected shouldUpdate(changed: PropertyValues): boolean {
        const previous = changed.get("hass") as HomeAssistant | undefined;
        // The layout decides whether the card is held to a height, even when a change of the house comes with it.
        if (
            changed.has("config") ||
            changed.has("layout") ||
            changed.has("opened") ||
            changed.has("tick") ||
            !this.config ||
            !changed.has("hass") ||
            !previous
        ) {
            return true;
        }
        // Home Assistant hands the card every state change in the house; only its own sensor matters.
        return previous.states[this.config.entity] !== this.hass?.states[this.config.entity];
    }

    /** Works out the rows, and forgets an opened row whose warning has gone, so it can't come back open by itself. */
    protected willUpdate(): void {
        const entity = this.config ? this.hass?.states[this.config.entity] : undefined;
        const now = Date.now();
        const shown = isWarningsSensor(entity) ? visibleWarnings(entity.attributes.warnings, now) : [];
        const keys = rowKeys(shown);
        if (this.opened !== undefined && ![...keys.values()].includes(this.opened)) {
            this.opened = undefined;
        }
        this.list = { now, shown, keys };
    }

    protected render(): TemplateResult | typeof nothing {
        if (!this.hass || !this.config) {
            return nothing;
        }
        return html`
            <ha-card style=${this.heightStyle()}>
                ${this.config.title ? html`<h1 class="card-title">${this.config.title}</h1>` : nothing} ${this.content(this.config.entity)}
            </ha-card>
        `;
    }

    private content(entityId: string): TemplateResult {
        const entity = this.hass?.states[entityId];
        if (!entity) {
            return html`<div class="message">${this.text("common.no_entity", { entity: entityId })}</div>`;
        }
        if (entity.state === "unavailable" || entity.state === "unknown") {
            return html`<div class="message">${this.text("common.unavailable")}</div>`;
        }
        if (!isWarningsSensor(entity)) {
            return html`<div class="message">${this.text("common.not_warnings", { entity: entityId })}</div>`;
        }
        const { now, shown, keys } = this.list;
        if (!shown.length) {
            return html`<div class="empty">
                <ha-icon icon="mdi:check-circle-outline"></ha-icon><span>${this.text("common.no_warnings")}</span>
            </div>`;
        }
        // Keyed, so each warning keeps its own row as others come and go, and an open one isn't drawn into a closed one.
        return html`
            <div class="body">
                ${this.config?.show_timeline === false ? nothing : this.timeline(shown, now, keys)}
                <div class="rows">
                    ${repeat(
                        shown,
                        ({ warning }) => keys.get(warning)!,
                        (item) => this.row(item, keys.get(item.warning)!, now),
                    )}
                </div>
            </div>
        `;
    }

    /** Today and the next two days, a bar per warning in lanes they share when they follow each other, and a line at now. */
    private timeline(shown: Shown[], now: number, keys: Map<Warning, string>): TemplateResult | typeof nothing {
        const { days, now: at, bars, lanes } = timeline(shown, now, this.language(), this.timeZone());
        if (!bars.length) {
            return nothing;
        }
        return html`
            <div class="timeline" aria-hidden="true">
                <div class="now-label" style="left:${at}%">${this.text("common.now")}</div>
                <div class="lanes">
                    ${days.slice(1).map(({ left }) => html`<span class="midnight" style="left:${left}%"></span>`)}
                    <span class="now" style="left:${at}%"></span>
                    ${Array.from(
                        { length: lanes },
                        (_, lane) =>
                            html`<div class="lane">
                                ${bars
                                    .filter((bar) => bar.lane === lane)
                                    .map(({ warning, left, width }) => {
                                        const colors = LEVEL_COLORS[warning.level];
                                        return html`<div
                                            class="bar"
                                            style="left:min(${left}%, calc(100% - 22px));width:${width}%;background:${colors.background};color:${colors.text}"
                                            title="${warning.event}"
                                            @click=${() => this.show(keys.get(warning)!)}
                                        >
                                            <ha-icon icon="${icon(warning)}"></ha-icon><span class="label">${this.typeName(warning)}</span>
                                        </div>`;
                                    })}
                            </div>`,
                    )}
                </div>
                <div class="days">${days.map(({ label, left }) => html`<span style="left:${left}%">${label}</span>`)}</div>
            </div>
        `;
    }

    /** A warning on one line, its details under it once opened. */
    private row({ warning, active }: Shown, key: string, now: number): TemplateResult {
        const open = this.opened === key;
        const color = LEVEL_COLORS[warning.level].background;
        const level = this.text(`levels.${warning.level}`);
        return html`
            <div class="row ${active ? "" : "upcoming"}" data-key=${key}>
                <span class="stripe" style="background:${color}"></span>
                <div class="row-body">
                    <button class="summary" aria-expanded="${open}" @click=${() => this.toggle(key)}>
                        <ha-icon icon="${icon(warning)}" style="color:${color}"></ha-icon>
                        <span class="visually-hidden">${level}</span>
                        <span class="text">
                            <span class="name">${warning.event}</span>
                            <span class="time">${this.period(warning, active, now)}</span>
                        </span>
                        <ha-icon class="chevron" icon="mdi:chevron-down"></ha-icon>
                    </button>
                    <div class="expander ${open ? "open" : ""}" ?inert=${!open} @transitionend=${this.opening}>
                        <div class="clip">
                            <div class="details">
                                <div class="level">${level}</div>
                                ${warning.description ? html`<div>${warning.description}</div>` : nothing}
                                ${warning.impacts ? html`<div class="impacts">${warning.impacts}</div>` : nothing}
                                ${
                                    typeof warning.probability === "number"
                                        ? html`<div class="probability">
                                              ${this.text("common.probability", { value: String(warning.probability) })}
                                          </div>`
                                        : nothing
                                }
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    /** "nyt – ti 3.00" for a warning in force, "ti 6.00 – ti 12.00" for one coming up, "from …" for one with no end. */
    private period(warning: Warning, active: boolean, now: number): string {
        const start = active || warning.onset === null ? this.text("common.now") : this.moment(warning.onset, now);
        return warning.expires === null
            ? this.text("common.from", { start })
            : this.text("common.period", { start, end: this.moment(warning.expires, now) });
    }

    private moment(time: string, now: number): string {
        return moment(time, now, this.language(), this.timeZone(), this.hour12());
    }

    /** The user's choice of clock in their profile. "language" leaves it to the language. */
    private hour12(): boolean | undefined {
        switch (this.hass?.locale?.time_format) {
            case "12":
                return true;
            case "24":
                return false;
            case "system":
                return new Intl.DateTimeFormat(undefined, { hour: "numeric" }).resolvedOptions().hour12;
            default:
                return undefined;
        }
    }

    /** A short name for a bar on the timeline. A type FMI adds later has none, and goes by the warning's own name. */
    private typeName(warning: Warning): string {
        const key = `types.${warning.type}`;
        const name = translate(this.language(), key);
        return name === key ? warning.event : name;
    }

    private toggle(key: string): void {
        this.opened = this.opened === key ? undefined : key;
        this.revealing = this.opened;
    }

    /** A bar tapped on the timeline opens its row, which is then brought into view. One already open has no opening to wait for. */
    private show(key: string): void {
        if (this.opened !== key) {
            this.toggle(key);
            return;
        }
        scrollTo([...this.renderRoot.querySelectorAll<HTMLElement>(".row")].find((element) => element.dataset.key === key));
    }

    /** Once a row a tap opened has slid open, scrolls the body or the page just enough to show it. */
    private opening = (event: TransitionEvent): void => {
        const row = (event.currentTarget as HTMLElement).closest<HTMLElement>(".row");
        if (event.propertyName !== "grid-template-rows" || event.target !== event.currentTarget || row?.dataset.key !== this.revealing) {
            return;
        }
        this.revealing = undefined;
        scrollTo(row);
    };

    /**
     * The lowest the card is held to, in pixels: its padding, the title when it has one, a timeline of one lane when it
     * is shown, and one warning row. The padding (with the card's border), the title and the timeline as measured on a
     * full section's width, the row estimated from the styles.
     */
    private minimumHeight(): number {
        const padding = 34;
        const title = 41;
        const timeline = 75;
        const row = 40;
        return padding + (this.config?.title ? title : 0) + (this.config?.show_timeline === false ? 0 : timeline) + row;
    }

    private heightStyle(): string {
        return heightStyle(this.config ?? {}, this.layout, this.minimumHeight());
    }

    private timeZone(): string | undefined {
        return this.hass?.locale?.time_zone === "server" ? this.hass.config?.time_zone : undefined;
    }

    /** A text in the viewer's language, with `{name}` in it replaced, so a translation can put the value where it reads right. */
    private text(key: string, values: Record<string, string> = {}): string {
        return translate(this.language(), key).replace(/\{(\w+)\}/g, (match, name: string) => values[name] ?? match);
    }

    private language(): string {
        return this.hass?.locale?.language ?? this.hass?.language ?? browserLanguage();
    }

    static get styles(): CSSResultGroup {
        return [
            css`
                :host {
                    display: block;
                    height: 100%;
                }

                /*
                 * The card is the container its layout measures, so it follows its own width, in a sections view or not.
                 * Held to a height, fixed or at most, or by a fixed number of rows in a sections view, the title stays and the
                 * timeline scrolls with the rows, as its lanes follow the warnings and could otherwise leave no room for a
                 * row. The card is never lower than its title, a timeline of one lane and a row. Clipped, not hidden,
                 * which would make the card a scroller that bringing a row into view could scroll out of place.
                 */
                ha-card {
                    overflow: clip;
                    container-type: inline-size;
                    box-sizing: border-box;
                    height: 100%;
                    display: flex;
                    flex-direction: column;
                    padding: 16px;
                    font-variant-numeric: tabular-nums;
                }

                ha-card > * {
                    flex: none;
                }

                /*
                 * Never sideways, where a turning chevron would otherwise flash a scrollbar for a moment. It reaches out over
                 * the card's padding to the sides, so its clipped edges don't cut what sits at the content's edge, such as the
                 * timeline's "now" label near midnight.
                 */
                ha-card > .body {
                    margin: 0 -16px;
                    padding: 0 16px;
                    flex: 1 1 auto;
                    min-height: 0;
                    overflow-x: hidden;
                    overflow-y: auto;
                    overscroll-behavior: contain;
                    scrollbar-width: thin;
                }

                .card-title {
                    margin: 0 0 12px;
                    font-size: var(--ha-card-header-font-size, 24px);
                    font-weight: var(--ha-font-weight-normal, 400);
                    line-height: 1.2;
                }

                .message {
                    color: var(--secondary-text-color);
                }

                .empty {
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    color: var(--secondary-text-color);
                }

                .empty ha-icon {
                    flex: none;
                    color: var(--success-color, #43a047);
                }

                .timeline {
                    position: relative;
                    margin-bottom: 8px;
                    padding-top: 16px;
                }

                .now-label {
                    position: absolute;
                    top: 0;
                    transform: translateX(-50%);
                    font-size: 11px;
                    line-height: 14px;
                    color: var(--primary-text-color);
                }

                .lanes {
                    position: relative;
                    padding: 2px 0;
                }

                .lane {
                    position: relative;
                    height: 22px;
                    margin: 4px 0;
                }

                .midnight,
                .now {
                    position: absolute;
                    top: 0;
                    bottom: 0;
                }

                .midnight {
                    width: 1px;
                    background: var(--divider-color);
                }

                /* Behind the bars, which come after it. */
                .now {
                    width: 2px;
                    margin-left: -1px;
                    background: var(--primary-text-color);
                    opacity: 0.7;
                }

                .now-label,
                .now {
                    pointer-events: none;
                }

                .bar {
                    position: absolute;
                    cursor: pointer;
                    top: 0;
                    box-sizing: border-box;
                    min-width: 22px;
                    height: 22px;
                    display: flex;
                    flex-wrap: wrap;
                    align-items: center;
                    column-gap: 4px;
                    padding: 0 3px;
                    border-radius: 6px;
                    font-size: 12px;
                    line-height: 22px;
                    white-space: nowrap;
                    overflow: hidden;
                }

                .bar ha-icon {
                    --mdc-icon-size: 16px;
                    flex: none;
                    width: 16px;
                    height: 22px;
                    display: inline-flex;
                    align-items: center;
                }

                /* A label that doesn't fit whole wraps to a second line, which the bar's height hides, leaving the icon alone. */
                .bar .label {
                    flex: none;
                }

                /* Below 400 px inside the padding, the bars are too short to name. The rows below say what each is. */
                @container (max-width: 399px) {
                    .bar .label {
                        display: none;
                    }
                }

                .days {
                    position: relative;
                    height: 16px;
                    border-top: 1px solid var(--divider-color);
                    font-size: 12px;
                    line-height: 16px;
                    color: var(--secondary-text-color);
                }

                .days span {
                    position: absolute;
                    padding-left: 4px;
                }

                .row {
                    display: flex;
                    gap: 10px;
                    border-top: 1px solid var(--divider-color);
                }

                .row:first-child {
                    border-top: none;
                }

                .stripe {
                    flex: none;
                    width: 4px;
                    margin: 8px 0;
                    border-radius: 2px;
                }

                .row-body {
                    flex: 1;
                    min-width: 0;
                }

                /* Drawn inside, where the body's clipped edges can't cut it. */
                .summary:focus-visible {
                    outline-offset: -2px;
                }

                .summary {
                    position: relative;
                    display: grid;
                    grid-template-columns: 24px minmax(0, 1fr) 20px;
                    align-items: center;
                    gap: 10px;
                    width: 100%;
                    padding: 8px 0;
                    border: none;
                    background: none;
                    color: inherit;
                    font: inherit;
                    font-size: 14px;
                    text-align: left;
                    cursor: pointer;
                }

                /* The name and the time on one line while both fit whole; the time moves under the name when they don't. */
                .text {
                    display: flex;
                    flex-wrap: wrap;
                    align-items: baseline;
                    gap: 2px 10px;
                    min-width: 0;
                }

                /* One line, cut short when even a line of its own is too narrow. An opened row shows it whole. */
                .name {
                    flex: 1 1 auto;
                    min-width: 0;
                    overflow: hidden;
                    white-space: nowrap;
                    text-overflow: ellipsis;
                }

                .summary[aria-expanded="true"] .name {
                    white-space: normal;
                    overflow-wrap: anywhere;
                }

                .time {
                    font-size: 13px;
                    color: var(--secondary-text-color);
                }

                .chevron {
                    --mdc-icon-size: 20px;
                    display: flex;
                    color: var(--secondary-text-color);
                    transition: transform 0.2s;
                }

                .summary[aria-expanded="true"] .chevron {
                    transform: rotate(180deg);
                }

                .upcoming .summary ha-icon,
                .upcoming .name {
                    opacity: 0.75;
                }

                /* The details are always there, folded to nothing and inert while the row is closed, so opening can slide. */
                .expander {
                    display: grid;
                    grid-template-rows: 0fr;
                    transition: grid-template-rows 0.2s ease;
                }

                .expander.open {
                    grid-template-rows: 1fr;
                }

                .clip {
                    min-height: 0;
                    overflow: hidden;
                }

                /* Over in a moment rather than not at all, so the row is still brought into view when it ends. */
                @media (prefers-reduced-motion: reduce) {
                    .expander,
                    .chevron {
                        transition-duration: 1ms;
                    }
                }

                .details {
                    display: grid;
                    gap: 4px;
                    padding: 0 0 10px 34px;
                    font-size: 13px;
                    line-height: 1.4;
                    overflow-wrap: anywhere;
                }

                .visually-hidden {
                    position: absolute;
                    width: 1px;
                    height: 1px;
                    overflow: hidden;
                    clip-path: inset(50%);
                    white-space: nowrap;
                }

                .level {
                    font-weight: var(--ha-font-weight-medium, 500);
                }

                .impacts {
                    font-style: italic;
                    color: var(--secondary-text-color);
                }

                .probability {
                    color: var(--secondary-text-color);
                }
            `,
            fadeStyles,
        ];
    }
}

/** Scrolls the body or the page just enough to show a row, its top first if it is taller than the body shows between its fades. */
function scrollTo(row: HTMLElement | null | undefined): void {
    if (!row) {
        return;
    }
    const behavior = (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false) ? "auto" : "smooth";
    const body = row.closest<HTMLElement>(".body");
    // A body that fades keeps its fade length clear at each end as scroll padding, as fadeStyles sets it.
    const padding = body?.classList.contains("fades") ? Math.min(24, body.clientHeight / 4) : 0;
    // Taller than the view between the paddings and starting above it, a row would be lined up by its bottom, its name
    // out of sight, so it is lined up by its top instead, under the top fade.
    if (body && row.offsetHeight > body.clientHeight - 2 * padding) {
        body.scrollTo({ top: body.scrollTop + row.getBoundingClientRect().top - body.getBoundingClientRect().top - padding, behavior });
        body.scrollIntoView({ block: "nearest", behavior });
        return;
    }
    row.scrollIntoView({ block: "nearest", behavior });
}

function icon(warning: Warning): string {
    return TYPE_ICONS[warning.type] ?? FALLBACK_ICON;
}

/**
 * A key per row. FMI gives a warning a new id each time it reissues it, usually unchanged, so a row goes by what the
 * warning is instead, numbered as a last resort when two are alike even in their areas.
 */
function rowKeys(shown: Shown[]): Map<Warning, string> {
    const seen = new Map<string, number>();
    return new Map(
        shown.map(({ warning }) => {
            // The areas tell apart twins such as the same warning for two sea areas, which FMI may list in either order.
            const areas = Array.isArray(warning.areas) ? warning.areas : [];
            // The start as a moment, as a reissue may write the same one with another offset.
            const onset = warning.onset === null ? "" : Date.parse(warning.onset);
            const key = `${warning.type}|${warning.level}|${onset}|${areas.join(",")}`;
            const count = seen.get(key) ?? 0;
            seen.set(key, count + 1);
            return [warning, count ? `${key}#${count}` : key];
        }),
    );
}

interface CardRegistration {
    type: string;
    name: string;
    description: string;
    documentationURL?: string;
    preview?: boolean;
}

// Anyone who installed the card on its own before it came with the integration may still load that copy too, as a
// dashboard resource of its own. Whichever loads first is the card, and the other stays out of the way.
if (!customElements.get("fmi-warnings-card")) {
    console.info(
        `%c  FMI-WARNINGS-CARD \n%c  ${CARD_VERSION}    `,
        "color: orange; font-weight: bold; background: black",
        "color: white; font-weight: bold; background: dimgray",
    );

    const registry = window as unknown as { customCards?: CardRegistration[] };
    registry.customCards = registry.customCards ?? [];
    registry.customCards.push({
        type: "fmi-warnings-card",
        name: translate(browserLanguage(), "common.name"),
        description: translate(browserLanguage(), "common.description"),
        documentationURL: "https://github.com/jesmak/fmi#warnings-card",
        preview: true,
    });
    customElements.define("fmi-warnings-card", FmiWarningsCard);
}

declare global {
    interface HTMLElementTagNameMap {
        "fmi-warnings-card": FmiWarningsCard;
    }
}
