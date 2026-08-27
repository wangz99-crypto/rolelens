import type { ScenarioStatus } from "./types";

export function scenarioStatusLabel(status: ScenarioStatus): string {
  const labels: Record<ScenarioStatus, string> = {
    CLEARS_BREAK_EVEN: "Clears modeled break-even",
    DOES_NOT_CLEAR_BREAK_EVEN: "Does not clear modeled break-even",
    NOT_EVALUABLE: "Not evaluable",
  };
  return labels[status];
}

export function scenarioStatusBadgeLabel(status: ScenarioStatus): string {
  const labels: Record<ScenarioStatus, string> = {
    CLEARS_BREAK_EVEN: "Scenario clears",
    DOES_NOT_CLEAR_BREAK_EVEN: "Scenario does not clear",
    NOT_EVALUABLE: "Scenario not evaluable",
  };
  return labels[status];
}

export function scenarioStatusShortLabel(status: ScenarioStatus): string {
  const labels: Record<ScenarioStatus, string> = {
    CLEARS_BREAK_EVEN: "CLEARS",
    DOES_NOT_CLEAR_BREAK_EVEN: "DOES NOT CLEAR",
    NOT_EVALUABLE: "NOT EVALUABLE",
  };
  return labels[status];
}
