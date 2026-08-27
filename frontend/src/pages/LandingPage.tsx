import { ArrowRight, CheckCircle2, Database, ShieldCheck } from "lucide-react";
import { BrandMark } from "../components/brand/BrandMark";

interface LandingPageProps {
  onOpenWorkspace: () => void;
}

export function LandingPage({ onOpenWorkspace }: LandingPageProps) {
  return (
    <main className="relative grid min-h-screen grid-cols-[minmax(520px,0.92fr)_minmax(620px,1.08fr)] overflow-hidden bg-graphite">
      <div className="relative z-10 flex flex-col px-[clamp(48px,7vw,112px)] py-10">
        <BrandMark />
        <div className="my-auto max-w-[610px] py-16">
          <p className="eyebrow text-cyan-300">Role-aware decision change workspace</p>
          <h1 className="mt-5 text-[clamp(48px,5.2vw,76px)] font-semibold leading-[1.02] tracking-[-0.045em] text-white">
            Know what must change when the decision changes.
          </h1>
          <p className="mt-7 max-w-[570px] text-lg leading-8 text-slate-400">
            Track how changing business assumptions affects team decisions — while keeping the underlying evidence intact.
          </p>
          <button
            type="button"
            onClick={onOpenWorkspace}
            className="mt-9 inline-flex items-center gap-3 rounded-lg bg-cyan-300 px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-200"
          >
            Open Demo Workspace
            <ArrowRight size={17} aria-hidden="true" />
          </button>
          <p className="mt-5 text-xs text-slate-500">
            Fictional IBM Telco sample · Governed evidence · IBM Granite-ready
          </p>
        </div>
        <p className="text-[11px] uppercase tracking-[0.18em] text-slate-700">Decision Signal System</p>
      </div>
      <div className="relative grid place-items-center border-l border-slate-800 bg-[#0b121c] p-12">
        <LandingMap />
      </div>
    </main>
  );
}

function LandingMap() {
  return (
    <div className="relative h-[620px] w-full max-w-[690px]" aria-label="Simplified Impact Map illustration">
      <div className="absolute inset-0 landing-grid opacity-40" />
      <svg className="absolute inset-0 h-full w-full" aria-hidden="true">
        <g stroke="#304559" strokeWidth="1.5" fill="none">
          <path d="M345 310 L345 96" />
          <path d="M345 310 L110 245" />
          <path d="M345 310 L584 245" />
          <path d="M345 310 L345 515" />
          <path d="M345 310 L112 474" />
        </g>
      </svg>
      <IllustrationNode className="left-1/2 top-8 -translate-x-1/2" label="Executive" icon={<ShieldCheck size={16} />} />
      <IllustrationNode className="left-3 top-[205px]" label="Analyst" icon={<CheckCircle2 size={16} />} foundation />
      <IllustrationNode className="right-2 top-[205px]" label="Sales" icon={<ArrowRight size={16} />} />
      <IllustrationNode className="bottom-10 left-1/2 -translate-x-1/2" label="Project Manager" icon={<CheckCircle2 size={16} />} />
      <IllustrationNode className="bottom-[75px] left-4" label="Data Engineer" icon={<Database size={16} />} foundation />
      <div className="absolute left-1/2 top-1/2 w-[230px] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-cyan-300/60 bg-[#122535] p-5 shadow-2xl shadow-black/40">
        <p className="eyebrow text-cyan-300">Decision</p>
        <p className="mt-3 text-sm font-semibold uppercase tracking-wide text-white">Customer Retention Pilot</p>
        <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-slate-800">
          <div className="h-full w-2/3 rounded-full bg-cyan-300" />
        </div>
        <p className="mt-3 text-xs text-slate-500">Impact map</p>
      </div>
    </div>
  );
}

function IllustrationNode({ className, label, icon, foundation = false }: { className: string; label: string; icon: React.ReactNode; foundation?: boolean }) {
  return (
    <div className={`absolute flex w-[180px] items-center gap-3 rounded-xl border px-4 py-3 ${foundation ? "border-cyan-400/25 bg-cyan-400/[0.06]" : "border-slate-700 bg-slate-900"} ${className}`}>
      <span className={foundation ? "text-cyan-300" : "text-slate-400"}>{icon}</span>
      <span className="text-xs font-medium text-slate-300">{label}</span>
    </div>
  );
}
