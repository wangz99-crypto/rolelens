import type { ScenarioStatus } from "./types";

export type ScenarioTone = "positive" | "blocked" | "neutral";

export function scenarioStatusTone(status: ScenarioStatus): ScenarioTone {
  const tones: Record<ScenarioStatus, ScenarioTone> = {
    CLEARS_BREAK_EVEN: "positive",
    DOES_NOT_CLEAR_BREAK_EVEN: "blocked",
    NOT_EVALUABLE: "neutral",
  };
  return tones[status];
}

export function formatSignedCurrency(value: number, currency: string): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString("en-US")} ${currency}`;
}

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

export function scenarioStatusCompactLabel(status: ScenarioStatus): string {
  const labels: Record<ScenarioStatus, string> = {
    CLEARS_BREAK_EVEN: "Clears",
    DOES_NOT_CLEAR_BREAK_EVEN: "Does not clear",
    NOT_EVALUABLE: "Not evaluable",
  };
  return labels[status];
}
