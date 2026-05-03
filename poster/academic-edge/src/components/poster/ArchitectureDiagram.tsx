import { ArrowRight, Layout, Server, Cpu, Database } from "lucide-react";

const nodes = [
  { icon: Layout, label: "Frontend", sub: "React · Vite", tone: "teal" as const },
  { icon: Server, label: "Backend", sub: "Django Channels", tone: "navy" as const },
  { icon: Cpu, label: "AI Services", sub: "Gemini · STT · TTS", tone: "orange" as const },
  { icon: Database, label: "Database", sub: "Postgres · Redis", tone: "navy" as const },
];

const toneStyles: Record<string, string> = {
  teal: "from-teal/15 to-teal-soft border-teal/30 text-navy",
  navy: "from-navy/10 to-navy/5 border-navy/30 text-navy",
  orange: "from-orange/15 to-orange-soft border-orange/40 text-navy",
};

export function ArchitectureDiagram() {
  return (
    <div className="grid grid-cols-2 gap-1 w-full">
      {nodes.map((n, i) => (
        <div key={n.label} className="flex items-center gap-1 flex-1 min-w-0">
          <div
            className={`relative flex-1 rounded-md border bg-gradient-to-br p-1 shadow-sm ${toneStyles[n.tone]}`}
          >
            <n.icon className="h-3 w-3 mb-0.5 opacity-80" strokeWidth={2} />
            <p className="font-display font-semibold text-[12px] leading-none truncate">{n.label}</p>
            <p className="text-[10px] opacity-70 mt-0.5 truncate">{n.sub}</p>
          </div>
          {i === 0 && (
            <ArrowRight className="h-2.5 w-2.5 text-muted-foreground shrink-0 opacity-50" />
          )}
          {i === 2 && (
            <ArrowRight className="h-2.5 w-2.5 text-muted-foreground shrink-0 opacity-50" />
          )}
        </div>
      ))}
    </div>
  );
}
