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

import { CARD_VERSION, FALLBACK_ICON, LEVEL_COLORS, PAST_COUNT, PAST_DAYS, TICK_MS, TYPE_ICONS } from "./const";
import "./editor";
import { ScrollFade, fadeStyles } from "./fade";
import type { HomeAssistant } from "./hass";
import { gridMinRows, heightCardSize, heightStyle, validHeight } from "./height";
import { browserLanguage, translate } from "./localize/localize";
import { fillLimit, filledHeight, filledStyle, validRowStep } from "./rows";
import type { FmiWarningsCardConfig, Warning } from "./types";
import { eventEntity, isWarningsSensor, moment, pastWarnings, timeline, visibleWarnings, warningsSensors } from "./warnings";
import type { HistoryRow, Past, Shown } from "./warnings";

/** The card's padding and border, top and bottom, so that its parts, each on the half-row step of 32 px, end on the rows. */
const PADDING = 24;

export class FmiWarningsCard extends LitElement {
    @property({ attribute: false }) public hass?: HomeAssistant;
    @property({ attribute: false }) public layout?: string;
    @state() private config?: FmiWarningsCardConfig;
    /** The one warning opened to show its details, by its key from `rowKeys`. Opening another closes it. */
    @state() private opened?: string;
    /** The row just opened by a tap, to be brought into view once it has opened, and only then. */
    private revealing?: string;
    /** The warnings to draw and their rows' keys, those that have ended with theirs, worked out once per update. */
    private list: { now: number; shown: Shown[]; keys: Map<Warning, string>; past: Past[]; pastKeys: Map<Warning, string> } = {
        now: 0,
        shown: [],
        keys: new Map(),
        past: [],
        pastKeys: new Map(),
    };
    /** The place's event entity's history, which the warnings that have ended are worked out from as time goes on. */
    @state() private history: HistoryRow[] = [];
    /** The event entity and its state the history was last read for, so it is read again only after a new event. */
    private historyRead?: string;
    /** The event entity the history is of. */
    private historyEvent?: string;
    private historyFailed = false;
    /** Set when a tap opens a warning over a held card, so the overlay's close button takes the focus once drawn. */
    private focusOverlay = false;
    /** Counts the minutes, so the card redraws for the time even when its sensor hasn't changed. */
    @state() private tick = 0;
    private ticker?: ReturnType<typeof setInterval>;
    /** The height that fills the card's rows on automatic rows, and the room in it the content leaves over. */
    @state() private filled = 0;
    @state() private spare = 0;
    /** While a row slides open or shut, so the card's height follows the slide instead of HA's own transition. */
    @state() private sliding = false;
    private slideTimer?: ReturnType<typeof setTimeout>;
    private frame?: number;
    private readonly resizes = typeof ResizeObserver === "undefined" ? undefined : new ResizeObserver(() => this.measureSoon());

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
        if (!validRowStep(config)) {
            throw new Error(translate(browserLanguage(), "common.invalid_row_step"));
        }
        this.config = config;
    }

    /** In units of 50 px, for a masonry view: the title, the timeline and a row per warning, or the height it is held to. */
    public getCardSize(): number {
        const now = Date.now();
        const shown = visibleWarnings(this.hass?.states[this.config?.entity ?? ""]?.attributes.warnings, now);
        const drawn = this.config?.show_timeline !== false && timeline(shown, now, this.language(), this.timeZone()).bars.length > 0;
        const past = this.list.past.length;
        const size = (this.config?.title ? 1 : 0) + (drawn ? 2 : 0) + Math.max(1, shown.length) + (past ? past + 1 : 0);
        return heightCardSize(this.config ?? {}, size, this.minimumHeight());
    }

    /**
     * In a sections view the card takes a whole section by default. Below 9 columns, 214 px on a 320 px phone, a
     * row's name and time have too little room to read, so it is never narrower, nor lower than its minimum height.
     */
    public getGridOptions(): Record<string, unknown> {
        return { columns: 12, min_columns: 9, rows: "auto", min_rows: gridMinRows(this.minimumHeight()) };
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
        clearTimeout(this.slideTimer);
        this.sliding = false;
        // Read again when back on the page, as events may have come meanwhile.
        this.historyRead = undefined;
        this.resizes?.disconnect();
        cancelAnimationFrame(this.frame ?? 0);
    }

    protected shouldUpdate(changed: PropertyValues): boolean {
        const previous = changed.get("hass") as HomeAssistant | undefined;
        // The layout decides whether the card is held to a height, even when a change of the house comes with it.
        if (
            changed.has("config") ||
            changed.has("layout") ||
            changed.has("opened") ||
            changed.has("tick") ||
            changed.has("filled") ||
            changed.has("spare") ||
            changed.has("sliding") ||
            changed.has("history") ||
            !this.config ||
            !changed.has("hass") ||
            !previous
        ) {
            return true;
        }
        // Home Assistant hands the card every state change in the house; only its own sensor and event entity, the
        // registry that finds the latter, the language and the locale (the time format and time zone with it) matter.
        const event = this.hass ? eventEntity(this.hass, this.config.entity) : undefined;
        return (
            previous.locale !== this.hass?.locale ||
            previous.language !== this.hass?.language ||
            previous.entities !== this.hass?.entities ||
            previous.states[this.config.entity] !== this.hass?.states[this.config.entity] ||
            (event !== undefined && previous.states[event] !== this.hass?.states[event])
        );
    }

    /** Works out the rows, and forgets an opened row whose warning has gone, so it can't come back open by itself. */
    protected willUpdate(): void {
        const entity = this.config ? this.hass?.states[this.config.entity] : undefined;
        const now = Date.now();
        const shown = isWarningsSensor(entity) ? visibleWarnings(entity.attributes.warnings, now) : [];
        const keys = rowKeys(shown);
        const event = this.readHistory();
        // The event entity's state is its latest event, which the recorder may not have written yet when it is read.
        const latest = event ? this.hass?.states[event] : undefined;
        const rows = latest ? [...this.history, { s: latest.state, a: latest.attributes }] : this.history;
        const past = event ? pastWarnings(rows, now, PAST_COUNT) : [];
        // Prefixed, so a row that has ended never shares a key with one in force.
        const pastKeys = new Map(
            [...rowKeys(past.map(({ warning }) => ({ warning, active: false })))].map(([warning, key]) => [warning, `past:${key}`]),
        );
        if (this.opened !== undefined && ![...keys.values(), ...pastKeys.values()].includes(this.opened)) {
            this.opened = undefined;
        }
        this.list = { now, shown, keys, past, pastKeys };
    }

    /**
     * Reads the event entity's history of the last days when the card first has it and after each new event, and returns
     * the event entity, none when the warnings that have ended are turned off or it isn't found. Another place's history
     * is let go at once. A history that can't be read, such as with the recorder left out, shows none, and is tried again
     * at the card's next update.
     */
    private readHistory(): string | undefined {
        const hass = this.hass;
        const event = hass && this.config && this.config.show_past !== false ? eventEntity(hass, this.config.entity) : undefined;
        const read = event ? `${event}|${hass?.states[event]?.state}` : undefined;
        if (read === this.historyRead) {
            return event;
        }
        if (event !== this.historyEvent) {
            this.history = [];
            this.historyEvent = event;
        }
        this.historyRead = read;
        if (!event || !hass?.callWS) {
            return event;
        }
        const now = Date.now();
        hass.callWS<Record<string, HistoryRow[]>>({
            type: "history/history_during_period",
            start_time: new Date(now - PAST_DAYS * 86_400_000).toISOString(),
            entity_ids: [event],
            minimal_response: false,
            no_attributes: false,
            significant_changes_only: false,
        }).then(
            (result) => {
                if (this.historyRead === read) {
                    this.history = result[event] ?? [];
                }
            },
            (error: unknown) => {
                // Said once, as it is tried again at every update, a minute apart at the most.
                if (!this.historyFailed) {
                    console.warn("fmi-warnings-card: couldn't read the warnings that have ended", error);
                    this.historyFailed = true;
                }
                if (this.historyRead === read) {
                    this.historyRead = undefined;
                }
            },
        );
        return event;
    }

    protected render(): TemplateResult | typeof nothing {
        if (!this.hass || !this.config) {
            return nothing;
        }
        const title = this.config.title;
        const held = !!this.heightStyle();
        const classes = [held ? "held" : "", this.sliding ? "sliding" : "", title ? "titled" : ""].filter(Boolean).join(" ");
        return html`
            <ha-card class=${classes} style=${this.cardStyle()}>
                ${title ? html`<h1 class="card-title spare" title=${title}>${title}</h1>` : nothing}
                ${this.content(this.config.entity, title ? "" : "spare-top", held)} ${held ? this.overlay() : nothing}
            </ha-card>
        `;
    }

    protected updated(): void {
        const card = this.renderRoot.querySelector("ha-card");
        if (card && this.isConnected) {
            this.resizes?.observe(card);
            this.measureSoon();
        }
        if (this.focusOverlay) {
            this.focusOverlay = false;
            this.renderRoot.querySelector<HTMLElement>(".overlay .close")?.focus();
        }
    }

    /**
     * `spare` is the class that takes the room a whole row leaves over, on the content when the card has no title. Held to
     * a height, the timeline stays in a band of its own above the rows, and only they and the warnings that have ended
     * scroll.
     */
    private content(entityId: string, spare: string, held: boolean): TemplateResult {
        const entity = this.hass?.states[entityId];
        if (!entity) {
            return html`<div class="message ${spare}">${this.text("common.no_entity", { entity: entityId })}</div>`;
        }
        if (entity.state === "unavailable" || entity.state === "unknown") {
            return html`<div class="message ${spare}">${this.text("common.unavailable")}</div>`;
        }
        if (!isWarningsSensor(entity)) {
            return html`<div class="message ${spare}">${this.text("common.not_warnings", { entity: entityId })}</div>`;
        }
        const { now, shown, keys, past, pastKeys } = this.list;
        // Under an open warning, the rows are out of reach of Tab and a screen reader, as of a tap.
        const covered = held && this.opened !== undefined;
        // Keyed, so each warning keeps its own row as others come and go, and an open one isn't drawn into a closed one.
        const ended = past.length
            ? html`<div class="past-label">${this.text("common.past")}</div>
                  <div class="rows past">
                      ${repeat(
                          past,
                          ({ warning }) => pastKeys.get(warning)!,
                          (item) => this.row({ warning: item.warning, active: false }, pastKeys.get(item.warning)!, now, held, item),
                      )}
                  </div>`
            : nothing;
        if (!shown.length) {
            return html`<div class="empty ${spare}">
                    <ha-icon icon="mdi:check-circle-outline"></ha-icon><span>${this.text("common.no_warnings")}</span>
                </div>
                ${past.length ? html`<div class="body" ?inert=${covered}>${ended}</div>` : nothing}`;
        }
        const timeline = this.config?.show_timeline === false ? nothing : this.timeline(shown, now, keys, held);
        const rows = html`<div class="rows">
            ${repeat(
                shown,
                ({ warning }) => keys.get(warning)!,
                (item) => this.row(item, keys.get(item.warning)!, now, held),
            )}
        </div>`;
        if (held) {
            return html`<div class="band ${spare}">${timeline}</div>
                <div class="body" ?inert=${covered}>${rows}${ended}</div>`;
        }
        return html`<div class="body ${spare}">${timeline}${rows}${ended}</div>`;
    }

    /**
     * Today and the next two days, a bar per warning in lanes they share when they follow each other, and a line at now.
     * Held, the lanes share the room of one, so the timeline is the same height whatever the warnings: two lanes are
     * bars with an icon, more are thin bars alone.
     */
    private timeline(shown: Shown[], now: number, keys: Map<Warning, string>, held: boolean): TemplateResult | typeof nothing {
        const { days, now: at, bars, lanes } = timeline(shown, now, this.language(), this.timeZone());
        if (!bars.length) {
            return nothing;
        }
        const packed = held && lanes > 1 ? `packed ${lanes > 2 ? "thin" : ""}` : "";
        return html`
            <div class="timeline" aria-hidden="true">
                <div class="now-label" style="left:${at}%">${this.text("common.now")}</div>
                <div class="lanes ${packed}" style="--lane: ${32 / lanes}px">
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

    /**
     * A warning's row, its details under it once opened, or held to a height, over the card. `past` is the warning that has
     * ended or was cancelled that the row is for.
     */
    private row({ warning, active }: Shown, key: string, now: number, held: boolean, past?: Past): TemplateResult {
        const open = this.opened === key;
        const color = LEVEL_COLORS[warning.level].background;
        const level = this.text(`levels.${warning.level}`);
        return html`
            <div class="row ${active || past ? "" : "upcoming"}" data-key=${key}>
                <span class="stripe" style="background:${color}"></span>
                <div class="row-body">
                    <button
                        class="summary"
                        aria-expanded="${held ? nothing : open}"
                        aria-haspopup=${held ? "dialog" : nothing}
                        @click=${() => this.toggle(key)}
                    >
                        <ha-icon icon="${icon(warning)}" style="color:${color}"></ha-icon>
                        <span class="visually-hidden">${level}</span>
                        <span class="text">
                            <span class="name" title=${warning.event}>${warning.event}</span>
                            <span class="time">${past ? this.ended(past, now) : this.period(warning, active, now)}</span>
                        </span>
                        <ha-icon class="chevron" icon=${held ? "mdi:chevron-right" : "mdi:chevron-down"}></ha-icon>
                    </button>
                    ${
                        held
                            ? nothing
                            : html`<div class="expander ${open ? "open" : ""}" ?inert=${!open} @transitionend=${this.opening}>
                                  <div class="clip">${this.details(warning, level)}</div>
                              </div>`
                    }
                </div>
            </div>
        `;
    }

    private details(warning: Warning, level: string): TemplateResult {
        return html`<div class="details">
            <div class="level">${level}</div>
            ${warning.description ? html`<div>${warning.description}</div>` : nothing}
            ${warning.impacts ? html`<div class="impacts">${warning.impacts}</div>` : nothing}
            ${
                typeof warning.probability === "number"
                    ? html`<div class="probability">${this.text("common.probability", { value: String(warning.probability) })}</div>`
                    : nothing
            }
        </div>`;
    }

    /** The opened warning over a held card, under its title, its details scrolling inside it when they are long. */
    private overlay(): TemplateResult | typeof nothing {
        const { now, shown, keys, past, pastKeys } = this.list;
        const current = shown.find(({ warning }) => keys.get(warning) === this.opened);
        const ended = current ? undefined : past.find(({ warning }) => pastKeys.get(warning) === this.opened);
        const warning = current?.warning ?? ended?.warning;
        if (!warning) {
            return nothing;
        }
        const color = LEVEL_COLORS[warning.level].background;
        const level = this.text(`levels.${warning.level}`);
        const time = ended ? this.ended(ended, now) : this.period(warning, current!.active, now);
        return html`
            <div class="overlay" role="dialog" aria-label=${warning.event} tabindex="-1" @keydown=${this.overlayKey}>
                <div class="overlay-head">
                    <span class="stripe" style="background:${color}"></span>
                    <ha-icon icon="${icon(warning)}" style="color:${color}"></ha-icon>
                    <span class="overlay-title">
                        <span class="name" title=${warning.event}>${warning.event}</span>
                        <span class="time">${time}</span>
                    </span>
                    <button class="close" aria-label=${this.text("common.close")} @click=${() => this.close()}>
                        <ha-icon icon="mdi:close"></ha-icon>
                    </button>
                </div>
                <div class="overlay-body">${this.details(warning, level)}</div>
            </div>
        `;
    }

    private overlayKey = (event: KeyboardEvent): void => {
        if (event.key === "Escape") {
            event.stopPropagation();
            this.close();
        }
    };

    /** Closes the overlay, and gives the focus back to the row it was opened from. */
    private close(): void {
        const key = this.opened;
        this.opened = undefined;
        void this.updateComplete.then(() =>
            [...this.renderRoot.querySelectorAll<HTMLElement>(".row")]
                .find((row) => row.dataset.key === key)
                ?.querySelector<HTMLElement>(".summary")
                ?.focus(),
        );
    }

    /** "päättyi ti 9.00" for a warning that has ended, "peruttu, ti 6.00" with its start for one that was cancelled. */
    private ended({ warning, cancelled }: Past, now: number): string {
        if (cancelled) {
            const start = warning.onset ?? warning.expires;
            return start === null
                ? this.text("common.cancelled_untimed")
                : this.text("common.cancelled", { time: this.moment(start, now) });
        }
        return this.text("common.ended", { time: this.moment(warning.expires!, now) });
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
        // Held, a warning opens over the card, which doesn't slide or move.
        if (this.heightStyle()) {
            this.opened = key;
            this.focusOverlay = true;
            return;
        }
        this.opened = this.opened === key ? undefined : key;
        this.revealing = this.opened;
        // Lifted when the slide ends, or after a second in case no transition comes to say so.
        this.sliding = true;
        clearTimeout(this.slideTimer);
        this.slideTimer = setTimeout(() => (this.sliding = false), 1000);
    }

    /** A bar tapped on the timeline opens its row, which is then brought into view. One already open has no opening to wait for. */
    private show(key: string): void {
        if (this.opened !== key || this.heightStyle()) {
            this.toggle(key);
            return;
        }
        scrollTo([...this.renderRoot.querySelectorAll<HTMLElement>(".row")].find((element) => element.dataset.key === key));
    }

    /** Once a row a tap opened has slid open, scrolls the body or the page just enough to show it. */
    private opening = (event: TransitionEvent): void => {
        const row = (event.currentTarget as HTMLElement).closest<HTMLElement>(".row");
        if (event.propertyName !== "grid-template-rows" || event.target !== event.currentTarget) {
            return;
        }
        // Another row may still be sliding, as one reversed halfway ends before the one opening beside it.
        const moving = [...this.renderRoot.querySelectorAll(".expander")].some(
            (expander) => expander !== event.currentTarget && (expander.getAnimations?.().length ?? 0) > 0,
        );
        if (!moving) {
            this.sliding = false;
            clearTimeout(this.slideTimer);
        }
        if (row?.dataset.key !== this.revealing) {
            return;
        }
        this.revealing = undefined;
        scrollTo(row);
    };

    /**
     * The lowest the card is held to, in pixels: its padding and border, the title when it has one, the timeline's band
     * when it is shown, and the first line of a warning's row, each on the half-row step. The rest of a row that wraps
     * scrolls with the other rows.
     */
    private minimumHeight(): number {
        const step = 32;
        return PADDING + (this.config?.title ? step : 0) + (this.config?.show_timeline === false ? 0 : 2 * step) + step;
    }

    private heightStyle(): string {
        return heightStyle(this.config ?? {}, this.layout, this.minimumHeight());
    }

    private measureSoon(): void {
        cancelAnimationFrame(this.frame ?? 0);
        this.frame = requestAnimationFrame(() => this.fillRows());
    }

    /**
     * In a sections view whose rows are left automatic, the card takes the whole rows its content needs, or the half rows
     * with `row_step: half`, so the cards under it stay on the rows, up to the limit of a card that grows up to one. The
     * room left over goes under the title, or above
     * the content without one. A row sliding open or shut counts as it will be when the slide ends.
     */
    private fillRows(): void {
        const card = this.renderRoot.querySelector<HTMLElement>("ha-card");
        if (!card || !card.clientWidth) {
            return;
        }
        const limit = fillLimit(this.config ?? {}, this.layout, this.minimumHeight());
        if (!limit) {
            this.filled = 0;
            this.spare = 0;
            return;
        }
        // From the card's top to the end of its own last part, never its own height, which is the min-height set here, and
        // never an element a theme adds to it.
        const parts = card.querySelectorAll<HTMLElement>(
            ":scope > .card-title, :scope > .message, :scope > .empty, :scope > .band > .timeline, :scope > .body > .timeline, " +
                ":scope > .body > .rows > .row, :scope > .body > .past-label",
        );
        const last = parts[parts.length - 1];
        if (!last) {
            return;
        }
        const style = getComputedStyle(card);
        let content =
            last.getBoundingClientRect().bottom - card.getBoundingClientRect().top + px(style.paddingBottom) + px(style.borderBottomWidth);
        // A slide's box is clipped while it moves, so each fold counts at its end: an open one at its details, a shut one at nothing.
        for (const expander of card.querySelectorAll<HTMLElement>(".expander")) {
            const end = expander.classList.contains("open")
                ? (expander.querySelector<HTMLElement>(".details")?.getBoundingClientRect().height ?? 0)
                : 0;
            content += end - expander.getBoundingClientRect().height;
        }
        // The spare room as drawn now.
        const spare = card.querySelector<HTMLElement>(".spare, .spare-top");
        if (spare) {
            const spareStyle = getComputedStyle(spare);
            content -= px(spare.classList.contains("spare") ? spareStyle.paddingBottom : spareStyle.paddingTop);
        }
        const filled = filledHeight(Math.round(content), this.config ?? {}, limit);
        this.filled = filled;
        this.spare = Math.max(0, Math.floor(filled - content));
    }

    /** The card's inline style: the height it is held to, or the rows it fills up to any limit, with their spare room. */
    private cardStyle(): string {
        const style = filledStyle(this.config ?? {}, this.layout, this.minimumHeight(), this.filled);
        return this.filled ? `${style}; --spare: ${this.spare}px` : style;
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
                 * Held to a height, fixed or at most, or by a fixed number of rows in a sections view, the title and the
                 * timeline's band stay and only the rows scroll, and an opened warning covers the card under its title. The
                 * card is never lower than its title, the band and a row. Clipped, not hidden, which would make the card a
                 * scroller that bringing a row into view could scroll out of place. Positioned, for the overlay.
                 *
                 * Its parts step in half rows of a sections view, 32 px, so that with its 24 px of padding and border the
                 * card is 32k − 8 px tall and fills whole or half rows exactly: the title, a line of a row or of a message,
                 * and the timeline's frame and each of its lanes one step each. Only an opened row's details are free.
                 */
                ha-card {
                    /* ha-card's own transition covers every property, so a change in the rows filled would animate. Only a slide does. */
                    transition: none;
                    position: relative;
                    overflow: clip;
                    container-type: inline-size;
                    box-sizing: border-box;
                    height: 100%;
                    display: flex;
                    flex-direction: column;
                    padding: 11px 16px;
                    font-variant-numeric: tabular-nums;
                }

                /* The card's height follows a row's slide, instead of moving on Home Assistant's own transition. */
                ha-card.sliding {
                    transition: min-height 0.2s ease;
                }

                /* And so does the room a whole row leaves over, which changes with the slide's end. */
                ha-card.sliding > .spare,
                ha-card.sliding > .spare-top {
                    transition: padding 0.2s ease;
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
                    scrollbar-width: thin;
                }

                /* Held, the rows keep the scrollbar's room whether they scroll or not, as room that came with the scrolling
                would make a row's time go under its name, and keep the card scrolling. */
                ha-card.held > .body {
                    scrollbar-gutter: stable;
                }

                .card-title {
                    margin: 0;
                    font-size: var(--ha-card-header-font-size, 24px);
                    font-weight: var(--ha-font-weight-normal, 400);
                    line-height: 32px;
                    overflow-wrap: anywhere;
                }

                /* The room a whole row leaves over, under the title, or above the content without one. Padding, not a
                margin, which would collapse into a neighbour's. */
                ha-card > .spare {
                    padding-bottom: var(--spare, 0px);
                }

                ha-card > .spare-top {
                    padding-top: var(--spare, 0px);
                }

                .message {
                    line-height: 32px;
                    color: var(--secondary-text-color);
                }

                .empty {
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    line-height: 32px;
                    color: var(--secondary-text-color);
                }

                /* Held to a height, the title keeps to one line, cut short with its whole text as a tooltip. */
                ha-card.held .card-title {
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                }

                .empty ha-icon {
                    flex: none;
                    color: var(--success-color, #43a047);
                }

                /* The label at now and the days make one step, each lane another. */
                .timeline {
                    position: relative;
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
                }

                .lane {
                    position: relative;
                    height: 32px;
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
                    top: 5px;
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

                /* On a card narrower than 434 px, 400 inside its padding, the bars are too short to name. The rows say what each is. */
                @container (max-width: 399px) {
                    .bar .label {
                        display: none;
                    }
                }

                /* Held, the lanes share one lane's step: two are bars with a small icon, more are thin bars alone. */
                .lanes.packed .lane {
                    height: var(--lane);
                }

                .lanes.packed .bar {
                    top: 1px;
                    height: calc(var(--lane) - 2px);
                    border-radius: 4px;
                    line-height: normal;
                }

                .lanes.packed .bar .label {
                    display: none;
                }

                .lanes.packed .bar ha-icon {
                    --mdc-icon-size: 12px;
                    width: 12px;
                    height: 14px;
                }

                .lanes.packed.thin .bar ha-icon {
                    display: none;
                }

                .days {
                    position: relative;
                    box-sizing: border-box;
                    height: 16px;
                    border-top: 1px solid var(--divider-color);
                    font-size: 12px;
                    line-height: 15px;
                    color: var(--secondary-text-color);
                }

                .days span {
                    position: absolute;
                    padding-left: 4px;
                }

                .row {
                    display: flex;
                    gap: 10px;
                }

                /* A line drawn between the rows, not a border, which would take a pixel off the step. */
                .row + .row {
                    box-shadow: inset 0 1px var(--divider-color);
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
                    padding: 4px 0;
                    border: none;
                    background: none;
                    color: inherit;
                    font: inherit;
                    font-size: 14px;
                    text-align: left;
                    cursor: pointer;
                }

                /*
                 * The name and the time on one line while both fit whole; the time moves under the name when they don't. Each
                 * line is a step, its first 24 px inside the summary's padding. Centred on the line, not on a shared baseline,
                 * which for the name's and the time's two sizes would add a pixel to it.
                 */
                .text {
                    display: flex;
                    flex-wrap: wrap;
                    align-items: center;
                    gap: 0 10px;
                    min-width: 0;
                    margin: -4px 0;
                    line-height: 32px;
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

                /* The warnings that have ended, under a label of half a row, dimmed, a line above the first of them. */
                .past-label {
                    box-shadow: inset 0 1px var(--divider-color);
                    color: var(--secondary-text-color);
                    font-size: 12px;
                    font-weight: var(--ha-font-weight-medium, 500);
                    line-height: 32px;
                    text-transform: uppercase;
                    letter-spacing: 0.04em;
                }

                .past .stripe,
                .past .summary > ha-icon,
                .past .name,
                .past .time {
                    opacity: 0.55;
                }

                /* Under the title, or over the whole card without one, its details scrolling when they are long. */
                /* Focusable only so a click on its text keeps the focus, and Escape, inside it: no ring of its own. */
                .overlay {
                    outline: none;
                    position: absolute;
                    inset: 0;
                    display: flex;
                    flex-direction: column;
                    padding: 11px 0 11px 16px;
                    background: var(--ha-card-background, var(--card-background-color, #fff));
                    animation: overlay-in 0.15s ease-out;
                }

                ha-card.titled .overlay {
                    top: calc(43px + var(--spare, 0px));
                    padding-top: 0;
                    box-shadow: inset 0 1px var(--divider-color);
                }

                @keyframes overlay-in {
                    from {
                        opacity: 0;
                        transform: translateY(8px);
                    }
                }

                @media (prefers-reduced-motion: reduce) {
                    .overlay {
                        animation: none;
                    }
                }

                .overlay-head {
                    flex: none;
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    min-height: 48px;
                    padding-right: 4px;
                }

                .overlay-head .stripe {
                    align-self: stretch;
                    margin: 10px 0;
                }

                .overlay-title {
                    flex: 1;
                    display: flex;
                    flex-direction: column;
                    min-width: 0;
                }

                .overlay-title .name {
                    font-weight: var(--ha-font-weight-medium, 500);
                    line-height: 20px;
                }

                .overlay-title .time {
                    line-height: 18px;
                }

                .close {
                    flex: none;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    width: 40px;
                    height: 40px;
                    padding: 0;
                    border: none;
                    border-radius: 50%;
                    background: none;
                    color: var(--primary-text-color);
                    cursor: pointer;
                }

                .close:hover {
                    background: rgba(var(--rgb-primary-text-color, 33, 33, 33), 0.08);
                }

                .close:focus-visible {
                    outline: 2px solid var(--primary-color);
                    outline-offset: -2px;
                }

                .overlay-body {
                    flex: 1 1 auto;
                    min-height: 0;
                    overflow-y: auto;
                    scrollbar-width: thin;
                    padding-right: 16px;
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
                    .chevron,
                    ha-card.sliding,
                    ha-card.sliding > .spare,
                    ha-card.sliding > .spare-top {
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

/**
 * Scrolls the page just enough to show a row opened in an auto card. A held card, whose body scrolls, opens a warning over
 * itself instead.
 */
function scrollTo(row: HTMLElement | null | undefined): void {
    const behavior = (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false) ? "auto" : "smooth";
    row?.scrollIntoView({ block: "nearest", behavior });
}

function px(value: string): number {
    return parseFloat(value) || 0;
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
