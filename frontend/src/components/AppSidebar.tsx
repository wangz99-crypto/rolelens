import { Database, LayoutDashboard } from "lucide-react";
import { BrandMark } from "./brand/BrandMark";

interface AppSidebarProps {
  activeLabel: "Decisions";
}

export function AppSidebar({ activeLabel }: AppSidebarProps) {
  return (
    <aside className="flex h-screen w-[232px] shrink-0 flex-col border-r border-slate-800 bg-[#0b111a] px-4 py-5">
      <div className="px-2">
        <BrandMark />
      </div>
      <nav aria-label="Primary" className="mt-10">
        <div className="flex items-center gap-3 rounded-lg border border-cyan-400/15 bg-cyan-400/[0.07] px-3 py-2.5 text-sm font-medium text-cyan-100">
          <LayoutDashboard size={17} aria-hidden="true" />
          {activeLabel}
        </div>
      </nav>
      <div className="mt-auto rounded-xl border border-slate-800 bg-slate-900/60 p-3.5">
        <div className="mb-2 flex items-center gap-2 text-cyan-300">
          <Database size={15} aria-hidden="true" />
          <span className="text-[10px] font-semibold uppercase tracking-[0.16em]">
            Dataset context
          </span>
        </div>
        <p className="text-sm font-medium text-slate-200">IBM Telco</p>
        <p className="mt-0.5 text-xs text-slate-500">Demo dataset</p>
      </div>
    </aside>
  );
}
