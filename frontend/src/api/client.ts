import type {
  DemoDecision,
  RecalculateDecisionInput,
  RecalculatedDecision,
} from "./types";

const SAFE_LOAD_ERROR = "RoleLens could not load the demo decision safely.";
const SAFE_RECALCULATION_ERROR =
  "Decision impact could not be recalculated safely.";

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

export class DecisionRecalculationError extends Error {
  constructor() {
    super(SAFE_RECALCULATION_ERROR);
    this.name = "DecisionRecalculationError";
  }
}

export async function recalculateDecision(
  input: RecalculateDecisionInput,
): Promise<RecalculatedDecision> {
  try {
    const response = await fetch("/api/demo/decision/recalculate", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(input),
    });
    if (!response.ok) {
      throw new DecisionRecalculationError();
    }
    return (await response.json()) as RecalculatedDecision;
  } catch {
    throw new DecisionRecalculationError();
  }
}
