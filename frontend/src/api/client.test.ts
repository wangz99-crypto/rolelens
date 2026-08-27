import { afterEach, describe, expect, it, vi } from "vitest";
import { DemoDecisionLoadError, getDemoDecision } from "./client";

describe("product API client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("converts backend and network failures to a safe error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));
    await expect(getDemoDecision()).rejects.toEqual(new DemoDecisionLoadError());
    expect(fetch).toHaveBeenCalledWith("/api/demo/decision", expect.any(Object));
  });
});
