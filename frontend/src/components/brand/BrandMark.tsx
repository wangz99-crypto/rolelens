import { Aperture } from "lucide-react";

interface BrandMarkProps {
  compact?: boolean;
}

export function BrandMark({ compact = false }: BrandMarkProps) {
  return (
    <div className="flex items-center gap-3" aria-label="RoleLens">
      <span className="grid size-9 place-items-center rounded-lg border border-cyan-400/35 bg-cyan-400/10 text-cyan-300">
        <Aperture size={19} strokeWidth={1.8} aria-hidden="true" />
      </span>
      {!compact && (
        <span className="text-sm font-semibold tracking-[0.22em] text-slate-100">
          ROLELENS
        </span>
      )}
    </div>
  );
}
