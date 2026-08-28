import { Handle, Position, type NodeProps } from "@xyflow/react";
import { BarChart3, BriefcaseBusiness, Database, Megaphone, Users } from "lucide-react";
import type { ImpactKind, RoleKey } from "../../api/types";

export interface RenderableRoleState {
  roleKey: RoleKey;
  label: string;
  state: string;
  impactKind: ImpactKind;
  foundation: boolean;
}

export interface RoleNodeData extends Record<string, unknown> {
  role: RenderableRoleState;
  onOpen: (roleKey: RoleKey) => void;
}

const icons = {
  executive: BriefcaseBusiness,
  data_analyst: BarChart3,
  data_engineer: Database,
  sales_marketing: Megaphone,
  project_manager: Users,
};

const tones: Record<ImpactKind, string> = {
  current: "border-slate-600/80 bg-[#151e2b]",
  unchanged: "border-cyan-400/35 bg-[#10202b]",
  recomputed: "border-amber-400/45 bg-[#292316]",
  changed: "border-orange-400/55 bg-[#2a1d17]",
  blocked: "border-red-400/60 bg-[#2a171c]",
};

const badgeTones: Record<ImpactKind, string> = {
  current: "bg-slate-700/60 text-slate-400",
  unchanged: "bg-cyan-400/10 text-cyan-200",
  recomputed: "bg-amber-400/10 text-amber-200",
  changed: "bg-orange-400/10 text-orange-200",
  blocked: "bg-red-400/10 text-red-200",
};

export function RoleNode({ data }: NodeProps) {
  const { role, onOpen } = data as RoleNodeData;
  const Icon = icons[role.roleKey];
  const baselineFoundationTone = role.foundation && role.impactKind === "current"
    ? "border-cyan-400/30 bg-[#10202b]"
    : tones[role.impactKind];
  return (
    <div className={`w-[188px] rounded-xl border transition-colors duration-300 ${baselineFoundationTone}`}>
      <Handle type="target" position={Position.Top} className="!border-0 !bg-transparent" />
      <Handle type="target" position={Position.Left} className="!border-0 !bg-transparent" />
      <button
        type="button"
        data-testid={`role-node-${role.roleKey}`}
        aria-label={`Open ${role.label} Role Lens`}
        onClick={() => onOpen(role.roleKey)}
        style={{ pointerEvents: "auto" }}
        className="nodrag nopan pointer-events-auto block w-full rounded-xl px-4 py-3 text-left outline-none transition hover:bg-white/[0.025] focus-visible:ring-2 focus-visible:ring-cyan-300/70"
      >
        <span className="flex items-center gap-2">
          <span className="grid size-7 place-items-center rounded-lg bg-slate-700/40 text-slate-300">
            <Icon size={14} aria-hidden="true" />
          </span>
          <span className="min-w-0 flex-1 text-xs font-semibold text-slate-100">{role.label}</span>
          <span className={`rounded px-1.5 py-0.5 text-[8px] font-bold tracking-[0.1em] ${badgeTones[role.impactKind]}`}>
            {role.impactKind.toUpperCase()}
          </span>
        </span>
        <span className="mt-2 block text-[11px] leading-4 text-slate-300/80">{role.state}</span>
      </button>
      <Handle type="source" position={Position.Right} className="!border-0 !bg-transparent" />
      <Handle type="source" position={Position.Bottom} className="!border-0 !bg-transparent" />
    </div>
  );
}
