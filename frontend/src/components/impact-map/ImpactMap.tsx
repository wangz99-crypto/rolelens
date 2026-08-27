import {
  Background,
  BackgroundVariant,
  MarkerType,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { scenarioStatusLabel } from "../../api/presentation";
import type { DemoDecision, RoleState } from "../../api/types";
import { DecisionNode, type DecisionNodeData } from "./DecisionNode";
import { RoleNode, type RoleNodeData } from "./RoleNode";

interface ImpactMapProps {
  data: DemoDecision;
}

const positions: Record<RoleState["role_key"], { x: number; y: number }> = {
  executive: { x: 302, y: 12 },
  data_analyst: { x: 28, y: 164 },
  data_engineer: { x: 70, y: 345 },
  sales_marketing: { x: 575, y: 164 },
  project_manager: { x: 328, y: 360 },
};

const nodeTypes = {
  decision: DecisionNode,
  role: RoleNode,
};

function buildNodes(data: DemoDecision): Node[] {
  const roleNodes: Node<RoleNodeData>[] = data.roles.map((role) => ({
    id: role.role_key,
    type: "role",
    position: positions[role.role_key],
    data: { role },
    draggable: false,
    selectable: false,
  }));
  const decisionNode: Node<DecisionNodeData> = {
    id: "decision",
    type: "decision",
    position: { x: 278, y: 156 },
    data: {
      title: data.decision.title,
      value: `+${data.scenario.net_scenario_value.toLocaleString("en-US")} ${data.scenario.currency}`,
      status: scenarioStatusLabel(data.scenario.status),
    },
    draggable: false,
    selectable: false,
  };
  return [...roleNodes, decisionNode];
}

const edges: Edge[] = [
  ["decision", "executive"],
  ["decision", "data_analyst"],
  ["decision", "data_engineer"],
  ["decision", "sales_marketing"],
  ["decision", "project_manager"],
].map(([source, target]) => ({
  id: `${source}-${target}`,
  source,
  target,
  type: "smoothstep",
  animated: false,
  style: { stroke: "#3c5368", strokeWidth: 1.3 },
  markerEnd: { type: MarkerType.ArrowClosed, color: "#3c5368", width: 14, height: 14 },
}));

export function ImpactMap({ data }: ImpactMapProps) {
  return (
    <section className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-800 bg-[#0d141e]" aria-labelledby="impact-map-title">
      <div className="flex items-center justify-between border-b border-slate-800 px-5 py-3">
        <div>
          <p className="eyebrow text-slate-500">Organizational view</p>
          <h2 id="impact-map-title" className="mt-1 text-sm font-semibold text-slate-100">Impact Map</h2>
        </div>
        <span className="text-[11px] text-slate-500">Baseline role states</span>
      </div>
      <div className="min-h-0 flex-1" data-testid="impact-map">
        <ReactFlow
          nodes={buildNodes(data)}
          edges={edges}
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
