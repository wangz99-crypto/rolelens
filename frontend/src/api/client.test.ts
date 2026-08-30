import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DecisionRecalculationError,
  DemoDecisionLoadError,
  generateRoleBriefs,
  getDemoDecision,
  recalculateDecision,
  RoleBriefGenerationError,
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

  it("posts exact trusted decimal strings to the bounded role-brief route", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          accepted_state_fingerprint: "a".repeat(64),
          provider: "IBM watsonx.ai",
          model_id: "ibm/granite-4-h-small",
          briefs: [],
        }),
      }),
    );
    await generateRoleBriefs({
      pilot_population: 500,
      expected_incremental_lift: "0.03",
      cost_per_intervention: "30",
      retained_customer_value: "500",
      currency: "USD",
    });
    expect(fetch).toHaveBeenCalledWith(
      "/api/demo/decision/role-brief",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          pilot_population: 500,
          expected_incremental_lift: "0.03",
          cost_per_intervention: "30",
          retained_customer_value: "500",
          currency: "USD",
        }),
      }),
    );
  });

  it("sanitizes role-brief backend diagnostics", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));
    await expect(
      generateRoleBriefs({
        pilot_population: 500,
        expected_incremental_lift: "0.03",
        cost_per_intervention: "30",
        retained_customer_value: "500",
        currency: "USD",
      }),
    ).rejects.toEqual(new RoleBriefGenerationError());
  });
});
