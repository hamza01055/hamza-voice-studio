import { ShieldCheck } from "lucide-react";
import { APP_NAME } from "../branding";
import { Card, Field, Input, Notice, Select, Skeleton, Switch } from "../components/ui";
import { useSettings, useSystem, useUpdateSettings } from "../lib/queries";
import type { AppSettings } from "../lib/types";

function Row({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-6 border-b border-line py-3 last:border-0">
      <div>
        <div className="text-sm font-medium">{title}</div>
        {hint && <div className="text-xs text-muted">{hint}</div>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

export default function SettingsPage() {
  const s = useSettings();
  const sys = useSystem();
  const upd = useUpdateSettings();
  if (!s.data) return <Skeleton className="m-8 h-60" />;
  const d = s.data;
  const set = (patch: Partial<AppSettings>) => upd.mutate(patch);
  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-8 py-8">
        <h1 className="mb-5 text-xl font-semibold">Settings</h1>
        <h2 className="mb-2 text-sm font-semibold text-muted">Appearance</h2>
        <Card className="mb-6 px-5">
          <Row title="Theme">
            <Select aria-label="Theme" value={d.theme} onChange={(e) => set({ theme: e.target.value as AppSettings["theme"] })} className="w-40">
              <option value="system">Match system</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </Select>
          </Row>
        </Card>

        <h2 className="mb-2 text-sm font-semibold text-muted">New projects</h2>
        <Card className="mb-6 px-5">
          <Row title="Segmentation" hint="How pasted scripts are split.">
            <Select aria-label="Segmentation" value={d.segmentation_mode} onChange={(e) => set({ segmentation_mode: e.target.value as "paragraph" | "sentence" })} className="w-40">
              <option value="paragraph">Paragraphs</option>
              <option value="sentence">Sentences</option>
            </Select>
          </Row>
          <Row title="Default pause after each segment (ms)">
            <Input aria-label="Default pause" type="number" className="w-28" defaultValue={d.default_pause_ms} onBlur={(e) => set({ default_pause_ms: Number(e.target.value) })} />
          </Row>
          <Row title="Gap between chapters in exports (ms)">
            <Input aria-label="Chapter gap" type="number" className="w-28" defaultValue={d.chapter_gap_ms} onBlur={(e) => set({ chapter_gap_ms: Number(e.target.value) })} />
          </Row>
          <Row title="Show unevaluated experimental languages" hint="Currently adds Urdu (eSpeak phonemes with a Hindi voice). Its quality has NOT been evaluated.">
            <Switch label="Show unevaluated languages" checked={d.show_unevaluated_languages} onChange={(v) => set({ show_unevaluated_languages: v })} />
          </Row>
        </Card>

        <h2 className="mb-2 text-sm font-semibold text-muted">Export defaults</h2>
        <Card className="mb-6 px-5">
          <Row title="Format">
            <Select aria-label="Export format" value={d.export_format} onChange={(e) => set({ export_format: e.target.value as "wav" | "mp3" })} className="w-28">
              <option value="mp3">MP3</option>
              <option value="wav">WAV</option>
            </Select>
          </Row>
          <Row title="MP3 bitrate">
            <Select aria-label="MP3 bitrate" value={d.mp3_bitrate_kbps} onChange={(e) => set({ mp3_bitrate_kbps: Number(e.target.value) })} className="w-28">
              {[96, 128, 160, 192, 256, 320].map((b) => (
                <option key={b} value={b}>
                  {b} kbps
                </option>
              ))}
            </Select>
          </Row>
          <Row title="Normalise loudness by default" hint="EBU R128 at −16 LUFS. Off by default because it changes the audio.">
            <Switch label="Normalise loudness" checked={d.export_loudnorm} onChange={(v) => set({ export_loudnorm: v })} />
          </Row>
        </Card>

        <h2 className="mb-2 text-sm font-semibold text-muted">Performance</h2>
        <Card className="mb-6 px-5">
          <Row title="Unload idle model after (minutes)" hint="Frees memory when you are not generating. 0 keeps it loaded.">
            <Input aria-label="Idle unload minutes" type="number" className="w-28" defaultValue={d.idle_unload_minutes} onBlur={(e) => set({ idle_unload_minutes: Number(e.target.value) })} />
          </Row>
          {sys.data && (
            <Row title="Compute device" hint={sys.data.cuda_note}>
              <span className="text-sm">
                {sys.data.selected_device.toUpperCase()} · {sys.data.inference_threads} threads
              </span>
            </Row>
          )}
        </Card>

        <h2 className="mb-2 text-sm font-semibold text-muted">Privacy &amp; data</h2>
        <Card className="mb-6 px-5 py-4">
          <Notice tone="ok" title="Local only">
            {APP_NAME} contains no analytics or telemetry. Scripts, recordings and generated audio stay on this computer. The network is used only
            when you approve a model download.
          </Notice>
          <div className="mt-3 grid gap-3">
            <Field label="Data folder" hint="Database, audio, exports and models. Back up this folder to back up everything; it is kept when the app is updated or uninstalled.">
              <Input readOnly value={sys.data?.data_dir ?? "…"} aria-label="Data folder" />
            </Field>
          </div>
          <div className="mt-3 flex items-center gap-2 text-xs text-muted">
            <ShieldCheck className="size-4" /> The local API only accepts requests from this app on 127.0.0.1 with a per-session token.
          </div>
        </Card>
      </div>
    </div>
  );
}
