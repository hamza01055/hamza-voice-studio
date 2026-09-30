import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Mic, Mic2, Pause, Pencil, Play, Plus, Scissors, Square, Trash2, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { usePlayer } from "../components/Player";
import { Badge, Button, Card, ConfirmDialog, EmptyState, Field, Input, Modal, Notice, Select, Skeleton, Textarea, useToast } from "../components/ui";
import { api, ApiError, errorMessage } from "../lib/api";
import { fmtDate, fmtDuration, langName } from "../lib/format";
import { qk, useVoices } from "../lib/queries";
import type { Voice } from "../lib/types";

const BASIS_LABEL: Record<string, string> = {
  my_own_voice: "This is my own voice",
  written_permission: "I have the speaker's written permission",
  licensed_voice: "The voice is licensed to me",
  public_domain: "Public domain / licence permits cloning",
};

function Recorder({ onDone }: { onDone: (f: File) => void }) {
  const [state, setState] = useState<"idle" | "recording" | "denied">("idle");
  const [secs, setSecs] = useState(0);
  const rec = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => {
    window.clearInterval(timer.current);
    rec.current?.stream.getTracks().forEach((t) => t.stop());
  }, []);
  const start = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false } });
      const r = new MediaRecorder(stream);
      chunks.current = [];
      r.ondataavailable = (e) => chunks.current.push(e.data);
      r.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks.current, { type: r.mimeType || "audio/webm" });
        onDone(new File([blob], `recording.${(r.mimeType || "audio/webm").includes("ogg") ? "ogg" : "webm"}`, { type: blob.type }));
      };
      r.start();
      rec.current = r;
      setSecs(0);
      timer.current = window.setInterval(() => setSecs((s) => s + 1), 1000);
      setState("recording");
    } catch {
      setState("denied");
    }
  };
  const stop = () => {
    window.clearInterval(timer.current);
    rec.current?.stop();
    setState("idle");
  };
  return (
    <div className="flex items-center gap-3">
      {state === "recording" ? (
        <Button variant="danger" icon={<Square className="size-4" />} onClick={stop}>
          Stop recording
        </Button>
      ) : (
        <Button icon={<Mic className="size-4" />} onClick={start}>
          Record with microphone
        </Button>
      )}
      {state === "recording" && (
        <span className="flex items-center gap-2 text-sm text-danger" role="status">
          <span className="size-2.5 animate-pulse rounded-full bg-danger" /> Recording · {secs}s
        </span>
      )}
      {state === "denied" && <span className="text-sm text-danger">Microphone access was denied or is unavailable.</span>}
    </div>
  );
}

function AddVoiceDialog({ open, onOpenChange, consentOptions }: { open: boolean; onOpenChange: (o: boolean) => void; consentOptions: Record<string, string> }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [lang, setLang] = useState("en-us");
  const [transcript, setTranscript] = useState("");
  const [tags, setTags] = useState("");
  const [basis, setBasis] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [docRef, setDocRef] = useState("");
  const [err, setErr] = useState<ApiError | null>(null);
  const reset = () => {
    setFile(null);
    setName("");
    setTranscript("");
    setTags("");
    setBasis("");
    setConfirmed(false);
    setDocRef("");
    setErr(null);
  };
  const create = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append("file", file!);
      fd.append("name", name.trim());
      fd.append("language", lang);
      fd.append("transcript", transcript);
      fd.append("tags", JSON.stringify(tags.split(",").map((t) => t.trim()).filter(Boolean)));
      fd.append("permission_basis", basis);
      fd.append("consent_confirmed", String(confirmed));
      if (docRef.trim()) fd.append("document_reference", docRef.trim());
      return api.form<Voice>("/voices", fd);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.voices });
      toast("ok", "Voice profile saved.");
      reset();
      onOpenChange(false);
    },
    onError: (e) => setErr(e instanceof ApiError ? e : new ApiError(0, "error", errorMessage(e))),
  });
  const analysisWarnings = (err?.details?.analysis as { warnings?: string[] } | undefined)?.warnings ?? [];
  return (
    <Modal
      open={open}
      onOpenChange={(o) => {
        if (!o) reset();
        onOpenChange(o);
      }}
      wide
      title="Add a voice"
      description="Upload or record a clean recording of one speaker. Only use voices you own or have permission to use."
      footer={
        <>
          <Button onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="primary" disabled={!file || !name.trim() || !basis || !confirmed} loading={create.isPending} onClick={() => create.mutate()}>
            Save voice
          </Button>
        </>
      }
    >
      <div className="grid gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <label className="inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-lg border border-line bg-panel px-3.5 text-sm font-medium hover:bg-panel-2 focus-within:outline-2 focus-within:outline-[var(--focus)]">
            <Upload className="size-4" /> Choose audio file
            <input type="file" accept="audio/*,.wav,.mp3,.flac,.ogg,.m4a,.webm" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <Recorder onDone={setFile} />
        </div>
        {file && (
          <p className="text-sm">
            Selected: <span className="font-medium">{file.name}</span> ({Math.round(file.size / 1024)} KB)
          </p>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Name" htmlFor="v-name">
            <Input id="v-name" value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Language" htmlFor="v-lang">
            <Select id="v-lang" value={lang} onChange={(e) => setLang(e.target.value)}>
              {["en-us", "en-gb", "ur", "hi", "es", "fr", "zh"].map((l) => (
                <option key={l} value={l}>
                  {langName(l)}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Transcript of the recording" htmlFor="v-tr" hint="Some cloning models need the exact words spoken. You can edit it later.">
          <Textarea id="v-tr" dir="auto" rows={3} value={transcript} onChange={(e) => setTranscript(e.target.value)} />
        </Field>
        <Field label="Tags (comma separated)" htmlFor="v-tags">
          <Input id="v-tags" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="narration, calm" />
        </Field>
        <fieldset className="grid gap-2 rounded-lg border border-line p-3">
          <legend className="px-1 text-[13px] font-medium">Permission</legend>
          {Object.keys(consentOptions).map((k) => (
            <label key={k} className="flex items-start gap-2 text-sm">
              <input type="radio" name="basis" value={k} checked={basis === k} onChange={() => setBasis(k)} className="mt-1" />
              <span>{BASIS_LABEL[k] ?? k}</span>
            </label>
          ))}
          <Field label="Consent document reference (optional)" htmlFor="v-doc" hint="e.g. where the signed permission is stored. The file itself is not uploaded.">
            <Input id="v-doc" value={docRef} onChange={(e) => setDocRef(e.target.value)} />
          </Field>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} className="mt-1" />
            <span>{basis ? consentOptions[basis] : "I confirm I own this voice or have permission to use it."} This confirmation is recorded with a timestamp; it is not proof of permission.</span>
          </label>
        </fieldset>
        {err && (
          <Notice tone="danger" title="The recording was not accepted">
            {err.message}
            {analysisWarnings.length > 0 && (
              <ul className="mt-1 list-disc pl-4">
                {analysisWarnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            )}
          </Notice>
        )}
      </div>
    </Modal>
  );
}

function EditVoiceDialog({ voice, onClose }: { voice: Voice | null; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState("");
  const [transcript, setTranscript] = useState("");
  const [tags, setTags] = useState("");
  const [trimStart, setTrimStart] = useState("");
  const [trimEnd, setTrimEnd] = useState("");
  useEffect(() => {
    if (voice) {
      setName(voice.name);
      setTranscript(voice.reference_transcript);
      setTags(voice.tags.join(", "));
      setTrimStart("");
      setTrimEnd("");
    }
  }, [voice]);
  const save = useMutation({
    mutationFn: () =>
      api.patch<Voice>(`/voices/${voice!.id}`, {
        name,
        reference_transcript: transcript,
        tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
        ...(trimStart !== "" || trimEnd !== "" ? { trim_start: trimStart === "" ? 0 : Number(trimStart), trim_end: trimEnd === "" ? voice!.duration : Number(trimEnd) } : {}),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.voices });
      onClose();
    },
    onError: (e) => toast("danger", errorMessage(e)),
  });
  return (
    <Modal
      open={!!voice}
      onOpenChange={(o) => !o && onClose()}
      title="Edit voice"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>
            Save
          </Button>
        </>
      }
    >
      <div className="grid gap-3">
        <Field label="Name" htmlFor="ev-name">
          <Input id="ev-name" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Transcript" htmlFor="ev-tr">
          <Textarea id="ev-tr" dir="auto" rows={3} value={transcript} onChange={(e) => setTranscript(e.target.value)} />
        </Field>
        <Field label="Tags" htmlFor="ev-tags">
          <Input id="ev-tags" value={tags} onChange={(e) => setTags(e.target.value)} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Trim start (s)" htmlFor="ev-ts" hint={`Recording length ${fmtDuration(voice?.duration)}`}>
            <Input id="ev-ts" type="number" min={0} step={0.1} value={trimStart} onChange={(e) => setTrimStart(e.target.value)} />
          </Field>
          <Field label="Trim end (s)" htmlFor="ev-te">
            <Input id="ev-te" type="number" min={0} step={0.1} value={trimEnd} onChange={(e) => setTrimEnd(e.target.value)} />
          </Field>
        </div>
        <p className="text-xs text-muted">
          <Scissors className="mr-1 inline size-3" />
          Trimming replaces the stored reference with the trimmed audio and re-checks its quality.
        </p>
      </div>
    </Modal>
  );
}

export default function VoicesPage() {
  const voices = useVoices();
  const player = usePlayer();
  const qc = useQueryClient();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Voice | null>(null);
  const [deleting, setDeleting] = useState<Voice | null>(null);
  const del = useMutation({
    mutationFn: (id: string) => api.del<{ unassigned_segments: number; note: string }>(`/voices/${id}`),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: qk.voices });
      toast("ok", `Voice deleted. ${r.note}`);
      setDeleting(null);
    },
    onError: (e) => toast("danger", errorMessage(e)),
  });
  const items = voices.data?.items ?? [];
  const cloning = voices.data?.cloning_engines_installed ?? [];
  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-8 py-8">
        <div className="mb-5 flex items-end justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold">Voices</h1>
            <p className="text-sm text-muted">Reference recordings you own or have permission to use, with their consent records.</p>
          </div>
          <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>
            Add voice
          </Button>
        </div>
        {cloning.length === 0 && (
          <Notice tone="info" title="No voice-cloning engine is installed" className="mb-5">
            You can build and check your voice library now, but speech is currently generated with the installed model's built-in voices. A
            profile becomes usable for generation once a compatible cloning model is integrated and installed.
          </Notice>
        )}
        {voices.isLoading ? (
          <Skeleton className="h-40" />
        ) : items.length === 0 ? (
          <Card>
            <EmptyState icon={<Mic2 className="size-6" />} title="No voices yet" action={<Button onClick={() => setAdding(true)}>Add a voice</Button>}>
              Upload or record 5–20 seconds of clear speech from one speaker.
            </EmptyState>
          </Card>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {items.map((v) => {
              const playing = player.playing && player.current?.assetId === v.reference_asset_id;
              return (
                <Card key={v.id} className="p-4">
                  <div className="flex items-start gap-3">
                    <button
                      aria-label={playing ? `Pause ${v.name}` : `Play ${v.name}`}
                      onClick={() => (playing ? player.toggle() : player.play({ assetId: v.reference_asset_id, title: v.name, subtitle: "Reference recording" }))}
                      className="flex size-10 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent"
                    >
                      {playing ? <Pause className="size-4" /> : <Play className="size-4" />}
                    </button>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <h2 className="truncate font-medium">{v.name}</h2>
                        {v.consent.revoked_at && <Badge tone="danger">Permission revoked</Badge>}
                      </div>
                      <div className="mt-1 flex flex-wrap gap-1">
                        <Badge>{langName(v.language)}</Badge>
                        <Badge>{fmtDuration(v.duration)}</Badge>
                        {v.analysis.source && <Badge>{v.analysis.source.sample_rate} Hz</Badge>}
                        {v.tags.map((t) => (
                          <Badge key={t} tone="accent">
                            {t}
                          </Badge>
                        ))}
                        <Badge tone={v.compatible_engine_installed ? "ok" : "neutral"}>
                          {v.compatible_engine ? `Engine: ${v.compatible_engine}` : "No compatible engine installed"}
                        </Badge>
                      </div>
                      {v.reference_transcript && (
                        <p dir="auto" className="rtl-text mt-2 line-clamp-2 text-sm text-muted">
                          “{v.reference_transcript}”
                        </p>
                      )}
                      {(v.analysis.warnings ?? []).length > 0 && (
                        <ul className="mt-2 list-disc pl-4 text-xs text-warn">
                          {v.analysis.warnings!.map((w) => (
                            <li key={w}>{w}</li>
                          ))}
                        </ul>
                      )}
                      <p className="mt-2 text-xs text-muted">
                        {BASIS_LABEL[v.consent.permission_basis]} · recorded {fmtDate(v.consent.recorded_at)}
                        {v.consent.document_reference && ` · document: ${v.consent.document_reference}`}
                      </p>
                    </div>
                    <div className="flex flex-col gap-1">
                      <Button size="sm" variant="ghost" aria-label={`Edit ${v.name}`} icon={<Pencil className="size-4" />} onClick={() => setEditing(v)} />
                      <Button size="sm" variant="ghost" aria-label={`Delete ${v.name}`} icon={<Trash2 className="size-4" />} onClick={() => setDeleting(v)} />
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </div>
      <AddVoiceDialog open={adding} onOpenChange={setAdding} consentOptions={voices.data?.consent_options ?? {}} />
      <EditVoiceDialog voice={editing} onClose={() => setEditing(null)} />
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`Delete voice “${deleting?.name}”?`}
        confirmLabel="Delete voice"
        busy={del.isPending}
        onConfirm={() => deleting && del.mutate(deleting.id)}
      >
        <p>The reference recording is deleted from disk and segments using this voice lose their assignment.</p>
        <p className="text-muted">
          Takes already generated with this voice stay in their projects until you delete them. The consent record is kept, marked as
          revoked, as an audit trail (it contains no audio).
        </p>
      </ConfirmDialog>
    </div>
  );
}
