import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Target } from "lucide-react";
import type { ScenarioStatus } from "../../api/types";

export interface DecisionNodeData extends Record<string, unknown> {
  title: string;
  value: string;
  statusLabel: string;
  scenarioStatus: ScenarioStatus;
}

export function DecisionNode({ data }: NodeProps) {
  const content = data as DecisionNodeData;
  const tones: Record<ScenarioStatus, { node: string; status: string }> = {
    CLEARS_BREAK_EVEN: {
      node: "border-cyan-300/60 bg-[#122535]",
      status: "text-emerald-300",
    },
    DOES_NOT_CLEAR_BREAK_EVEN: {
      node: "border-red-400/60 bg-[#2a171c]",
      status: "text-red-300",
    },
    NOT_EVALUABLE: {
      node: "border-amber-300/50 bg-[#292318]",
      status: "text-amber-200",
    },
  };
  const tone = tones[content.scenarioStatus];
  return (
    <div className={`w-[236px] rounded-2xl border px-5 py-4 shadow-[0_18px_45px_rgba(0,0,0,0.35)] transition-colors duration-300 ${tone.node}`}>
      <Handle type="target" position={Position.Top} className="!border-0 !bg-transparent" />
      <Handle type="target" position={Position.Left} className="!border-0 !bg-transparent" />
      <Handle type="target" position={Position.Right} className="!border-0 !bg-transparent" />
      <div className="flex items-center gap-2 text-cyan-300">
        <Target size={15} aria-hidden="true" />
        <span className="text-[9px] font-semibold uppercase tracking-[0.2em]">Decision</span>
      </div>
      <p className="mt-3 text-[11px] font-semibold uppercase tracking-[0.09em] text-white">{content.title}</p>
      <p className="mt-2 text-2xl font-semibold tabular-nums text-white">{content.value}</p>
      <p className={`mt-1 text-[11px] ${tone.status}`}>{content.statusLabel}</p>
      <Handle type="source" position={Position.Bottom} className="!border-0 !bg-transparent" />
    </div>
  );
}
