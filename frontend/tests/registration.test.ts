import { expect, test, vi } from "vitest";

// A copy of the card installed on its own, before it came with the integration, may be loaded first.
test("a copy of the card loaded earlier stays the card and its editor, and the picker lists it once", async () => {
    class Earlier extends HTMLElement {}
    class EarlierEditor extends HTMLElement {}
    customElements.define("fmi-warnings-card", Earlier);
    customElements.define("fmi-warnings-card-editor", EarlierEditor);
    const registry = window as unknown as { customCards?: unknown[] };
    registry.customCards = [{ type: "fmi-warnings-card" }];
    const info = vi.spyOn(console, "info").mockImplementation(() => undefined);

    await import("../src/fmi-warnings-card");

    expect(customElements.get("fmi-warnings-card")).toBe(Earlier);
    expect(customElements.get("fmi-warnings-card-editor")).toBe(EarlierEditor);
    expect(registry.customCards).toHaveLength(1);
    expect(info).not.toHaveBeenCalled();
});
