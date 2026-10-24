/** The card's visual editor: the warnings sensor, the title, the timeline and the height. */
import { LitElement, html, nothing } from "lit";
import type { TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";

import type { HomeAssistant } from "./hass";
import { browserLanguage, translate } from "./localize/localize";
import type { FmiWarningsCardConfig } from "./types";
import { warningsSensors } from "./warnings";

interface SchemaEntry {
    name: string;
}

const DEFAULTS: Record<string, unknown> = {
    show_timeline: true,
};

function schema(hass: HomeAssistant) {
    return [
        { name: "entity", required: true, selector: { entity: { include_entities: warningsSensors(hass) } } },
        { name: "title", selector: { text: {} } },
        { name: "show_timeline", selector: { boolean: {} } },
        { name: "max_height", selector: { number: { min: 100, step: 10, mode: "box", unit_of_measurement: "px" } } },
    ];
}

export class FmiWarningsCardEditor extends LitElement {
    @property({ attribute: false }) public hass?: HomeAssistant;
    @state() private config: FmiWarningsCardConfig = { type: "custom:fmi-warnings-card", entity: "" };

    public setConfig(config: FmiWarningsCardConfig): void {
        this.config = { ...config };
    }

    protected render(): TemplateResult | typeof nothing {
        if (!this.hass) {
            return nothing;
        }
        return html`
            <ha-form
                .hass=${this.hass}
                .data=${{ ...DEFAULTS, ...this.config }}
                .schema=${schema(this.hass)}
                .computeLabel=${(entry: SchemaEntry) => this.text(`editor.${entry.name}`)}
                .computeHelper=${(entry: SchemaEntry) => this.helper(entry.name)}
                @value-changed=${this.valueChanged}
            ></ha-form>
        `;
    }

    private valueChanged(event: CustomEvent<{ value: FmiWarningsCardConfig }>): void {
        const config: FmiWarningsCardConfig = { ...event.detail.value };
        if (!config.title) {
            delete config.title;
        }
        if (!config.max_height) {
            delete config.max_height;
        }
        // The defaults are shown in the form but left out of the configuration.
        for (const [key, value] of Object.entries(DEFAULTS)) {
            if (config[key] === value || config[key] === undefined || config[key] === null) {
                delete config[key];
            }
        }
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
    }

    private text(key: string): string {
        return translate(this.language(), key);
    }

    private helper(name: string): string | undefined {
        const key = `editor.${name}_helper`;
        const helper = translate(this.language(), key);
        return helper === key ? undefined : helper;
    }

    private language(): string {
        return this.hass?.locale?.language ?? this.hass?.language ?? browserLanguage();
    }
}

if (!customElements.get("fmi-warnings-card-editor")) {
    customElements.define("fmi-warnings-card-editor", FmiWarningsCardEditor);
}

declare global {
    interface HTMLElementTagNameMap {
        "fmi-warnings-card-editor": FmiWarningsCardEditor;
    }
}
