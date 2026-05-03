import { createFileRoute } from "@tanstack/react-router";
import {
  Info,
  Target,
  Settings,
  Network,
  MonitorSmartphone,
  BarChart3,
  CheckCircle2,
  Sparkles,
  Heart,
  Mail,
  BookOpen,
  Layers,
} from "lucide-react";
import { PosterHeader } from "@/components/poster/PosterHeader";
import { SectionCard } from "@/components/poster/SectionCard";
import { SubBox } from "@/components/poster/SubBox";
import { ArchitectureDiagram } from "@/components/poster/ArchitectureDiagram";
import { OutputGallery } from "@/components/poster/OutputGallery";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "IELTS Mock Examiner — AI-Assisted Writing & Speaking Practice" },
      {
        name: "description",
        content:
          "Capstone research poster for IELTS Mock Examiner — an AI-assisted IELTS writing and speaking practice platform built at Central Asian University Engineering School.",
      },
      { property: "og:title", content: "IELTS Mock Examiner — Capstone Poster" },
      {
        property: "og:description",
        content:
          "AI-assisted IELTS writing and speaking practice platform — Central Asian University Engineering School BSc Computer Science Capstone.",
      },
      { property: "og:type", content: "website" },
    ],
  }),
  component: PosterPage,
});

function Bullet({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex gap-2 items-start">
      <span className="mt-[6px] h-1 w-1 shrink-0 rounded-full bg-accent-gradient" />
      <span>{children}</span>
    </li>
  );
}

function NumberedRow({ n, title, body }: { n: string; title: string; body: string }) {
  return (
    <li className="flex gap-2 items-start">
      <span className="font-display text-[15px] font-bold leading-none bg-clip-text text-transparent bg-gradient-to-br from-teal to-orange w-5 shrink-0 mt-0.5">
        {n}
      </span>
      <div className="min-w-0">
        <p className="font-semibold text-navy text-[13px] leading-tight">{title}</p>
        <p className="text-[12px] text-muted-foreground leading-snug">{body}</p>
      </div>
    </li>
  );
}

function PosterPage() {
  return (
    <main className="min-h-screen w-full flex items-center justify-center p-2 sm:p-3 overflow-hidden bg-background">
      {/* 16:9 poster frame — always fits viewport */}
      <div
        className="
          w-full max-w-[min(100vw-1.5rem,calc((100vh-1.5rem)*16/9))]
          aspect-[16/9]
          flex flex-col gap-2
        "
      >
        <PosterHeader />

        {/* 3-column horizontal grid filling remaining space */}
        <section className="grid grid-cols-[1.3fr_3fr_1.3fr] gap-2 flex-1 min-h-0">
          {/* LEFT COLUMN */}
          <div className="flex flex-col gap-2 min-h-0">
            <SectionCard title="Project Foundation" icon={BookOpen} delay={50} className="flex-1 min-h-0">
              <div className="flex flex-col h-full justify-between gap-2 flex-1 min-h-0">
                <SubBox title="Introduction" icon={Info}>
                  <p>
                    IELTS learners need repeated writing and speaking practice, but access to fast and structured feedback is limited. Existing preparation workflows are often fragmented and do not provide one integrated system for both modules.
                  </p>
                  <p className="mt-1">
                    <span className="font-semibold text-navy">IELTS Mock Examiner</span> closes
                    this gap with AI-assisted, examiner-grade feedback in seconds.
                  </p>
                </SubBox>

                <SubBox title="Project Objectives" icon={Target}>
                  <ul className="space-y-1.5">
                    <Bullet>Full-stack React & Django platform for IELTS practice.</Bullet>
                    <Bullet>Writing feedback pipeline with criterion scoring.</Bullet>
                    <Bullet>Real-time Speaking evaluation via WebSockets & AI.</Bullet>
                    <Bullet>Containerized Docker deployment.</Bullet>
                    <Bullet>Low-latency streaming architecture for natural conversation.</Bullet>
                  </ul>
                </SubBox>

                <SubBox title="Methodology" icon={Settings} className="p-1.5">
                  <ol className="grid grid-cols-2 gap-x-3 gap-y-0.5 content-start">
                    <NumberedRow n="01" title="Client–Server" body="React Vite UI & Django API." />
                    <NumberedRow n="02" title="Real-Time" body="WebSockets & Channels." />
                    <NumberedRow n="03" title="AI Pipelines" body="Gemini LLM, STT & TTS." />
                    <NumberedRow n="04" title="Dockerized" body="Containerized deploys." />
                    <NumberedRow n="05" title="Audio Streaming" body="Dynamic VAD endpointing." />
                    <NumberedRow n="06" title="Async Workers" body="Parallel Python TTS queues." />
                  </ol>
                </SubBox>

                <SubBox title="System Architecture" icon={Network} className="p-1.5">
                  <ArchitectureDiagram />
                </SubBox>

                <SubBox title="Tech Stack" icon={Layers} className="flex-1">
                  <ul className="grid grid-cols-2 gap-x-2 gap-y-1 text-[12px]">
                    <Bullet>Python, Django, DRF</Bullet>
                    <Bullet>React, Vite, Tailwind</Bullet>
                    <Bullet>Gemini Integration</Bullet>
                    <Bullet>Faster-Whisper STT</Bullet>
                    <Bullet>Kokoro TTS</Bullet>
                    <Bullet>Docker Compose</Bullet>
                  </ul>
                </SubBox>
              </div>
            </SectionCard>
          </div>

          {/* MIDDLE COLUMN */}
          <div className="flex flex-col gap-2 min-h-0">
            <SectionCard title="Project Output" icon={MonitorSmartphone} delay={150} className="flex-1 min-h-0">
              <div className="h-full min-h-0">
                <OutputGallery />
              </div>
            </SectionCard>
          </div>

          {/* RIGHT COLUMN */}
          <div className="flex flex-col gap-2 min-h-0">
            <SectionCard title="Outcomes & Future Work" icon={Layers} delay={110} className="flex-1 min-h-0">
              <div className="flex flex-col h-full justify-between gap-2 flex-1 min-h-0">
                <SubBox title="Conclusion" icon={CheckCircle2}>
                  <div className="space-y-1.5 text-[13px]">
                    <p>
                      IELTS Mock Examiner shows AI-driven evaluation can deliver examiner-aligned
                      feedback at scale — unifying writing and speaking practice in one accessible
                      workflow.
                    </p>
                    <p>
                      By leveraging asynchronous streaming pipelines and dynamic Voice Activity Detection, 
                      the platform achieves a natural, conversational feel that closely mimics a human examiner.
                    </p>
                  </div>
                </SubBox>

                <SubBox title="Key Features" icon={MonitorSmartphone}>
                  <ul className="space-y-1 text-[13px]">
                    <Bullet>Speaking pipeline with VAD-based segmentation, STT, and TTS.</Bullet>
                    <Bullet>Writing submission and evaluation flow through Gemini-configured AI service.</Bullet>
                    <Bullet>Dedicated frontend pages for dashboard and admin configuration.</Bullet>
                    <Bullet>User authentication and protected practice workflows.</Bullet>
                    <Bullet>An ability to update question bank based on the official IELTS updates</Bullet>
                    <Bullet>Possibility of getting enhanced version of the exact user response</Bullet>
                    <Bullet>Tracking the progress of the user based on test performance</Bullet>

                  </ul>
                </SubBox>

                <SubBox title="Results" icon={BarChart3}>
                  <ul className="grid grid-cols-2 gap-x-2 gap-y-1 text-[13px]">
                    <Bullet>Frontend - backend integration</Bullet>
                    <Bullet>Secure auth & sessions</Bullet>
                    <Bullet>Reliable AI scoring</Bullet>
                    <Bullet>Positive pilot feedback</Bullet>
                    <Bullet>Stable Docker deploys</Bullet>
                    <Bullet>Sub-second response latency</Bullet>
                    <Bullet>Seamless audio sequencing</Bullet>
                    
                  </ul>
                </SubBox>

                <SubBox title="Future Work" icon={Sparkles} className="flex-1">
                  <ul className="space-y-1 text-[13px]">
                    <Bullet>Fine-tuning local LLMs for domain-specific scoring.</Bullet>
                    <Bullet>Multi role system for instructors and students.</Bullet>
                    <Bullet>Mobile-first responsive redesign for broader accessibility.</Bullet>
                  </ul>
                </SubBox>
              </div>
            </SectionCard>
          </div>
        </section>

        {/* Footer */}
        <footer className="text-center shrink-0 -mt-1">
          <p className="text-[8px] uppercase tracking-[0.22em] text-muted-foreground">
            Central Asian University · Engineering School · BSc Computer Science Capstone · 2026
          </p>
        </footer>
      </div>
    </main>
  );
}
