import { useMutation } from "@tanstack/react-query";
import { CircleStop, ListChecks, RotateCcw } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, EmptyState, Progress, Select, Skeleton, useToast } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { isActive } from "../lib/events";
import { fmtDate, JOB_STATUS_LABEL } from "../lib/format";
import { useJobs } from "../lib/queries";
import type { Job } from "../lib/types";

const TYPE_LABEL: Record<string, string> = { tts: "Speech", transcribe: "Transcription", export: "Export", model_download: "Model install" };
const TONE: Record<string, "neutral" | "ok" | "warn" | "danger" | "accent"> = {
  queued: "neutral",
  loading_model: "accent",
  running: "accent",
  cancelling: "warn",
  cancelled: "neutral",
  completed: "ok",
  failed: "danger",
  interrupted: "warn",
};

function JobRow({ j }: { j: Job }) {
  const toast = useToast();
  const act = useMutation({
    mutationFn: (a: "cancel" | "retry") => api.post(`/jobs/${j.id}/${a}`),
    onError: (e) => toast("danger", errorMessage(e)),
  });
  const timings = j.result as { rtf?: number; generation_seconds?: number; audio_seconds?: number };
  return (
    <li className="grid grid-cols-[110px_1fr_auto] items-center gap-4 border-b border-line px-4 py-3 last:border-0">
      <div className="flex flex-col gap-1">
        <Badge tone={TONE[j.status]}>{JOB_STATUS_LABEL[j.status]}</Badge>
        <span className="text-xs text-muted">{TYPE_LABEL[j.type]}</span>
      </div>
      <div className="min-w-0">
        <div className="truncate text-sm">
          {j.type === "tts" && `Segment ${j.segment_id?.slice(0, 8) ?? "(deleted)"} · ${String(j.params.voice_label ?? "")}`}
          {j.type === "export" && `${String(j.params.file_name ?? "")}`}
          {j.type === "model_download" && String(j.params.model_id)}
          {j.type === "transcribe" && `Transcription · ${String(j.params.model_id)}`}
        </div>
        <div className="text-xs text-muted">
          {j.progress_stage} · created {fmtDate(j.created_at)}
          {j.retry_count > 0 && ` · attempt ${j.retry_count + 1}`}
          {j.status === "completed" && timings.rtf != null && ` · ${timings.generation_seconds}s for ${timings.audio_seconds}s audio (RTF ${timings.rtf})`}
        </div>
        {isActive(j.status) && <Progress className="mt-1.5" value={j.status === "queued" ? null : j.progress} label="Job progress" />}
        {j.error_message && <div className="mt-1 text-xs text-danger">{j.error_message}</div>}
      </div>
      <div className="flex gap-1.5">
        {(j.status === "queued" || j.status === "running" || j.status === "loading_model") && (
          <Button size="sm" icon={<CircleStop className="size-4" />} loading={act.isPending} onClick={() => act.mutate("cancel")}>
            Cancel
          </Button>
        )}
        {(j.status === "failed" || j.status === "cancelled" || j.status === "interrupted") && (
          <Button size="sm" icon={<RotateCcw className="size-4" />} loading={act.isPending} onClick={() => act.mutate("retry")}>
            Retry
          </Button>
        )}
      </div>
    </li>
  );
}

export default function JobsPage() {
  const [filter, setFilter] = useState("");
  const jobs = useJobs(filter);
  const counts = jobs.data?.counts ?? {};
  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-8 py-8">
        <div className="mb-5 flex items-end justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold">Jobs</h1>
            <p className="text-sm text-muted">
              Every generation, export, transcription and install is a durable job. Jobs survive restarts; work interrupted by a crash is
              detected and can be retried.
            </p>
          </div>
          <Select aria-label="Filter jobs" className="w-52" value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All jobs</option>
            <option value="&status=queued,loading_model,running,cancelling">Active</option>
            <option value="&status=failed,interrupted">Failed or interrupted</option>
            <option value="&status=completed">Completed</option>
          </Select>
        </div>
        <div className="mb-3 flex flex-wrap gap-2 text-xs">
          {Object.entries(counts).map(([k, v]) => (
            <Badge key={k} tone={TONE[k]}>
              {JOB_STATUS_LABEL[k] ?? k}: {v}
            </Badge>
          ))}
        </div>
        {jobs.isLoading ? (
          <Skeleton className="h-40" />
        ) : (jobs.data?.items ?? []).length === 0 ? (
          <Card>
            <EmptyState icon={<ListChecks className="size-6" />} title="No jobs here">
              Jobs appear when you generate speech, export, transcribe or install a model.
            </EmptyState>
          </Card>
        ) : (
          <Card>
            <ul>
              {jobs.data!.items.map((j) => (
                <JobRow key={j.id} j={j} />
              ))}
            </ul>
          </Card>
        )}
      </div>
    </div>
  );
}
