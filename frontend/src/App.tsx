import { useState } from "react";
import { getDemoDecision } from "./api/client";
import type { DemoDecision } from "./api/types";
import { AppSidebar } from "./components/AppSidebar";
import { DecisionHomePage } from "./pages/DecisionHomePage";
import { DecisionRoomPage } from "./pages/DecisionRoomPage";
import { LandingPage } from "./pages/LandingPage";

type Screen = "landing" | "decisions" | "decision-room";
type LoadState = "idle" | "loading" | "loaded" | "error";

export default function App() {
  const [screen, setScreen] = useState<Screen>("landing");
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [decision, setDecision] = useState<DemoDecision | null>(null);

  async function openWorkspace() {
    setScreen("decisions");
    setLoadState("loading");
    try {
      const loadedDecision = await getDemoDecision();
      setDecision(loadedDecision);
      setLoadState("loaded");
    } catch {
      setLoadState("error");
    }
  }

  if (screen === "landing") {
    return <LandingPage onOpenWorkspace={openWorkspace} />;
  }
  if (loadState === "loading") {
    return <WorkspaceState mode="loading" />;
  }
  if (loadState === "error" || !decision) {
    return <WorkspaceState mode="error" />;
  }
  if (screen === "decision-room") {
    return <DecisionRoomPage data={decision} />;
  }
  return (
    <DecisionHomePage
      data={decision}
      onOpenDecision={() => setScreen("decision-room")}
    />
  );
}

function WorkspaceState({ mode }: { mode: "loading" | "error" }) {
  return (
    <div className="flex h-screen overflow-hidden bg-graphite">
      <AppSidebar activeLabel="Decisions" />
      <main className="grid flex-1 place-items-center px-8">
        {mode === "loading" ? (
          <div role="status" className="text-center">
            <div className="mx-auto size-8 animate-spin rounded-full border-2 border-slate-700 border-t-cyan-300" />
            <p className="mt-4 text-sm text-slate-400">Loading governed decision…</p>
          </div>
        ) : (
          <div role="alert" className="max-w-md rounded-xl border border-red-400/20 bg-red-400/[0.06] p-5 text-sm text-red-100">
            RoleLens could not load the demo decision safely.
          </div>
        )}
      </main>
    </div>
  );
}
