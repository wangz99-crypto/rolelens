import type {
  DemoDecision,
  EvidenceDetail,
  RecalculateDecisionInput,
  RecalculatedDecision,
  RoleImpactBriefSetResponse,
} from "./types";

const SAFE_LOAD_ERROR = "RoleLens could not load the demo decision safely.";
const SAFE_RECALCULATION_ERROR =
  "Decision impact could not be recalculated safely.";
const SAFE_EVIDENCE_ERROR = "Evidence details could not be loaded safely.";
const SAFE_ROLE_BRIEF_ERROR =
  "IBM Granite Role Brief could not be generated safely.";

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

export class EvidenceDetailLoadError extends Error {
  constructor() {
    super(SAFE_EVIDENCE_ERROR);
    this.name = "EvidenceDetailLoadError";
  }
}

export class RoleBriefGenerationError extends Error {
  constructor() {
    super(SAFE_ROLE_BRIEF_ERROR);
    this.name = "RoleBriefGenerationError";
  }
}

export async function getDemoDecisionEvidence(): Promise<EvidenceDetail[]> {
  try {
    const response = await fetch("/api/demo/decision/evidence", {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new EvidenceDetailLoadError();
    }
    return (await response.json()) as EvidenceDetail[];
  } catch {
    throw new EvidenceDetailLoadError();
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

export async function generateRoleBriefs(
  input: RecalculateDecisionInput,
): Promise<RoleImpactBriefSetResponse> {
  try {
    const response = await fetch("/api/demo/decision/role-brief", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(input),
    });
    if (!response.ok) {
      throw new RoleBriefGenerationError();
    }
    return (await response.json()) as RoleImpactBriefSetResponse;
  } catch {
    throw new RoleBriefGenerationError();
  }
}
