import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { AudioLines, CircleStop, Download, FilePlus2, FolderOpen, Pencil, Plus, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button, EmptyState, IconButton, Input, Notice, Skeleton, useToast } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { isActive, onJob } from "../lib/events";
import { fmtDuration, langName } from "../lib/format";
import { qk, useModels, useProject } from "../lib/queries";
import { navigate } from "../lib/router";
import type { Project, Segment } from "../lib/types";
import { NewProjectDialog } from "./ProjectsPage";
import { useGenerate } from "./studio/hooks";
import { ExportDialog } from "./studio/ExportDialog";
import { ScriptDialog } from "./studio/ScriptDialog";
import { SegmentCard } from "./studio/SegmentCard";
import { currentModel, SettingsPanel } from "./studio/SettingsPanel";

function dotClass(s: Segment): string {
  if (isActive(s.active_job_status)) return "bg-accent animate-pulse";
  if (s.selected_take_id && s.selected_take_stale) return "bg-warn";
  if (s.selected_take_id) return "bg-ok";
  return "bg-line";
}

export default function StudioPage({ projectId }: { projectId: string | null }) {
  const project = useProject(projectId);
  const [creating, setCreating] = useState(false);
  if (!projectId)
    return (
      <>
        <EmptyState
          icon={<AudioLines className="size-6" />}
          title="Open a project to start"
          action={
            <div className="flex gap-2">
              <Button onClick={() => navigate("/projects")} icon={<FolderOpen className="size-4" />}>
                Browse projects
              </Button>
              <Button variant="primary" onClick={() => setCreating(true)} icon={<Plus className="size-4" />}>
                New project
              </Button>
            </div>
          }
        >
          The Studio is where you edit a script, generate each segment, compare takes and export.
        </EmptyState>
        <NewProjectDialog open={creating} onOpenChange={setCreating} />
      </>
    );
  if (project.isLoading)
    return (
      <div className="flex h-full gap-4 p-6">
        <Skeleton className="h-full w-60" />
        <div className="flex flex-1 flex-col gap-3">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      </div>
    );
  if (project.isError || !project.data)
    return (
      <EmptyState icon={<FolderOpen className="size-6" />} title="Project not available" action={<Button onClick={() => navigate("/projects")}>Back to projects</Button>}>
        {errorMessage(project.error)}
      </EmptyState>
    );
  return <Studio project={project.data} />;
}

function Studio({ project }: { project: Project }) {
  const qc = useQueryClient();
  const toast = useToast();
  const models = useModels();
  const gen = useGenerate();
  const [chapterId, setChapterId] = useState(project.chapters[0]?.id);
  const chapter = project.chapters.find((c) => c.id === chapterId) ?? project.chapters[0];
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [scriptOpen, setScriptOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [renaming, setRenaming] = useState<string | null>(null);

  const installed = (models.data?.items ?? []).filter((m) => m.kind === "tts" && m.status === "installed");
  const model = currentModel(installed, project.settings.model_id);
  const caps = model?.capabilities;
  const maxChars = caps?.max_input_chars ?? 1000;
  const allSegs = useMemo(() => project.chapters.flatMap((c) => c.segments), [project]);
  const focused = allSegs.find((s) => s.id === focusedId) ?? null;
  const activeCount = allSegs.filter((s) => isActive(s.active_job_status)).length;

  useEffect(
    () =>
      onJob((j) => {
        if (j.project_id !== project.id) return;
        if (j.status === "failed") toast("danger", `Generation failed: ${j.error_message ?? j.error_code}`);
        if (j.status === "interrupted") toast("warn", "A job was interrupted. Retry it from the Jobs page.");
      }),
    [project.id, toast],
  );

  const renameProject = useMutation({
    mutationFn: (name: string) => api.patch<Project>(`/projects/${project.id}`, { name }),
    onSuccess: (p) => {
      qc.setQueryData(qk.project(p.id), p);
      qc.invalidateQueries({ queryKey: qk.projects });
    },
    onError: (e) => toast("danger", errorMessage(e)),
  });
  const chapterMut = useMutation({
    mutationFn: ({ method, path, body }: { method: "post" | "patch" | "del"; path: string; body?: unknown }) =>
      method === "del" ? api.del<Project>(path) : method === "post" ? api.post<Project>(path, body) : api.patch<Project>(path, body),
    onSuccess: (p) => qc.setQueryData(qk.project(project.id), p),
    onError: (e) => toast("danger", errorMessage(e)),
  });
  const cancelAll = useMutation({
    mutationFn: () => api.post<{ cancelled_or_requested: number }>(`/jobs/cancel-all?project_id=${project.id}`),
    onSuccess: (r) => toast("info", `Cancellation requested for ${r.cancelled_or_requested} job(s). Running work stops after the current sentence.`),
  });

  const runGenerate = (ids: string[], onlyMissing: boolean) =>
    gen.mutate(
      { segment_ids: ids, only_missing: onlyMissing },
      {
        onSuccess: (r) => {
          const n = r.jobs.filter((j) => !j.deduplicated).length;
          toast(n ? "ok" : "info", n ? `Queued ${n} segment(s).` : "Nothing new to generate.");
          const errs = r.skipped.filter((s) => s.reason !== "Already has a current take.");
          if (errs.length) toast("warn", `${errs.length} skipped: ${errs[0].reason}`);
          setChecked(new Set());
        },
        onError: (e) => toast("danger", errorMessage(e)),
      },
    );

  const chapterDuration = chapter.segments.reduce((a, s) => a + (s.selected_take_duration ?? 0), 0);
  const voiceLabel = (s: Segment) => {
    const v = s.preset_voice ?? project.settings.voice;
    const opt = caps?.preset_voices.find((x) => x.id === v);
    return `${opt?.label ?? v ?? "No voice"}${s.preset_voice ? " (override)" : ""} · ${langName(s.language ?? project.default_language)}`;
  };

  return (
    <div className="flex h-full">
      {/* left: project + chapter/segment navigation */}
      <aside aria-label="Project outline" className="scroll-thin flex w-60 shrink-0 flex-col overflow-y-auto border-r border-line bg-panel">
        <div className="border-b border-line p-3">
          <label htmlFor="proj-name" className="sr-only">
            Project name
          </label>
          <input
            id="proj-name"
            key={project.name}
            defaultValue={project.name}
            onBlur={(e) => e.target.value.trim() && e.target.value !== project.name && renameProject.mutate(e.target.value.trim())}
            onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
            className="w-full rounded-md bg-transparent px-1 py-0.5 text-sm font-semibold hover:bg-panel-2 focus:bg-panel-2 focus:outline-none"
          />
          <div className="px-1 text-xs text-muted">
            {allSegs.length} segments · {allSegs.filter((s) => s.selected_take_id).length} with takes
          </div>
        </div>
        <div className="flex items-center justify-between px-3 pt-3 pb-1">
          <span className="text-xs font-semibold tracking-wide text-muted uppercase">Chapters</span>
          <IconButton
            label="Add chapter"
            icon={<Plus className="size-4" />}
            onClick={() => chapterMut.mutate({ method: "post", path: `/projects/${project.id}/chapters`, body: { title: `Chapter ${project.chapters.length + 1}` } })}
          />
        </div>
        <ul className="flex flex-col gap-0.5 px-2 pb-3">
          {project.chapters.map((c) => (
            <li key={c.id}>
              <div className={clsx("group flex items-center rounded-lg", c.id === chapter.id ? "bg-accent-soft" : "hover:bg-panel-2")}>
                {renaming === c.id ? (
                  <Input
                    autoFocus
                    defaultValue={c.title}
                    aria-label="Chapter title"
                    className="h-8"
                    onBlur={(e) => {
                      setRenaming(null);
                      if (e.target.value.trim() && e.target.value !== c.title)
                        chapterMut.mutate({ method: "patch", path: `/chapters/${c.id}`, body: { title: e.target.value.trim() } });
                    }}
                    onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
                  />
                ) : (
                  <button
                    onClick={() => setChapterId(c.id)}
                    aria-current={c.id === chapter.id ? "true" : undefined}
                    className={clsx("min-w-0 flex-1 truncate px-2.5 py-1.5 text-left text-sm", c.id === chapter.id && "font-medium text-accent")}
                  >
                    {c.title}
                    <span className="ml-1 text-xs text-muted">({c.segments.length})</span>
                  </button>
                )}
                <div className="hidden items-center pr-1 group-focus-within:flex group-hover:flex">
                  <IconButton label="Rename chapter" icon={<Pencil className="size-3.5" />} onClick={() => setRenaming(c.id)} />
                  {project.chapters.length > 1 && (
                    <IconButton
                      label="Delete chapter"
                      icon={<Trash2 className="size-3.5" />}
                      onClick={() => {
                        if (window.confirm(`Delete “${c.title}”, its ${c.segments.length} segments and all their takes?`))
                          chapterMut.mutate({ method: "del", path: `/chapters/${c.id}` });
                      }}
                    />
                  )}
                </div>
              </div>
              {c.id === chapter.id && c.segments.length > 0 && (
                <ol className="mt-0.5 mb-1 ml-2 flex flex-col border-l border-line pl-2">
                  {c.segments.map((s, i) => (
                    <li key={s.id}>
                      <button
                        onClick={() => {
                          setFocusedId(s.id);
                          document.getElementById(`seg-${s.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
                        }}
                        className={clsx(
                          "flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-xs",
                          s.id === focusedId ? "bg-panel-2 text-fg" : "text-muted hover:text-fg",
                        )}
                      >
                        <span className={clsx("size-2 shrink-0 rounded-full", dotClass(s))} aria-hidden />
                        <span className="w-5 shrink-0 font-mono tabular-nums">{i + 1}</span>
                        <span dir="auto" className="truncate">
                          {s.original_text}
                        </span>
                      </button>
                    </li>
                  ))}
                </ol>
              )}
            </li>
          ))}
        </ul>
      </aside>

      {/* center: script editor and takes */}
      <section aria-label="Script" className="flex min-w-0 flex-1 flex-col">
        <div className="flex flex-wrap items-center gap-2 border-b border-line bg-panel px-5 py-2.5">
          <div className="mr-auto min-w-0">
            <h1 className="truncate text-base font-semibold">{chapter.title}</h1>
            <p className="text-xs text-muted">
              {chapter.segments.length} segments · generated audio {fmtDuration(chapterDuration)}
            </p>
          </div>
          <Button size="sm" icon={<FilePlus2 className="size-4" />} onClick={() => setScriptOpen(true)}>
            Add script
          </Button>
          {checked.size > 0 && (
            <Button size="sm" icon={<Sparkles className="size-4" />} loading={gen.isPending} onClick={() => runGenerate([...checked], false)}>
              Generate selected ({checked.size})
            </Button>
          )}
          <Button
            size="sm"
            variant="primary"
            icon={<Sparkles className="size-4" />}
            loading={gen.isPending}
            disabled={!model || chapter.segments.length === 0}
            onClick={() => runGenerate(chapter.segments.map((s) => s.id), true)}
            title="Generates segments that have no current take; completed segments are not regenerated."
          >
            Generate missing
          </Button>
          {activeCount > 0 && (
            <Button size="sm" icon={<CircleStop className="size-4" />} loading={cancelAll.isPending} onClick={() => cancelAll.mutate()}>
              Cancel all ({activeCount})
            </Button>
          )}
          <Button size="sm" icon={<Download className="size-4" />} onClick={() => setExportOpen(true)} disabled={allSegs.length === 0}>
            Export
          </Button>
        </div>
        <div className="scroll-thin flex-1 overflow-y-auto bg-bg px-5 py-4">
          <div className="mx-auto flex max-w-3xl flex-col gap-3">
            {!model && !models.isLoading && (
              <Notice tone="warn" title="No speech model installed">
                You can write and organise your script now. To generate audio, install a model on the{" "}
                <a className="text-accent underline" href="#/models">
                  Models page
                </a>
                .
              </Notice>
            )}
            {chapter.segments.length === 0 ? (
              <EmptyState
                icon={<FilePlus2 className="size-6" />}
                title="This chapter is empty"
                action={
                  <Button variant="primary" onClick={() => setScriptOpen(true)}>
                    Add script
                  </Button>
                }
              >
                Paste your script and it will be split into paragraphs or sentences you can generate individually.
              </EmptyState>
            ) : (
              chapter.segments.map((s, i) => (
                <SegmentCard
                  key={s.id}
                  seg={s}
                  index={i}
                  total={chapter.segments.length}
                  focused={s.id === focusedId}
                  onFocus={() => setFocusedId(s.id)}
                  checked={checked.has(s.id)}
                  onCheck={(v) =>
                    setChecked((prev) => {
                      const n = new Set(prev);
                      if (v) n.add(s.id);
                      else n.delete(s.id);
                      return n;
                    })
                  }
                  maxChars={maxChars}
                  voiceLabel={voiceLabel(s)}
                  takeVariation={caps?.take_variation ?? "unknown"}
                  language={s.language ?? project.default_language}
                />
              ))
            )}
          </div>
        </div>
      </section>

      <SettingsPanel project={project} focused={focused} />
      <ScriptDialog open={scriptOpen} onOpenChange={setScriptOpen} project={project} chapter={chapter} />
      <ExportDialog open={exportOpen} onOpenChange={setExportOpen} project={project} />
    </div>
  );
}
