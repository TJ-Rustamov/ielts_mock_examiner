import logo from "@/assets/logo.png";

export function PosterHeader() {
  return (
    <header className="relative overflow-hidden rounded-2xl bg-header-gradient shadow-header shrink-0">
      <div className="absolute inset-0 grid-pattern opacity-40" />
      <div className="absolute -top-24 -right-24 h-72 w-72 rounded-full bg-orange/30 blur-3xl" />
      <div className="absolute -bottom-24 -left-24 h-72 w-72 rounded-full bg-teal/30 blur-3xl" />

      <div className="relative flex items-center justify-between gap-4 px-6 sm:px-10 py-5">
        {/* Left: Logo + university */}
        <div className="flex flex-1 items-center gap-4 shrink-0">
          <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-white/10 ring-1 ring-white/20 backdrop-blur-sm p-1">
            <img src={logo} alt="IELTS Mock Examiner logo" className="h-full w-full object-contain" />
          </div>
          <div className="text-white hidden sm:block">
            <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-teal-soft">
              Central Asian University
            </p>
            <p className="text-[10px] font-medium uppercase tracking-[0.22em] text-white/70">
              Engineering School
            </p>
          </div>
        </div>

        {/* Center: Title */}
        <div className="text-center text-white shrink-0">
          <h1 className="font-display text-2xl sm:text-3xl lg:text-4xl font-bold leading-[1.05] tracking-tight">
            IELTS Mock Examiner
          </h1>
          <div className="mx-auto mt-2 h-[3px] w-32 bg-accent-gradient rounded-full" />
          <p className="mt-2 text-[11px] sm:text-sm text-white/85 font-light">
            AI-Assisted IELTS Writing and Speaking Practice Platform
          </p>
        </div>

        {/* Right: Team & Supervisor */}
        <div className="text-right text-white flex-1 hidden sm:flex flex-col gap-3 items-end">
          <div className="space-y-0.5">
            <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-orange-soft mb-1">
              Capstone Team
            </p>
            <p className="text-[13px] font-medium">A. Khasakhojaev (220263)</p>
            <p className="text-[13px] font-medium">J. Rustamov (220237)</p>
            <p className="text-[10px] text-white/70 pt-0.5">BSc in Computer Science</p>
          </div>
          <div className="space-y-0.5">
            <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-orange-soft mb-1">
              Supervisor
            </p>
            <p className="text-[13px] font-medium">Eugene Castro</p>
          </div>
        </div>
      </div>

      <div className="relative h-1 w-full bg-accent-gradient" />
    </header>
  );
}
