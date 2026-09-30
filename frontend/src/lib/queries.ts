import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type {
  AppSettings,
  ExportRecord,
  Job,
  ModelInfo,
  Page,
  Project,
  ProjectSummary,
  Segment,
  SystemCapabilities,
  Take,
  Transcription,
  Voice,
} from "./types";

export const qk = {
  projects: ["projects"] as const,
  project: (id: string) => ["project", id] as const,
  takes: (segId: string) => ["takes", segId] as const,
  models: ["models"] as const,
  voices: ["voices"] as const,
  jobs: (filter: string) => ["jobs", filter] as const,
  settings: ["settings"] as const,
  system: ["system"] as const,
  exports: (pid: string) => ["exports", pid] as const,
  transcriptions: ["transcriptions"] as const,
};

export const useProjects = () =>
  useQuery({ queryKey: qk.projects, queryFn: () => api.get<Page<ProjectSummary>>("/projects?limit=200") });

export const useProject = (id: string | null) =>
  useQuery({
    queryKey: qk.project(id ?? "none"),
    queryFn: () => api.get<Project>(`/projects/${id}`),
    enabled: !!id,
  });

export const useTakes = (segId: string | null, enabled = true) =>
  useQuery({
    queryKey: qk.takes(segId ?? "none"),
    queryFn: () => api.get<{ items: Take[]; selected_take_id: string | null }>(`/segments/${segId}/takes`),
    enabled: !!segId && enabled,
  });

export const useModels = () =>
  useQuery({
    queryKey: qk.models,
    queryFn: () => api.get<{ items: ModelInfo[]; free_disk_bytes: number; registry_reviewed_at: string }>("/models"),
  });

export const useVoices = () =>
  useQuery({
    queryKey: qk.voices,
    queryFn: () =>
      api.get<Page<Voice> & { cloning_engines_installed: string[]; consent_options: Record<string, string> }>(
        "/voices?limit=500",
      ),
  });

export const useJobs = (filter = "") =>
  useQuery({
    queryKey: qk.jobs(filter),
    queryFn: () => api.get<Page<Job> & { counts: Record<string, number> }>(`/jobs?limit=200${filter}`),
  });

export const useSettings = () => useQuery({ queryKey: qk.settings, queryFn: () => api.get<AppSettings>("/settings") });

export const useSystem = () =>
  useQuery({ queryKey: qk.system, queryFn: () => api.get<SystemCapabilities>("/system/capabilities") });

export const useExports = (pid: string | null) =>
  useQuery({
    queryKey: qk.exports(pid ?? "none"),
    queryFn: () => api.get<Page<ExportRecord>>(`/projects/${pid}/exports`),
    enabled: !!pid,
  });

export const useTranscriptions = () =>
  useQuery({ queryKey: qk.transcriptions, queryFn: () => api.get<Page<Transcription>>("/transcriptions") });

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: Partial<AppSettings>) => api.patch<AppSettings>("/settings", patch),
    onSuccess: (data) => {
      qc.setQueryData(qk.settings, data);
      qc.invalidateQueries({ queryKey: qk.models });
    },
  });
}

/** Replace one segment inside the cached project without a refetch. */
export function patchSegmentInCache(qc: ReturnType<typeof useQueryClient>, seg: Segment): void {
  qc.setQueryData<Project>(qk.project(seg.project_id), (p) => {
    if (!p) return p;
    return {
      ...p,
      chapters: p.chapters.map((c) => ({
        ...c,
        segments: c.segments.map((s) => (s.id === seg.id ? { ...s, ...seg } : s)),
      })),
    };
  });
}
