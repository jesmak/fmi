import { expect, test, vi } from "vitest";

// A file of its own, as the first copy has to be loaded into a page that has none.
test("the first copy registers the card and its editor, lists it in the picker and logs its version", async () => {
    const info = vi.spyOn(console, "info").mockImplementation(() => undefined);

    await import("../src/fmi-warnings-card");

    expect(customElements.get("fmi-warnings-card")).toBeDefined();
    expect(customElements.get("fmi-warnings-card-editor")).toBeDefined();
    const registry = window as unknown as { customCards?: { type: string }[] };
    expect(registry.customCards?.filter((card) => card.type === "fmi-warnings-card")).toEqual([
        {
            type: "fmi-warnings-card",
            name: "FMI warnings",
            description: expect.any(String),
            documentationURL: "https://github.com/jesmak/fmi#warnings-card",
            preview: true,
        },
    ]);
    expect(info).toHaveBeenCalledTimes(1);
    expect(info.mock.calls[0]?.[0]).toContain("FMI-WARNINGS-CARD");
});
