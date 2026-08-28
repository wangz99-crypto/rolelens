import { useState } from "react";
import { GitBranch } from "lucide-react";
import { recalculateDecision } from "../api/client";
import {
  canonicalDecimalString,
  fractionToPercentDisplay,
  percentageStringToFractionString,
} from "../api/decimal";
import {
  scenarioStatusBadgeLabel,
  scenarioStatusTone,
} from "../api/presentation";
import {
  isRecalculatedDecision,
  type Assumption,
  type DemoDecision,
  type ProductDecision,
} from "../api/types";
import { AppSidebar } from "../components/AppSidebar";
import { StatusBadge } from "../components/StatusBadge";
import {
  AssumptionCard,
  type AssumptionDraft,
} from "../components/decision/AssumptionCard";
import { CurrentDecisionBar } from "../components/decision/CurrentDecisionBar";
import { DecisionDiffPanel } from "../components/decision/DecisionDiffPanel";
import { EvidenceFoundationCard } from "../components/decision/EvidenceFoundationCard";
import { ImpactMap } from "../components/impact-map/ImpactMap";

interface DecisionRoomPageProps {
  data: DemoDecision;
}

const SAFE_RECALCULATION_ERROR =
  "Decision impact could not be recalculated safely.";

function valueFor(assumptions: Assumption[], key: string): number {
  const assumption = assumptions.find((item) => item.key === key);
  if (!assumption) {
    throw new Error("Required assumption is unavailable.");
  }
  return assumption.value;
}

function draftFrom(assumptions: Assumption[]): AssumptionDraft {
  return {
    pilot_population: String(valueFor(assumptions, "pilot_population")),
    expected_incremental_lift_pct: fractionToPercentDisplay(
      valueFor(assumptions, "expected_incremental_lift"),
    ),
    cost_per_intervention: String(
      valueFor(assumptions, "cost_per_intervention"),
    ),
    retained_customer_value: String(
      valueFor(assumptions, "retained_customer_value"),
    ),
  };
}

function draftMatches(
  draft: AssumptionDraft,
  assumptions: Assumption[],
): boolean {
  try {
    return (
      Number(draft.pilot_population) ===
        valueFor(assumptions, "pilot_population") &&
      percentageStringToFractionString(
        draft.expected_incremental_lift_pct,
      ) ===
        canonicalDecimalString(
          valueFor(assumptions, "expected_incremental_lift"),
        ) &&
      canonicalDecimalString(draft.cost_per_intervention) ===
        canonicalDecimalString(valueFor(assumptions, "cost_per_intervention")) &&
      canonicalDecimalString(draft.retained_customer_value) ===
        canonicalDecimalString(valueFor(assumptions, "retained_customer_value"))
    );
  } catch {
    return false;
  }
}

export function DecisionRoomPage({ data }: DecisionRoomPageProps) {
  const [trusted, setTrusted] = useState<ProductDecision>(data);
  const [draft, setDraft] = useState<AssumptionDraft>(() =>
    draftFrom(data.assumptions),
  );
  const [isRecalculating, setIsRecalculating] = useState(false);
  const [recalculationError, setRecalculationError] = useState<string | null>(
    null,
  );
  const dirty = !draftMatches(draft, trusted.assumptions);

  function updateDraft(key: keyof AssumptionDraft, value: string) {
    setDraft((current) => ({ ...current, [key]: value }));
    setRecalculationError(null);
  }

  async function recalculate() {
    if (!dirty || isRecalculating) {
      return;
    }
    setIsRecalculating(true);
    setRecalculationError(null);
    try {
      const result = await recalculateDecision({
        pilot_population: Number(draft.pilot_population),
        expected_incremental_lift: percentageStringToFractionString(
          draft.expected_incremental_lift_pct,
        ),
        cost_per_intervention: canonicalDecimalString(
          draft.cost_per_intervention,
        ),
        retained_customer_value: canonicalDecimalString(
          draft.retained_customer_value,
        ),
        currency: "USD",
      });
      setTrusted(result);
      setDraft(draftFrom(result.assumptions));
    } catch {
      setRecalculationError(SAFE_RECALCULATION_ERROR);
    } finally {
      setIsRecalculating(false);
    }
  }

  const scenarioTone = scenarioStatusTone(trusted.scenario.status);

  return (
    <div className="flex h-screen overflow-hidden bg-graphite">
      <AppSidebar activeLabel="Decisions" />
      <main className="grid min-w-0 flex-1 grid-rows-[auto_minmax(0,1fr)_auto] gap-3 overflow-hidden px-6 py-4">
        <header className="flex items-start justify-between gap-8">
          <div className="min-w-0">
            <p className="eyebrow text-cyan-300">Decision Room</p>
            <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-white">
              {trusted.decision.title}
            </h1>
            <p
              className="mt-1 max-w-[760px] truncate text-sm text-slate-400"
              title={trusted.decision.business_question}
            >
              {trusted.decision.business_question}
            </p>
            <div className="mt-2.5 flex gap-2">
              <StatusBadge tone="evidence">Evidence locked</StatusBadge>
              <StatusBadge tone={scenarioTone}>
                {scenarioStatusBadgeLabel(trusted.scenario.status)}
              </StatusBadge>
              <StatusBadge tone="neutral">AI Brief not generated</StatusBadge>
            </div>
          </div>
          <div className="mt-1 flex shrink-0 items-center gap-2 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2 text-xs font-semibold tracking-[0.08em] text-slate-300">
            <GitBranch size={15} className="text-slate-500" aria-hidden="true" />
            {trusted.revision.revision_id.toUpperCase()} ·{" "}
            {trusted.revision.label.toUpperCase()}
          </div>
        </header>
        <div className="grid min-h-0 grid-cols-[minmax(0,1fr)_304px] gap-4">
          <ImpactMap data={trusted} />
          <aside className="flex min-h-0 flex-col gap-3 overflow-hidden">
            <AssumptionCard
              draft={draft}
              dirty={dirty}
              isRecalculating={isRecalculating}
              error={recalculationError}
              onChange={updateDraft}
              onRecalculate={recalculate}
            />
            <EvidenceFoundationCard evidence={trusted.evidence} />
          </aside>
        </div>
        {isRecalculatedDecision(trusted) && trusted.diff.kind !== "no_change" ? (
          <DecisionDiffPanel data={trusted} />
        ) : (
          <CurrentDecisionBar scenario={trusted.scenario} />
        )}
      </main>
    </div>
  );
}
