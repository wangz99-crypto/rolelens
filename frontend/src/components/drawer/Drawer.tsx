import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

interface DrawerProps {
  labelledBy: string;
  onClose: () => void;
  children: ReactNode;
}

export function Drawer({ labelledBy, onClose, children }: DrawerProps) {
  const drawerRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    drawerRef.current?.focus();

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      previousFocus?.focus();
    };
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/55 backdrop-blur-[2px]"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <section
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        tabIndex={-1}
        className="relative h-full w-[min(480px,calc(100vw-24px))] overflow-y-auto border-l border-slate-700 bg-[#0d141e] px-6 py-6 shadow-[-28px_0_70px_rgba(0,0,0,0.5)] outline-none"
      >
        <button
          type="button"
          aria-label="Close drawer"
          onClick={onClose}
          className="absolute right-5 top-5 grid size-9 place-items-center rounded-lg border border-slate-700 bg-slate-900 text-slate-300 transition hover:border-slate-500 hover:text-white focus-visible:ring-2 focus-visible:ring-cyan-300/70"
        >
          <X size={17} aria-hidden="true" />
        </button>
        {children}
      </section>
    </div>
  );
}
