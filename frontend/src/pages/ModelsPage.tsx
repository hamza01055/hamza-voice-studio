import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Boxes, Cpu, Download, ExternalLink, HardDrive, ShieldCheck, Trash2, XCircle } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, ConfirmDialog, Modal, Notice, Progress, Skeleton, useToast } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { isActive, useLiveJob } from "../lib/events";
import { COMMERCIAL_LABEL, fmtBytes, fmtDate, langName } from "../lib/format";
import { qk, useModels, useSystem } from "../lib/queries";
import type { ModelInfo } from "../lib/types";

const STATUS: Record<string, { label: string; tone: "neutral" | "ok" | "warn" | "danger" | "accent" }> = {
  installed: { label: "Installed", tone: "ok" },
  not_installed: { label: "Not installed", tone: "neutral" },
  pending: { label: "Download pending", tone: "accent" },
  downloading: { label: "Downloading", tone: "accent" },
  verifying: { label: "Verifying", tone: "accent" },
  failed: { label: "Install failed", tone: "danger" },
  damaged: { label: "Files missing", tone: "danger" },
  not_integrated: { label: "Not integrated", tone: "neutral" },
};

const VERIFICATION: Record<string, string> = {
  verified_real_inference: "Real inference verified in development",
  unverified_not_downloaded: "Integrated, but not yet verified with real weights",
  not_tested: "Evaluated on paper only",
  test_only: "Test fixture",
};

function ModelCard({ m, onInstall, onRemove }: { m: ModelInfo; onInstall: () => void; onRemove: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const job = useLiveJob(m.active_job_id);
  const st = STATUS[job && isActive(job.status) ? "downloading" : m.status] ?? STATUS.not_installed;
  const cancel = useMutation({
    mutationFn: () => api.post(`/model-downloads/${m.active_job_id}/cancel`),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.models }),
    onError: (e) => toast("danger", errorMessage(e)),
  });
  const commercial = m.license.commercial_use;
  const active = !!m.active_job_id && (!job || isActive(job.status));
  return (
    <Card className="p-5">
      <div className="flex items-start gap-4">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent">
          <Boxes className="size-5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-semibold">{m.name}</h2>
            <Badge tone={st.tone}>{st.label}</Badge>
            <Badge>{m.kind === "tts" ? "Speech generation" : "Transcription"}</Badge>
            <Badge tone={commercial === "prohibited" ? "danger" : commercial.startsWith("permitted") ? "ok" : "warn"}>
              {COMMERCIAL_LABEL[commercial] ?? commercial}
            </Badge>
          </div>
          <p className="mt-1 text-xs text-muted">{VERIFICATION[m.verification] ?? m.verification}</p>

          <dl className="mt-3 grid grid-cols-[130px_1fr] gap-x-3 gap-y-1 text-sm">
            <dt className="text-muted">Code licence</dt>
            <dd>{m.license.code}</dd>
            <dt className="text-muted">Weights licence</dt>
            <dd>{m.license.weights}</dd>
            {m.license.third_party && (
              <>
                <dt className="text-muted">Third-party</dt>
                <dd>{m.license.third_party}</dd>
              </>
            )}
            {m.license.commercial_note && (
              <>
                <dt className="text-muted">Note</dt>
                <dd>{m.license.commercial_note}</dd>
              </>
            )}
            {m.languages && (
              <>
                <dt className="text-muted">Languages</dt>
                <dd className="flex flex-wrap gap-1">
                  {(m.languages.verified ?? []).map((l) => (
                    <Badge key={l} tone="ok">
                      {langName(l)}
                    </Badge>
                  ))}
                  {(m.languages.experimental ?? []).map((l) => (
                    <Badge key={l} tone="warn" title="Experimental: produces audio, not evaluated by native listeners">
                      {langName(l)} (exp.)
                    </Badge>
                  ))}
                  {!(m.languages.verified?.length || m.languages.experimental?.length) && <span className="text-muted">Not evaluated</span>}
                </dd>
              </>
            )}
            {m.languages?.notes && (
              <>
                <dt className="text-muted">Language notes</dt>
                <dd className="text-xs text-muted">{m.languages.notes}</dd>
              </>
            )}
            <dt className="text-muted">Download size</dt>
            <dd>{fmtBytes(m.download_size_bytes)}{m.installed_size_bytes ? ` (≈ ${fmtBytes(m.installed_size_bytes)} installed)` : ""}</dd>
            {m.runtime && (
              <>
                <dt className="text-muted">Runtime</dt>
                <dd>{m.runtime}</dd>
              </>
            )}
            {m.capabilities && (
              <>
                <dt className="text-muted">Capabilities</dt>
                <dd className="flex flex-wrap gap-1">
                  <Badge>{m.capabilities.devices.join("/").toUpperCase()}</Badge>
                  {m.kind === "tts" && <Badge>{m.capabilities.voice_cloning ? "Voice cloning" : "Built-in voices only"}</Badge>}
                  {m.capabilities.speed_control && <Badge>Speed control</Badge>}
                  <Badge>Progress: {m.capabilities.progress_reporting.replace("_", " ")}</Badge>
                  <Badge>Cancel: {m.capabilities.cancellation.replace(/_/g, " ")}</Badge>
                  {m.capabilities.output_sample_rate && <Badge>{m.capabilities.output_sample_rate} Hz</Badge>}
                </dd>
              </>
            )}
            {m.upstream && (
              <>
                <dt className="text-muted">Source</dt>
                <dd className="break-all">
                  <a className="inline-flex items-center gap-1 text-accent" href={m.upstream.repository} target="_blank" rel="noreferrer noopener">
                    {m.upstream.model_id} <ExternalLink className="size-3" />
                  </a>{" "}
                  <span className="text-xs text-muted">{m.upstream.version}</span>
                </dd>
              </>
            )}
            {m.installed_at && (
              <>
                <dt className="text-muted">Installed</dt>
                <dd>
                  {fmtDate(m.installed_at)} ·{" "}
                  {m.integrity_status === "verified" ? "checksum verified against pinned value" : "checksum recorded (not pinned upstream)"}
                </dd>
              </>
            )}
          </dl>

          {active && (
            <div className="mt-4 grid gap-1.5">
              <div className="flex justify-between text-xs text-muted">
                <span>{job?.progress_stage ?? "Waiting to download"}</span>
                {job?.progress != null && <span>{Math.round(job.progress * 100)}%</span>}
              </div>
              <Progress value={job?.progress ?? null} label={`Installing ${m.name}`} />
            </div>
          )}
          {m.error_message && !active && m.status !== "installed" && (
            <Notice tone={m.status === "failed" ? "danger" : "info"} className="mt-3">
              {m.error_message}
            </Notice>
          )}
        </div>
        <div className="flex shrink-0 flex-col gap-2">
          {m.status === "not_integrated" ? null : active ? (
            <Button size="sm" icon={<XCircle className="size-4" />} loading={cancel.isPending} onClick={() => cancel.mutate()}>
              Cancel
            </Button>
          ) : m.status === "installed" ? (
            <Button size="sm" variant="ghost" icon={<Trash2 className="size-4" />} onClick={onRemove}>
              Remove
            </Button>
          ) : (
            <Button size="sm" variant="primary" icon={<Download className="size-4" />} onClick={onInstall}>
              {m.status === "failed" || m.status === "damaged" ? "Retry install" : "Install"}
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}

export default function ModelsPage() {
  const models = useModels();
  const system = useSystem();
  const qc = useQueryClient();
  const toast = useToast();
  const [installing, setInstalling] = useState<ModelInfo | null>(null);
  const [removing, setRemoving] = useState<ModelInfo | null>(null);
  const install = useMutation({
    mutationFn: (id: string) => api.post(`/models/${id}/download`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.models });
      setInstalling(null);
    },
    onError: (e) => toast("danger", errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.del(`/models/${id}/installation`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.models });
      setRemoving(null);
    },
    onError: (e) => toast("danger", errorMessage(e)),
  });
  const items = models.data?.items ?? [];
  const integrated = items.filter((m) => m.status !== "not_integrated");
  const evaluated = items.filter((m) => m.status === "not_integrated");
  const s = system.data;
  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-8 py-8">
        <h1 className="text-xl font-semibold">Models</h1>
        <p className="mb-5 text-sm text-muted">
          Models run on this computer. The internet is used only when you install a model. Code and weight licences are shown separately.
        </p>
        {s && (
          <Card className="mb-6 flex flex-wrap gap-x-8 gap-y-2 px-5 py-3 text-sm">
            <span className="flex items-center gap-2">
              <Cpu className="size-4 text-muted" /> {s.cpu.name} · {s.cpu.logical_cores} threads
            </span>
            <span>RAM {Math.round(s.ram.total_mb / 1024)} GB ({Math.round(s.ram.available_mb / 1024)} GB free)</span>
            <span>GPU: {s.gpus.length ? s.gpus.map((g) => `${g.name} (${Math.round(g.vram_total_mb / 1024)} GB)`).join(", ") : "none detected"}</span>
            <span>Device used: {s.selected_device.toUpperCase()}</span>
            <span className="flex items-center gap-2">
              <HardDrive className="size-4 text-muted" /> {Math.round(s.disk.free_mb / 1024)} GB free
            </span>
            {!s.ffmpeg.ffmpeg && <Badge tone="danger">FFmpeg missing</Badge>}
            <span className="w-full text-xs text-muted">{s.cuda_note}</span>
          </Card>
        )}
        {models.isLoading ? (
          <Skeleton className="h-60" />
        ) : (
          <div className="grid gap-4">
            {integrated.map((m) => (
              <ModelCard key={m.id} m={m} onInstall={() => setInstalling(m)} onRemove={() => setRemoving(m)} />
            ))}
            <h2 className="mt-4 text-sm font-semibold">Evaluated but not integrated</h2>
            <p className="-mt-2 text-sm text-muted">Listed for transparency. These cannot be installed in this version.</p>
            {evaluated.map((m) => (
              <ModelCard key={m.id} m={m} onInstall={() => {}} onRemove={() => {}} />
            ))}
          </div>
        )}
      </div>

      <Modal
        open={!!installing}
        onOpenChange={(o) => !o && setInstalling(null)}
        title={`Install ${installing?.name}?`}
        description="Review what will be downloaded before approving."
        footer={
          <>
            <Button onClick={() => setInstalling(null)}>Cancel</Button>
            <Button
              variant="primary"
              icon={<ShieldCheck className="size-4" />}
              loading={install.isPending}
              onClick={() => installing && install.mutate(installing.id)}
            >
              Approve download
            </Button>
          </>
        }
      >
        {installing && (
          <dl className="grid grid-cols-[120px_1fr] gap-x-3 gap-y-2 text-sm">
            <dt className="text-muted">Model</dt>
            <dd>{installing.upstream?.model_id}</dd>
            <dt className="text-muted">Revision</dt>
            <dd className="break-all">{installing.revision}</dd>
            <dt className="text-muted">Download</dt>
            <dd>{fmtBytes(installing.download_size_bytes)}</dd>
            <dt className="text-muted">From</dt>
            <dd className="text-xs break-all">{installing.artifact_urls.join(", ")}</dd>
            <dt className="text-muted">Weights licence</dt>
            <dd>{installing.license.weights}</dd>
            <dt className="text-muted">Destination</dt>
            <dd>The studio's model folder in your app-data directory (see Settings → Data).</dd>
            <dt className="text-muted">Free space</dt>
            <dd>{fmtBytes(models.data?.free_disk_bytes)}</dd>
          </dl>
        )}
      </Modal>
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(o) => !o && setRemoving(null)}
        title={`Remove ${removing?.name}?`}
        confirmLabel="Remove model files"
        busy={remove.isPending}
        onConfirm={() => removing && remove.mutate(removing.id)}
      >
        <p>The model files are deleted from disk. Projects and generated audio are kept; you can reinstall later.</p>
      </ConfirmDialog>
    </div>
  );
}
