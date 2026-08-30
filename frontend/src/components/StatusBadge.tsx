import type { ReactNode } from "react";

interface StatusBadgeProps {
  children: ReactNode;
  tone: "evidence" | "positive" | "neutral" | "assumption" | "blocked" | "ai";
}

const tones = {
  evidence: "border-cyan-400/25 bg-cyan-400/10 text-cyan-200",
  positive: "border-emerald-400/25 bg-emerald-400/10 text-emerald-200",
  neutral: "border-slate-700 bg-slate-800/70 text-slate-300",
  assumption: "border-amber-400/25 bg-amber-400/10 text-amber-200",
  blocked: "border-red-400/25 bg-red-400/10 text-red-200",
  ai: "border-violet-400/25 bg-violet-400/10 text-violet-200",
};

export function StatusBadge({ children, tone }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}
