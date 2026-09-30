import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileAudio, Play, Trash2, Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { usePlayer } from "../components/Player";
import { Badge, Button, Card, EmptyState, Field, Notice, Progress, Select, Skeleton, Textarea, useToast } from "../components/ui";
import { api, errorMessage, mediaUrl } from "../lib/api";
import { isActive, useLiveJob } from "../lib/events";
import { fmtDate, fmtDuration, langName } from "../lib/format";
import { qk, useModels, useTranscriptions } from "../lib/queries";
import type { Transcription } from "../lib/types";

function Editor({ t }: { t: Transcription }) {
  const qc = useQueryClient();
  const toast = useToast();
  const player = usePlayer();
  const job = useLiveJob(t.job_id);
  const status = job?.status ?? t.job_status;
  const [text, setText] = useState(t.edited_text ?? t.text);
  useEffect(() => setText(t.edited_text ?? t.text), [t.id, t.text, t.edited_text]);
  const save = useMutation({
    mutationFn: () => api.patch<Transcription>(`/transcriptions/${t.id}`, { edited_text: text }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.transcriptions });
      toast("ok", "Transcript saved.");
    },
    onError: (e) => toast("danger", errorMessage(e)),
  });
  const cancel = useMutation({ mutationFn: () => api.post(`/jobs/${t.job_id}/cancel`) });
  if (isActive(status))
    return (
      <Card className="p-5">
        <div className="mb-2 flex justify-between text-sm">
          <span>{job?.progress_stage ?? "Queued"}</span>
          <Button size="sm" onClick={() => cancel.mutate()}>
            Cancel
          </Button>
        </div>
        <Progress value={job?.progress ?? null} label="Transcription progress" />
      </Card>
    );
  if (status === "failed" || status === "cancelled" || status === "interrupted")
    return <Notice tone="danger">{job?.error_message ?? `Transcription ${status}.`}</Notice>;
  const edited = text !== t.text;
  return (
    <Card className="grid gap-3 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" icon={<Play className="size-4" />} onClick={() => player.play({ assetId: t.source_asset_id, title: t.name, subtitle: "Source audio" })}>
          Play source
        </Button>
        <Badge>Detected: {langName(t.language_detected)}</Badge>
        <Badge>Timestamps: {t.timestamp_kind === "chunk" ? "~28 s chunks" : t.timestamp_kind}</Badge>
        <Badge>No speaker labels (no diarization)</Badge>
      </div>
      <Notice tone="warn">Machine transcripts can contain errors. Review and correct before use.</Notice>
      <Textarea dir="auto" rows={12} value={text} onChange={(e) => setText(e.target.value)} aria-label="Transcript" />
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" size="sm" disabled={text === (t.edited_text ?? t.text)} loading={save.isPending} onClick={() => save.mutate()}>
          Save edits
        </Button>
        <a className="text-sm text-accent" href={mediaUrl(`/transcriptions/${t.id}/export?format=txt`)}>
          Download TXT
        </a>
        {t.timestamp_kind !== "none" && !edited && t.edited_text == null && (
          <>
            <a className="text-sm text-accent" href={mediaUrl(`/transcriptions/${t.id}/export?format=srt`)}>
              SRT
            </a>
            <a className="text-sm text-accent" href={mediaUrl(`/transcriptions/${t.id}/export?format=vtt`)}>
              VTT
            </a>
          </>
        )}
        {(edited || t.edited_text != null) && <span className="text-xs text-muted">Subtitles are only offered for the unedited machine transcript (timings would not match).</span>}
      </div>
      {t.segments.length > 0 && (
        <details>
          <summary className="cursor-pointer text-sm text-muted">Timed segments ({t.segments.length})</summary>
          <ol className="mt-2 grid gap-1 text-sm">
            {t.segments.map((s, i) => (
              <li key={i} className="flex gap-3">
                <span className="w-28 shrink-0 font-mono text-xs text-muted">
                  {fmtDuration(s.start)}–{fmtDuration(s.end)}
                </span>
                <span dir="auto">{s.text}</span>
              </li>
            ))}
          </ol>
        </details>
      )}
    </Card>
  );
}

export default function TranscriptionPage() {
  const models = useModels();
  const list = useTranscriptions();
  const qc = useQueryClient();
  const toast = useToast();
  const asr = (models.data?.items ?? []).filter((m) => m.kind === "asr" && m.status === "installed");
  const [modelId, setModelId] = useState("");
  const [lang, setLang] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    if (!modelId && asr[0]) setModelId(asr[0].id);
  }, [asr, modelId]);
  const start = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append("file", file!);
      fd.append("model_id", modelId);
      if (lang) fd.append("language", lang);
      return api.form<Transcription>("/transcriptions", fd);
    },
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: qk.transcriptions });
      setSelected(t.id);
      setFile(null);
    },
    onError: (e) => toast("danger", errorMessage(e)),
  });
  const del = useMutation({
    mutationFn: (id: string) => api.del(`/transcriptions/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.transcriptions });
      setSelected(null);
    },
  });
  const items = list.data?.items ?? [];
  const current = items.find((t) => t.id === selected) ?? items[0];
  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-8 py-8">
        <h1 className="text-xl font-semibold">Transcription</h1>
        <p className="mb-5 text-sm text-muted">Transcribe local audio on this computer. Nothing is uploaded to the internet.</p>
        {models.isLoading ? (
          <Skeleton className="h-24" />
        ) : asr.length === 0 ? (
          <Card>
            <EmptyState icon={<FileAudio className="size-6" />} title="No transcription model installed" action={<Button onClick={() => (window.location.hash = "#/models")}>Go to Models</Button>}>
              Install a Whisper model on the Models page to enable transcription. Note: Whisper support in this version is implemented but has not
              yet been verified with real weights.
            </EmptyState>
          </Card>
        ) : (
          <Card className="mb-5 grid grid-cols-[1fr_200px_180px_auto] items-end gap-3 p-4">
            <Field label="Audio file" htmlFor="tr-file">
              <input id="tr-file" type="file" accept="audio/*,video/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-sm" />
            </Field>
            <Field label="Model" htmlFor="tr-model">
              <Select id="tr-model" value={modelId} onChange={(e) => setModelId(e.target.value)}>
                {asr.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Language" htmlFor="tr-lang">
              <Select id="tr-lang" value={lang} onChange={(e) => setLang(e.target.value)}>
                <option value="">Detect automatically</option>
                {["en", "ur", "hi", "ar", "es", "fr", "de", "zh"].map((l) => (
                  <option key={l} value={l}>
                    {langName(l)}
                  </option>
                ))}
              </Select>
            </Field>
            <Button variant="primary" icon={<Upload className="size-4" />} disabled={!file || !modelId} loading={start.isPending} onClick={() => start.mutate()}>
              Transcribe
            </Button>
          </Card>
        )}
        {items.length > 0 && (
          <div className="grid grid-cols-[240px_1fr] gap-4">
            <ul className="grid content-start gap-1">
              {items.map((t) => (
                <li key={t.id} className={`group flex items-center rounded-lg ${current?.id === t.id ? "bg-accent-soft" : "hover:bg-panel-2"}`}>
                  <button onClick={() => setSelected(t.id)} className="min-w-0 flex-1 px-3 py-2 text-left">
                    <div className="truncate text-sm font-medium">{t.name}</div>
                    <div className="text-xs text-muted">{fmtDate(t.created_at)}</div>
                  </button>
                  <button
                    aria-label={`Delete ${t.name}`}
                    className="mr-1 hidden rounded p-1 text-muted group-hover:block hover:text-danger"
                    onClick={() => window.confirm("Delete this transcript and its audio?") && del.mutate(t.id)}
                  >
                    <Trash2 className="size-4" />
                  </button>
                </li>
              ))}
            </ul>
            {current && <Editor t={current} />}
          </div>
        )}
      </div>
    </div>
  );
}
