import { useMutation } from "@tanstack/react-query";
import { Download, FolderOpen } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Button, Field, Input, Modal, Notice, Progress, Select, Switch, useToast } from "../../components/ui";
import { api, errorMessage, mediaUrl } from "../../lib/api";
import { isActive, useLiveJob } from "../../lib/events";
import { fmtBytes, fmtDate, fmtDuration } from "../../lib/format";
import { useExports, useSettings } from "../../lib/queries";
import type { ExportRecord, Project } from "../../lib/types";

export function ExportDialog({ open, onOpenChange, project }: { open: boolean; onOpenChange: (o: boolean) => void; project: Project }) {
  const settings = useSettings();
  const toast = useToast();
  const exports = useExports(open ? project.id : null);
  const [format, setFormat] = useState<"wav" | "mp3">("mp3");
  const [bitrate, setBitrate] = useState(192);
  const [loud, setLoud] = useState(false);
  const [skip, setSkip] = useState(false);
  const [chapter, setChapter] = useState("");
  const [name, setName] = useState(project.name);
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useLiveJob(jobId);

  useEffect(() => {
    if (open && settings.data) {
      setFormat(settings.data.export_format);
      setBitrate(settings.data.mp3_bitrate_kbps);
      setLoud(settings.data.export_loudnorm);
      setName(project.name);
      setJobId(null);
    }
  }, [open, settings.data, project.name]);

  const segs = project.chapters.filter((c) => !chapter || c.id === chapter).flatMap((c) => c.segments);
  const missing = segs.filter((s) => !s.selected_take_id).length;
  const stale = segs.filter((s) => s.selected_take_id && s.selected_take_stale).length;
  const total = segs.reduce((a, s) => a + (s.selected_take_duration ?? 0) + s.pause_after_ms / 1000, 0);

  const start = useMutation({
    mutationFn: () =>
      api.post<{ export: ExportRecord; job_id: string }>(`/projects/${project.id}/exports`, {
        format,
        file_name: name,
        bitrate_kbps: bitrate,
        loudnorm: loud,
        skip_missing: skip,
        chapter_id: chapter || null,
        chapter_gap_ms: settings.data?.chapter_gap_ms ?? 1500,
      }),
    onSuccess: (r) => setJobId(r.job_id),
    onError: (e) => toast("danger", errorMessage(e)),
  });

  const running = job ? isActive(job.status) : start.isPending;
  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      wide
      title="Export audio"
      description="Selected takes are joined in order with each segment's pause. Files are validated before they are marked complete and are never overwritten."
      footer={
        <>
          <Button onClick={() => onOpenChange(false)}>Close</Button>
          <Button
            variant="primary"
            icon={<Download className="size-4" />}
            loading={running}
            disabled={(missing > 0 && !skip) || segs.length === 0 || !name.trim()}
            onClick={() => start.mutate()}
          >
            Export {format.toUpperCase()}
          </Button>
        </>
      }
    >
      <div className="grid gap-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="File name" htmlFor="ex-name">
            <Input id="ex-name" value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Content" htmlFor="ex-ch">
            <Select id="ex-ch" value={chapter} onChange={(e) => setChapter(e.target.value)}>
              <option value="">Whole project</option>
              {project.chapters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Format" htmlFor="ex-fmt">
            <Select id="ex-fmt" value={format} onChange={(e) => setFormat(e.target.value as "wav" | "mp3")}>
              <option value="mp3">MP3</option>
              <option value="wav">WAV (16-bit PCM, native sample rate)</option>
            </Select>
          </Field>
          {format === "mp3" && (
            <Field label="MP3 bitrate" htmlFor="ex-br">
              <Select id="ex-br" value={bitrate} onChange={(e) => setBitrate(Number(e.target.value))}>
                {[96, 128, 160, 192, 256, 320].map((b) => (
                  <option key={b} value={b}>
                    {b} kbps
                  </option>
                ))}
              </Select>
            </Field>
          )}
        </div>
        <label className="flex items-center justify-between gap-3 text-sm">
          <span>
            Normalise loudness (EBU R128, −16 LUFS)
            <span className="block text-xs text-muted">Optional. Makes the level consistent; changes the audio.</span>
          </span>
          <Switch checked={loud} onChange={setLoud} label="Normalise loudness" />
        </label>
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge>{segs.length} segments</Badge>
          <Badge>≈ {fmtDuration(total)}</Badge>
          {missing > 0 && <Badge tone="warn">{missing} without a selected take</Badge>}
          {stale > 0 && <Badge tone="warn">{stale} take(s) from older text</Badge>}
        </div>
        {missing > 0 && (
          <label className="flex items-center justify-between gap-3 text-sm">
            <span>Skip segments without a selected take</span>
            <Switch checked={skip} onChange={setSkip} label="Skip segments without a take" />
          </label>
        )}
        {job && (
          <div className="grid gap-1.5">
            <div className="flex justify-between text-xs text-muted">
              <span>{job.progress_stage}</span>
              {job.progress != null && <span>{Math.round(job.progress * 100)}%</span>}
            </div>
            <Progress value={isActive(job.status) ? job.progress : 1} label="Export progress" />
            {job.status === "failed" && <Notice tone="danger">{job.error_message}</Notice>}
            {job.status === "completed" && <Notice tone="ok">Export complete. Download it below.</Notice>}
          </div>
        )}
        <div>
          <h3 className="mb-2 text-sm font-semibold">Previous exports</h3>
          {(exports.data?.items ?? []).length === 0 ? (
            <p className="text-sm text-muted">None yet.</p>
          ) : (
            <ul className="grid gap-1.5">
              {exports.data!.items.map((e) => (
                <li key={e.id} className="flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm">
                  <span className="min-w-0 flex-1 truncate font-medium">{e.file_name}</span>
                  <span className="text-xs text-muted">
                    {e.status === "completed" ? `${fmtDuration(e.duration)} · ${fmtBytes(e.byte_size)} · ${e.sample_rate} Hz` : e.status}
                  </span>
                  <span className="text-xs text-muted">{fmtDate(e.created_at)}</span>
                  {e.status === "completed" && (
                    <>
                      <a className="text-accent" href={mediaUrl(`/exports/${e.id}/file`)} download={e.file_name}>
                        Download
                      </a>
                      {window.hvsDesktop && (
                        <button className="text-muted hover:text-fg" aria-label="Show in folder" onClick={() => window.hvsDesktop!.revealExport(e.file_name)}>
                          <FolderOpen className="size-4" />
                        </button>
                      )}
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Modal>
  );
}
