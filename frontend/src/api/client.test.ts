import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DecisionRecalculationError,
  DemoDecisionLoadError,
  getDemoDecision,
  recalculateDecision,
} from "./client";

describe("product API client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("converts backend and network failures to a safe error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));
    await expect(getDemoDecision()).rejects.toEqual(new DemoDecisionLoadError());
    expect(fetch).toHaveBeenCalledWith("/api/demo/decision", expect.any(Object));
  });

  it("converts recalculation failures to a bounded client error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({ detail: "raw backend diagnostics" }),
      }),
    );
    await expect(
      recalculateDecision({
        pilot_population: 500,
        expected_incremental_lift: "0.03",
        cost_per_intervention: "30",
        retained_customer_value: "500",
        currency: "USD",
      }),
    ).rejects.toEqual(new DecisionRecalculationError());
    expect(fetch).toHaveBeenCalledWith(
      "/api/demo/decision/recalculate",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
