import type { DemoDecision } from "./types";

const SAFE_LOAD_ERROR = "RoleLens could not load the demo decision safely.";

export class DemoDecisionLoadError extends Error {
  constructor() {
    super(SAFE_LOAD_ERROR);
    this.name = "DemoDecisionLoadError";
  }
}

export async function getDemoDecision(): Promise<DemoDecision> {
  try {
    const response = await fetch("/api/demo/decision", {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new DemoDecisionLoadError();
    }
    return (await response.json()) as DemoDecision;
  } catch {
    throw new DemoDecisionLoadError();
  }
}
