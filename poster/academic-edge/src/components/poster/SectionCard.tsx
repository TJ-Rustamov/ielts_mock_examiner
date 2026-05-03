import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";
import type { ReactNode, CSSProperties } from "react";

interface SectionCardProps {
  title: string;
  icon: LucideIcon;
  children: ReactNode;
  delay?: number;
  className?: string;
}

export function SectionCard({ title, icon: Icon, children, delay = 0, className }: SectionCardProps) {
  return (
    <article
      className={cn(
        "group animate-fade-up rounded-2xl bg-card shadow-md overflow-hidden border-2 border-slate-300",
        "transition-all duration-300 hover:-translate-y-1 hover:shadow-card-hover",
        "flex flex-col min-h-0",
        className,
      )}
      style={{ animationDelay: `${delay}ms` } as CSSProperties}
    >
      <header className="relative bg-header-gradient px-3 py-2 flex items-center gap-3 shrink-0">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-white/10 ring-1 ring-white/20 backdrop-blur-sm">
          <Icon className="h-4 w-4 text-white" strokeWidth={2.25} />
        </span>
        <h2 className="text-[14px] font-semibold uppercase tracking-[0.18em] text-white">
          {title}
        </h2>
        <span className="absolute bottom-0 left-0 h-px w-full bg-accent-gradient opacity-80" />
      </header>
      <div className="p-2 text-[14px] leading-relaxed text-foreground/85 flex-1 min-h-0 overflow-hidden flex flex-col">
        {children}
      </div>
    </article>
  );
}
