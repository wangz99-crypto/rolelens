import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Target } from "lucide-react";

export interface DecisionNodeData extends Record<string, unknown> {
  title: string;
  value: string;
  status: string;
}

export function DecisionNode({ data }: NodeProps) {
  const content = data as DecisionNodeData;
  return (
    <div className="w-[236px] rounded-2xl border border-cyan-300/60 bg-[#122535] px-5 py-4 shadow-[0_18px_45px_rgba(0,0,0,0.35)]">
      <Handle type="target" position={Position.Top} className="!border-0 !bg-transparent" />
      <Handle type="target" position={Position.Left} className="!border-0 !bg-transparent" />
      <Handle type="target" position={Position.Right} className="!border-0 !bg-transparent" />
      <div className="flex items-center gap-2 text-cyan-300">
        <Target size={15} aria-hidden="true" />
        <span className="text-[9px] font-semibold uppercase tracking-[0.2em]">Decision</span>
      </div>
      <p className="mt-3 text-[11px] font-semibold uppercase tracking-[0.09em] text-white">
        {content.title}
      </p>
      <p className="mt-2 text-2xl font-semibold tabular-nums text-white">{content.value}</p>
      <p className="mt-1 text-[11px] text-emerald-300">{content.status}</p>
      <Handle type="source" position={Position.Bottom} className="!border-0 !bg-transparent" />
    </div>
  );
}
