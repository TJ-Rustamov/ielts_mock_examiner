import { Mic, PenLine, BarChart3, LayoutDashboard } from "lucide-react";
import dashboardImg from "@/assets/dashboard.png";
import writingProcessImg from "@/assets/writing_process.png";
import writingEvalImg from "@/assets/writing evaluation.png";
import speakingProcessImg from "@/assets/speaking_rpocess.png";
import speakingEvalImg from "@/assets/speaking_evaluation.png";
import adminImg from "@/assets/admin.png";

const screens = [
  { icon: BarChart3, name: "Admin", img: adminImg },
  { icon: LayoutDashboard, name: "Dashboard", img: dashboardImg },
  { icon: Mic, name: "Speaking Test",  img: speakingProcessImg },
  { icon: PenLine, name: "Writing Task", img: writingProcessImg },
  { icon: Mic, name: "Speaking Eval",  img: speakingEvalImg },
  { icon: PenLine, name: "Writing Eval", img: writingEvalImg },
];

export function OutputGallery() {
  return (
    <div className="grid grid-cols-2 gap-2 h-full">
      {screens.map((s) => (
        <div
          key={s.name}
          className="group relative flex flex-col overflow-hidden rounded-xl border border-border bg-white shadow-sm transition hover:-translate-y-0.5 hover:shadow-card h-full min-h-0"
        >
          {/* Just the image taking up maximum space without outer padding */}
          <div className="relative flex-1 bg-white overflow-hidden min-h-0 flex justify-center items-start">
            <s.icon className="w-10 h-10 text-muted-foreground/30 absolute inset-0 m-auto" />
            <img 
              src={s.img} 
              alt={s.name} 
              className="w-full h-full object-contain object-top relative z-10"
            />
          </div>
          
          {/* Label section overlaid */}
          <div className="absolute bottom-2 left-2 z-20 bg-white/95 backdrop-blur-md px-2.5 py-1 rounded shadow-md border border-white/20 flex items-center gap-2">
            <p className="text-[10px] font-bold text-navy uppercase tracking-wide">{s.name}</p>
            <span className="w-1 h-1 rounded-full bg-orange" />
            <p className="text-[9px] font-medium text-muted-foreground">{s.note}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
