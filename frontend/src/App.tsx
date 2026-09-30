import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import clsx from "clsx";
import {
  AudioLines,
  Boxes,
  FileAudio,
  FolderOpen,
  KeyRound,
  ListChecks,
  Mic2,
  Settings as SettingsIcon,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { APP_NAME } from "./branding";
import { PlayerProvider } from "./components/Player";
import { EmptyState, Spinner, ToastProvider } from "./components/ui";
import { getToken, initToken } from "./lib/api";
import { useJobEvents } from "./lib/events";
import { useJobs, useSettings } from "./lib/queries";
import { useRoute, type Route } from "./lib/router";
import JobsPage from "./pages/JobsPage";
import ModelsPage from "./pages/ModelsPage";
import ProjectsPage from "./pages/ProjectsPage";
import SettingsPage from "./pages/SettingsPage";
import StudioPage from "./pages/StudioPage";
import TranscriptionPage from "./pages/TranscriptionPage";
import VoicesPage from "./pages/VoicesPage";

const NAV: { page: Route["page"]; label: string; icon: ReactNode; href: string }[] = [
  { page: "studio", label: "Studio", icon: <AudioLines className="size-[18px]" />, href: "/studio" },
  { page: "projects", label: "Projects", icon: <FolderOpen className="size-[18px]" />, href: "/projects" },
  { page: "voices", label: "Voices", icon: <Mic2 className="size-[18px]" />, href: "/voices" },
  { page: "transcription", label: "Transcription", icon: <FileAudio className="size-[18px]" />, href: "/transcription" },
  { page: "models", label: "Models", icon: <Boxes className="size-[18px]" />, href: "/models" },
  { page: "jobs", label: "Jobs", icon: <ListChecks className="size-[18px]" />, href: "/jobs" },
  { page: "settings", label: "Settings", icon: <SettingsIcon className="size-[18px]" />, href: "/settings" },
];

const LAST_PROJECT = "hvs.lastProject";

function useTheme(theme: string | undefined) {
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const dark = theme === "dark" || ((theme ?? "system") === "system" && mq.matches);
      document.documentElement.classList.toggle("dark", dark);
    };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);
}

function Shell() {
  const route = useRoute();
  const settings = useSettings();
  useTheme(settings.data?.theme);
  const sse = useJobEvents(true);
  const active = useJobs("&status=queued,loading_model,running,cancelling");
  const activeCount = active.data?.total ?? 0;

  let studioProject: string | null = null;
  if (route.page === "studio") {
    studioProject = route.projectId;
    if (!studioProject) {
      try {
        studioProject = localStorage.getItem(LAST_PROJECT);
      } catch {
        studioProject = null;
      }
    }
  }
  useEffect(() => {
    if (route.page === "studio" && route.projectId) {
      try {
        localStorage.setItem(LAST_PROJECT, route.projectId);
      } catch {
        /* ignore */
      }
    }
  }, [route]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex min-h-0 flex-1">
        <nav aria-label="Main" className="flex w-[216px] shrink-0 flex-col border-r border-line bg-panel">
          <div className="flex h-14 items-center gap-2.5 px-4">
            <div className="flex size-8 items-center justify-center rounded-lg bg-accent text-accent-fg">
              <AudioLines className="size-[18px]" />
            </div>
            <div className="leading-tight">
              <div className="text-[13px] font-semibold">{APP_NAME}</div>
              <div className="text-[11px] text-muted">Local voice production</div>
            </div>
          </div>
          <ul className="flex flex-1 flex-col gap-0.5 px-2 py-2">
            {NAV.map((n) => {
              const on = route.page === n.page;
              const href = n.page === "studio" && studioProject ? `/studio/${studioProject}` : n.href;
              return (
                <li key={n.page}>
                  <a
                    href={`#${href}`}
                    aria-current={on ? "page" : undefined}
                    className={clsx(
                      "flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-sm",
                      on ? "bg-accent-soft font-medium text-accent" : "text-muted hover:bg-panel-2 hover:text-fg",
                    )}
                  >
                    {n.icon}
                    <span className="flex-1">{n.label}</span>
                    {n.page === "jobs" && activeCount > 0 && (
                      <span className="rounded-full bg-accent px-1.5 text-[11px] font-semibold text-accent-fg">
                        {activeCount}
                      </span>
                    )}
                  </a>
                </li>
              );
            })}
          </ul>
          <div className="flex items-center gap-2 border-t border-line px-4 py-3 text-xs text-muted">
            {sse === "error" ? (
              <>
                <WifiOff className="size-3.5 text-danger" /> Live updates reconnecting…
              </>
            ) : (
              <>
                <Wifi className="size-3.5" /> Local only · 127.0.0.1
              </>
            )}
          </div>
        </nav>
        <main className="min-w-0 flex-1 overflow-hidden">
          {route.page === "studio" && <StudioPage projectId={studioProject} />}
          {route.page === "projects" && <ProjectsPage />}
          {route.page === "voices" && <VoicesPage />}
          {route.page === "transcription" && <TranscriptionPage />}
          {route.page === "models" && <ModelsPage />}
          {route.page === "jobs" && <JobsPage />}
          {route.page === "settings" && <SettingsPage />}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  const [ready, setReady] = useState<"loading" | "ok" | "missing">("loading");
  useEffect(() => {
    initToken().then((t) => setReady(t ? "ok" : "missing"));
  }, []);
  if (ready === "loading")
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    );
  if (ready === "missing" || !getToken())
    return (
      <EmptyState icon={<KeyRound className="size-6" />} title="Open the studio from its launcher">
        This local studio needs a per-session access token. Start it with <code>scripts/start</code> (or the desktop
        app) and use the link it prints, which includes <code>#token=…</code>.
      </EmptyState>
    );
  return (
    <TooltipPrimitive.Provider>
      <ToastProvider>
        <div className="flex h-full flex-col">
          <PlayerProvider>
            <div className="min-h-0 flex-1">
              <Shell />
            </div>
          </PlayerProvider>
        </div>
      </ToastProvider>
    </TooltipPrimitive.Provider>
  );
}

