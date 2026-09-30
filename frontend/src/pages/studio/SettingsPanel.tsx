import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BookA, Info, Languages, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Button, Field, Input, Modal, Notice, Select, Textarea, useToast } from "../../components/ui";
import { api, errorMessage } from "../../lib/api";
import { langName } from "../../lib/format";
import { patchSegmentInCache, qk, useModels } from "../../lib/queries";
import type { Capabilities, ModelInfo, Project, ProjectSettings, Pronunciation, Segment } from "../../lib/types";

export function languagesOf(caps: Capabilities | null | undefined): { code: string; experimental: boolean }[] {
  if (!caps) return [];
  return [
    ...caps.languages_tested.map((code) => ({ code, experimental: false })),
    ...caps.languages_experimental.map((code) => ({ code, experimental: true })),
  ];
}

const PREFIX: Record<string, string> = { "en-us": "a", "en-gb": "b", es: "e", fr: "f", hi: "h", it: "i", "pt-br": "p", zh: "z", ur: "h" };
export function voicesFor(caps: Capabilities | null | undefined, lang: string) {
  return (caps?.preset_voices ?? []).filter((v) => v.id[0] === PREFIX[lang]);
}

function useTtsModels() {
  const models = useModels();
  const installed = (models.data?.items ?? []).filter((m) => m.kind === "tts" && m.status === "installed");
  return { models, installed };
}

export function currentModel(installed: ModelInfo[], id: string | null | undefined): ModelInfo | undefined {
  return installed.find((m) => m.id === id) ?? installed[0];
}

export function SettingsPanel({ project, focused }: { project: Project; focused: Segment | null }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { models, installed } = useTtsModels();
  const model = currentModel(installed, project.settings.model_id);
  const caps = model?.capabilities;
  const langs = languagesOf(caps);
  const [prons, setProns] = useState(false);
  const [translit, setTranslit] = useState(false);

  const saveProject = useMutation({
    mutationFn: (body: { default_language?: string; settings?: ProjectSettings }) => api.patch<Project>(`/projects/${project.id}`, body),
    onSuccess: (p) => qc.setQueryData(qk.project(p.id), p),
    onError: (e) => toast("danger", errorMessage(e)),
  });
  const saveSeg = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.patch<Segment>(`/segments/${focused!.id}`, body),
    onSuccess: (s) => {
      patchSegmentInCache(qc, s);
      qc.invalidateQueries({ queryKey: qk.project(project.id) });
    },
    onError: (e) => toast("danger", errorMessage(e)),
  });
  const setSettings = (patch: Partial<ProjectSettings>) => saveProject.mutate({ settings: { ...project.settings, ...patch } });

  if (models.isLoading) return <aside className="w-80 shrink-0 border-l border-line bg-panel p-4 text-sm text-muted">Loading…</aside>;

  const lang = project.default_language;
  const langSupported = langs.some((l) => l.code === lang);
  const voiceList = voicesFor(caps, lang);
  const segLang = focused?.language ?? lang;
  const segVoices = voicesFor(caps, segLang);

  return (
    <aside aria-label="Generation settings" className="scroll-thin flex w-80 shrink-0 flex-col gap-5 overflow-y-auto border-l border-line bg-panel p-4">
      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold">Project voice</h2>
        {!model ? (
          <Notice tone="warn" title="No speech model installed">
            Install one on the <a className="text-accent underline" href="#/models">Models page</a> to generate audio.
          </Notice>
        ) : (
          <>
            <Field label="Model" htmlFor="sp-model">
              <Select id="sp-model" value={model.id} onChange={(e) => setSettings({ model_id: e.target.value })}>
                {installed.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              label="Language"
              htmlFor="sp-lang"
              hint={langs.find((l) => l.code === lang)?.experimental ? "Experimental: not yet evaluated by native listeners." : undefined}
            >
              <Select id="sp-lang" value={lang} onChange={(e) => saveProject.mutate({ default_language: e.target.value })}>
                {!langSupported && <option value={lang}>{langName(lang)} (not supported by this model)</option>}
                {langs.map((l) => (
                  <option key={l.code} value={l.code}>
                    {langName(l.code)}
                    {l.experimental ? " — experimental" : ""}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Voice" htmlFor="sp-voice" hint={caps?.voice_cloning ? undefined : "This model uses built-in voices (no cloning)."}>
              <Select
                id="sp-voice"
                value={project.settings.voice ?? ""}
                onChange={(e) => setSettings({ voice: e.target.value, voice_profile_id: null })}
              >
                {!voiceList.some((v) => v.id === project.settings.voice) && <option value={project.settings.voice ?? ""}>Choose a voice…</option>}
                {voiceList.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.label} ({v.gender})
                  </option>
                ))}
              </Select>
            </Field>
            {caps?.speed_control && caps.speed_range && (
              <Field label={`Speed · ${project.settings.speed.toFixed(2)}×`} htmlFor="sp-speed" hint="A model control (not post-processing).">
                <input
                  id="sp-speed"
                  type="range"
                  min={caps.speed_range[0]}
                  max={caps.speed_range[1]}
                  step={0.05}
                  defaultValue={project.settings.speed}
                  onMouseUp={(e) => setSettings({ speed: Number((e.target as HTMLInputElement).value) })}
                  onKeyUp={(e) => setSettings({ speed: Number((e.target as HTMLInputElement).value) })}
                  className="accent-[var(--accent)]"
                />
              </Field>
            )}
            <Field label="Default pause between segments (ms)" htmlFor="sp-pause" hint="Applies to new segments.">
              <Input
                id="sp-pause"
                type="number"
                min={0}
                max={10000}
                step={100}
                defaultValue={project.settings.pause_ms}
                onBlur={(e) => setSettings({ pause_ms: Number(e.target.value) })}
              />
            </Field>
          </>
        )}
      </section>

      {focused && model && (
        <section className="flex flex-col gap-3 border-t border-line pt-4">
          <h2 className="text-sm font-semibold">Selected segment</h2>
          <Field label="Language override" htmlFor="sg-lang">
            <Select id="sg-lang" value={focused.language ?? ""} onChange={(e) => saveSeg.mutate({ language: e.target.value || null })}>
              <option value="">Project default ({langName(lang)})</option>
              {langs.map((l) => (
                <option key={l.code} value={l.code}>
                  {langName(l.code)}
                  {l.experimental ? " — experimental" : ""}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Voice override" htmlFor="sg-voice">
            <Select
              id="sg-voice"
              value={focused.preset_voice ?? ""}
              onChange={(e) => saveSeg.mutate(e.target.value ? { preset_voice: e.target.value } : { clear_voice: true })}
            >
              <option value="">Project voice</option>
              {segVoices.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.label} ({v.gender})
                </option>
              ))}
            </Select>
          </Field>
          {caps?.speed_control && (
            <Field label="Speed override" htmlFor="sg-speed">
              <Select
                id="sg-speed"
                value={focused.speed == null ? "" : String(focused.speed)}
                onChange={(e) => saveSeg.mutate({ speed: e.target.value ? Number(e.target.value) : null })}
              >
                <option value="">Project speed</option>
                {[0.8, 0.9, 1.0, 1.1, 1.2, 1.3].map((s) => (
                  <option key={s} value={s}>
                    {s.toFixed(1)}×
                  </option>
                ))}
              </Select>
            </Field>
          )}
        </section>
      )}

      <section className="flex flex-col gap-2 border-t border-line pt-4">
        <h2 className="text-sm font-semibold">Text tools</h2>
        <Button icon={<BookA className="size-4" />} onClick={() => setProns(true)}>
          Pronunciations ({project.settings.pronunciations.length})
        </Button>
        <Button icon={<Languages className="size-4" />} onClick={() => setTranslit(true)}>
          Roman Urdu → Urdu script
        </Button>
      </section>

      {caps && (
        <section className="flex flex-col gap-2 border-t border-line pt-4 text-xs text-muted">
          <h2 className="flex items-center gap-1.5 text-sm font-semibold text-fg">
            <Info className="size-4" /> About this model
          </h2>
          <div className="flex flex-wrap gap-1">
            <Badge>{caps.output_sample_rate ? `${caps.output_sample_rate / 1000} kHz` : "?"}</Badge>
            <Badge>Max {caps.max_input_chars} chars/segment</Badge>
            <Badge>{caps.devices.join(", ").toUpperCase()}</Badge>
            <Badge>{caps.voice_cloning ? "Voice cloning" : "No cloning"}</Badge>
          </div>
          <ul className="list-disc space-y-1 pl-4">
            {caps.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </section>
      )}
      <PronunciationDialog open={prons} onOpenChange={setProns} project={project} onSave={(list) => setSettings({ pronunciations: list })} />
      <TransliterateDialog open={translit} onOpenChange={setTranslit} />
    </aside>
  );
}

function PronunciationDialog({
  open,
  onOpenChange,
  project,
  onSave,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  project: Project;
  onSave: (p: Pronunciation[]) => void;
}) {
  const [rows, setRows] = useState<Pronunciation[]>(project.settings.pronunciations);
  useEffect(() => {
    if (open) setRows(project.settings.pronunciations);
  }, [open, project.settings.pronunciations]);
  const update = (i: number, patch: Partial<Pronunciation>) => setRows((r) => r.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const valid = rows.every((r) => r.pattern.trim());
  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      wide
      title="Pronunciation dictionary"
      description="Project-wide replacements applied to the spoken text only. Your script is not changed. Segments affected by a change get a new revision (their old takes are marked as made from older text)."
      footer={
        <>
          <Button onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            variant="primary"
            disabled={!valid}
            onClick={() => {
              onSave(rows.map((r) => ({ ...r, pattern: r.pattern.trim(), language: r.language || null })));
              onOpenChange(false);
            }}
          >
            Save dictionary
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-2">
        {rows.length === 0 && <p className="text-sm text-muted">No entries. Example: “Hamza” → “Hum-zah”.</p>}
        {rows.map((r, i) => (
          <div key={i} className="grid grid-cols-[1fr_1fr_110px_auto_auto] items-center gap-2">
            <Input aria-label="Written as" placeholder="Written as" value={r.pattern} onChange={(e) => update(i, { pattern: e.target.value })} dir="auto" />
            <Input aria-label="Say as" placeholder="Say as" value={r.replacement} onChange={(e) => update(i, { replacement: e.target.value })} dir="auto" />
            <Select aria-label="Language" value={r.language ?? ""} onChange={(e) => update(i, { language: e.target.value || null })}>
              <option value="">All languages</option>
              <option value="en">English</option>
              <option value="ur">Urdu</option>
              <option value="hi">Hindi</option>
            </Select>
            <label className="flex items-center gap-1 text-xs">
              <input type="checkbox" checked={r.whole_word} onChange={(e) => update(i, { whole_word: e.target.checked })} /> Whole word
            </label>
            <button aria-label="Remove entry" className="rounded p-1 text-muted hover:text-danger" onClick={() => setRows((x) => x.filter((_, j) => j !== i))}>
              <Trash2 className="size-4" />
            </button>
          </div>
        ))}
        <Button
          className="self-start"
          size="sm"
          icon={<Plus className="size-4" />}
          onClick={() => setRows((r) => [...r, { pattern: "", replacement: "", language: null, whole_word: true, case_sensitive: false }])}
        >
          Add entry
        </Button>
      </div>
    </Modal>
  );
}

function TransliterateDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [text, setText] = useState("");
  const [amb, setAmb] = useState(false);
  const run = useMutation({
    mutationFn: () =>
      api.post<{ text: string; converted: string[]; unchanged: string[]; ambiguous_skipped: string[]; notice: string }>("/text/transliterate", {
        text,
        convert_ambiguous: amb,
      }),
  });
  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      wide
      title="Roman Urdu → Urdu script (preview)"
      description="An explicit, dictionary-based helper. It does not change your project; copy the result into a segment if you want it."
    >
      <div className="grid gap-3">
        <Textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder="aap kaise hain?" aria-label="Roman Urdu text" />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={amb} onChange={(e) => setAmb(e.target.checked)} />
          Also convert words that are also English (is, to, main, do…)
        </label>
        <Button className="self-start" variant="primary" disabled={!text.trim()} loading={run.isPending} onClick={() => run.mutate()}>
          Preview conversion
        </Button>
        {run.data && (
          <div className="grid gap-2">
            <Textarea readOnly dir="rtl" rows={4} value={run.data.text} aria-label="Converted text" className="rtl-text" />
            <Notice tone="warn">{run.data.notice}</Notice>
            <div className="text-xs text-muted">
              Converted: {run.data.converted.length} · Left unchanged: {run.data.unchanged.join(", ") || "none"}
              {run.data.ambiguous_skipped.length > 0 && ` · Skipped (ambiguous): ${run.data.ambiguous_skipped.join(", ")}`}
            </div>
            <Button size="sm" className="self-start" onClick={() => navigator.clipboard?.writeText(run.data!.text)}>
              Copy result
            </Button>
          </div>
        )}
      </div>
    </Modal>
  );
}
