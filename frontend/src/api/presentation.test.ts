import { describe, expect, it } from "vitest";
import { scenarioStatusTone } from "./presentation";

describe("scenario status visual tone", () => {
  it("does not present a non-evaluable scenario as positive", () => {
    expect(scenarioStatusTone("CLEARS_BREAK_EVEN")).toBe("positive");
    expect(scenarioStatusTone("DOES_NOT_CLEAR_BREAK_EVEN")).toBe("blocked");
    expect(scenarioStatusTone("NOT_EVALUABLE")).toBe("neutral");
  });
});
