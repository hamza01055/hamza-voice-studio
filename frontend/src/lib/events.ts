import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { mediaUrl } from "./api";
import { qk } from "./queries";
import type { Job, Project } from "./types";

type Listener = (job: Job) => void;
const listeners = new Set<Listener>();
const latest = new Map<string, Job>();

export function onJob(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function latestJob(id: string | null | undefined): Job | undefined {
  return id ? latest.get(id) : undefined;
}

/** Single SSE connection per UI; pushes job updates into the query cache. */
export function useJobEvents(enabled: boolean): "connecting" | "open" | "error" {
  const qc = useQueryClient();
  const [state, setState] = useState<"connecting" | "open" | "error">("connecting");
  const timers = useRef<Record<string, number>>({});

  useEffect(() => {
    if (!enabled) return;
    let es: EventSource | null = null;
    let retry: number | undefined;
    const debounce = (key: string, fn: () => void, ms = 250) => {
      window.clearTimeout(timers.current[key]);
      timers.current[key] = window.setTimeout(fn, ms);
    };
    const connect = () => {
      es = new EventSource(mediaUrl("/events"));
      es.addEventListener("ready", () => setState("open"));
      es.addEventListener("job", (ev) => {
        const job = JSON.parse((ev as MessageEvent).data) as Job;
        latest.set(job.id, job);
        listeners.forEach((l) => l(job));
        debounce("jobs", () => qc.invalidateQueries({ queryKey: ["jobs"] }), 400);
        if (job.type === "tts" && job.project_id) {
          const pid = job.project_id;
          // keep segment badges live without refetching the whole project on every tick
          qc.setQueryData<Project>(qk.project(pid), (p) =>
            p
              ? {
                  ...p,
                  chapters: p.chapters.map((c) => ({
                    ...c,
                    segments: c.segments.map((s) =>
                      s.id === job.segment_id
                        ? {
                            ...s,
                            active_job_id: isActive(job.status) ? job.id : s.active_job_id === job.id ? null : s.active_job_id,
                            active_job_status: isActive(job.status)
                              ? job.status
                              : s.active_job_id === job.id
                                ? null
                                : s.active_job_status,
                          }
                        : s,
                    ),
                  })),
                }
              : p,
          );
          if (!isActive(job.status)) {
            debounce(`p-${pid}`, () => qc.invalidateQueries({ queryKey: qk.project(pid) }));
            if (job.segment_id) qc.invalidateQueries({ queryKey: qk.takes(job.segment_id) });
            debounce("projects", () => qc.invalidateQueries({ queryKey: qk.projects }), 800);
          }
        }
        if (job.type === "export" && job.project_id && !isActive(job.status)) {
          qc.invalidateQueries({ queryKey: qk.exports(job.project_id) });
        }
        if (job.type === "model_download") {
          debounce("models", () => qc.invalidateQueries({ queryKey: qk.models }), 500);
          if (!isActive(job.status)) qc.invalidateQueries({ queryKey: qk.system });
        }
        if (job.type === "transcribe" && !isActive(job.status)) {
          qc.invalidateQueries({ queryKey: qk.transcriptions });
        }
      });
      es.onerror = () => {
        setState("error");
        es?.close();
        retry = window.setTimeout(connect, 3000);
      };
    };
    connect();
    return () => {
      es?.close();
      window.clearTimeout(retry);
    };
  }, [enabled, qc]);
  return state;
}

export function isActive(status: string | null | undefined): boolean {
  return status === "queued" || status === "loading_model" || status === "running" || status === "cancelling";
}

/** Live view of one job (from SSE), falling back to the initial value. */
export function useLiveJob(jobId: string | null | undefined): Job | undefined {
  const [job, setJob] = useState<Job | undefined>(() => latestJob(jobId));
  useEffect(() => {
    setJob(latestJob(jobId));
    if (!jobId) return;
    return onJob((j) => {
      if (j.id === jobId) setJob(j);
    });
  }, [jobId]);
  return job;
}
