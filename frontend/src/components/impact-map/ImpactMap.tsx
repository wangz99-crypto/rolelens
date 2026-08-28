import {
  Background,
  BackgroundVariant,
  MarkerType,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { formatSignedCurrency, scenarioStatusLabel } from "../../api/presentation";
import {
  isRecalculatedDecision,
  type ImpactKind,
  type ProductDecision,
  type RoleKey,
} from "../../api/types";
import { DecisionNode, type DecisionNodeData } from "./DecisionNode";
import { RoleNode, type RenderableRoleState, type RoleNodeData } from "./RoleNode";

interface ImpactMapProps {
  data: ProductDecision;
  onRoleSelect: (roleKey: RoleKey) => void;
}

const positions: Record<RoleKey, { x: number; y: number }> = {
  executive: { x: 302, y: 12 },
  data_analyst: { x: 28, y: 164 },
  data_engineer: { x: 70, y: 345 },
  sales_marketing: { x: 575, y: 164 },
  project_manager: { x: 328, y: 360 },
};

const edgeColors: Record<ImpactKind, string> = {
  current: "#3c5368",
  unchanged: "#367b8f",
  recomputed: "#b4862d",
  changed: "#c96d32",
  blocked: "#b9474d",
};

const nodeTypes = { decision: DecisionNode, role: RoleNode };

function renderableRoles(data: ProductDecision): RenderableRoleState[] {
  if (isRecalculatedDecision(data)) {
    return data.roles.map((role) => ({
      roleKey: role.role_key,
      label: role.label,
      state: role.state,
      impactKind: role.impact_kind,
      foundation: role.role_key === "data_analyst" || role.role_key === "data_engineer",
    }));
  }
  return data.roles.map((role) => ({
    roleKey: role.role_key,
    label: role.label,
    state: role.baseline_state,
    impactKind: "current",
    foundation: role.state_kind === "foundation",
  }));
}

function buildNodes(
  data: ProductDecision,
  roles: RenderableRoleState[],
  onRoleSelect: (roleKey: RoleKey) => void,
): Node[] {
  const roleNodes: Node<RoleNodeData>[] = roles.map((role) => ({
    id: role.roleKey,
    type: "role",
    position: positions[role.roleKey],
    data: { role, onOpen: onRoleSelect },
    draggable: false,
    selectable: false,
  }));
  const decisionNode: Node<DecisionNodeData> = {
    id: "decision",
    type: "decision",
    position: { x: 278, y: 156 },
    data: {
      title: data.decision.title,
      value: formatSignedCurrency(data.scenario.net_scenario_value, data.scenario.currency),
      statusLabel: scenarioStatusLabel(data.scenario.status),
      scenarioStatus: data.scenario.status,
    },
    draggable: false,
    selectable: false,
  };
  return [...roleNodes, decisionNode];
}

function buildEdges(roles: RenderableRoleState[]): Edge[] {
  return roles.map((role) => {
    const color = edgeColors[role.impactKind];
    return {
      id: `decision-${role.roleKey}`,
      source: "decision",
      target: role.roleKey,
      type: "smoothstep",
      animated: false,
      style: { stroke: color, strokeWidth: role.impactKind === "current" ? 1.3 : 1.7 },
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 14, height: 14 },
    };
  });
}

export function ImpactMap({ data, onRoleSelect }: ImpactMapProps) {
  const roles = renderableRoles(data);
  return (
    <section className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-800 bg-[#0d141e]" aria-labelledby="impact-map-title">
      <div className="flex items-center justify-between border-b border-slate-800 px-5 py-3">
        <div>
          <p className="eyebrow text-slate-500">Organizational view</p>
          <h2 id="impact-map-title" className="mt-1 text-sm font-semibold text-slate-100">Impact Map</h2>
        </div>
        <span className="text-[11px] text-slate-500">{isRecalculatedDecision(data) ? "Revision impact projection" : "Baseline role states"}</span>
      </div>
      <div className="min-h-0 flex-1" data-testid="impact-map">
        <ReactFlow
          nodes={buildNodes(data, roles, onRoleSelect)}
          edges={buildEdges(roles)}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.12, maxZoom: 1 }}
          minZoom={0.6}
          maxZoom={1}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          panOnDrag={false}
          zoomOnScroll={false}
          zoomOnPinch={false}
          zoomOnDoubleClick={false}
          preventScrolling={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#223043" />
        </ReactFlow>
      </div>
    </section>
  );
}
