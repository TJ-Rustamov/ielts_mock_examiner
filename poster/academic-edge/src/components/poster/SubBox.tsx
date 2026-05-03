import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface SubBoxProps {
  title: string;
  icon: LucideIcon;
  children: ReactNode;
  className?: string;
}

export function SubBox({ title, icon: Icon, children, className }: SubBoxProps) {
  return (
    <div
      className={cn(
        "relative rounded-xl border-2 border-slate-200 bg-gradient-to-br from-white to-muted/40 shadow-sm",
        "p-2 flex flex-col",
        "transition-all duration-300 hover:border-teal/40 hover:shadow-sm",
        className,
      )}
    >
      <div className="flex items-center gap-2 mb-1 shrink-0">
        <span className="flex h-5 w-5 items-center justify-center rounded-md bg-navy text-white">
          <Icon className="h-2.5 w-2.5" strokeWidth={2.4} />
        </span>
        <h3 className="text-[11px] font-bold uppercase tracking-[0.16em] text-navy">
          {title}
        </h3>
        <span className="flex-1 h-px bg-gradient-to-r from-teal/30 to-transparent" />
      </div>
      <div className="text-[12px] leading-[1.3] text-foreground/85 flex flex-col justify-center">
        {children}
      </div>
    </div>
  );
}
