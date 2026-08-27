import { Handle, Position, type NodeProps } from "@xyflow/react";
import { BarChart3, BriefcaseBusiness, Database, Megaphone, Users } from "lucide-react";
import type { RoleState } from "../../api/types";

export interface RoleNodeData extends Record<string, unknown> {
  role: RoleState;
}

const icons = {
  executive: BriefcaseBusiness,
  data_analyst: BarChart3,
  data_engineer: Database,
  sales_marketing: Megaphone,
  project_manager: Users,
};

export function RoleNode({ data }: NodeProps) {
  const role = (data as RoleNodeData).role;
  const Icon = icons[role.role_key];
  const foundation = role.state_kind === "foundation";
  return (
    <div
      data-testid={`role-node-${role.role_key}`}
      className={`w-[188px] rounded-xl border px-4 py-3 ${
        foundation
          ? "border-cyan-400/30 bg-[#10202b]"
          : "border-slate-600/80 bg-[#151e2b]"
      }`}
    >
      <Handle type="target" position={Position.Top} className="!border-0 !bg-transparent" />
      <Handle type="target" position={Position.Left} className="!border-0 !bg-transparent" />
      <div className="flex items-center gap-2">
        <span className={`grid size-7 place-items-center rounded-lg ${foundation ? "bg-cyan-400/10 text-cyan-300" : "bg-slate-700/60 text-slate-300"}`}>
          <Icon size={14} aria-hidden="true" />
        </span>
        <span className="text-xs font-semibold text-slate-100">{role.label}</span>
      </div>
      <p className={`mt-2 text-[11px] leading-4 ${foundation ? "text-cyan-200/80" : "text-slate-400"}`}>
        {role.baseline_state}
      </p>
      <Handle type="source" position={Position.Right} className="!border-0 !bg-transparent" />
      <Handle type="source" position={Position.Bottom} className="!border-0 !bg-transparent" />
    </div>
  );
}
