import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FolderOpen, Plus, Search, Trash2 } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, ConfirmDialog, EmptyState, Field, Input, Modal, Select, Skeleton, Textarea, useToast } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { fmtDate, langName } from "../lib/format";
import { qk, useProjects, useSettings } from "../lib/queries";
import { navigate } from "../lib/router";
import type { Project, ProjectSummary } from "../lib/types";

export const PROJECT_LANGUAGES = ["en-us", "en-gb", "es", "fr", "hi", "it", "pt-br", "zh", "ur"];

export function NewProjectDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const settings = useSettings();
  const [name, setName] = useState("");
  const [lang, setLang] = useState("en-us");
  const [script, setScript] = useState("");
  const create = useMutation({
    mutationFn: () => api.post<Project>("/projects", { name: name.trim(), default_language: lang, script }),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: qk.projects });
      qc.setQueryData(qk.project(p.id), p);
      onOpenChange(false);
      setName("");
      setScript("");
      navigate(`/studio/${p.id}`);
    },
    onError: (e) => toast("danger", errorMessage(e)),
  });
  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title="New project"
      description="Your script is split into segments you can generate and review one by one."
      wide
      footer={
        <>
          <Button onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="primary" disabled={!name.trim()} loading={create.isPending} onClick={() => create.mutate()}>
            Create project
          </Button>
        </>
      }
    >
      <div className="grid gap-4">
        <div className="grid grid-cols-[1fr_200px] gap-3">
          <Field label="Project name" htmlFor="np-name">
            <Input id="np-name" autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Course intro narration" />
          </Field>
          <Field label="Language" htmlFor="np-lang">
            <Select id="np-lang" value={lang} onChange={(e) => setLang(e.target.value)}>
              {PROJECT_LANGUAGES.filter((l) => l !== "ur" || settings.data?.show_unevaluated_languages).map((l) => (
                <option key={l} value={l}>
                  {langName(l)}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field
          label="Script (optional)"
          htmlFor="np-script"
          hint={`Separate paragraphs with a blank line. Segmentation: ${settings.data?.segmentation_mode ?? "paragraph"} (change in Settings).`}
        >
          <Textarea id="np-script" dir="auto" rows={10} value={script} onChange={(e) => setScript(e.target.value)} placeholder="Paste or type your script…" />
        </Field>
      </div>
    </Modal>
  );
}

export default function ProjectsPage() {
  const projects = useProjects();
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<ProjectSummary | null>(null);
  const qc = useQueryClient();
  const toast = useToast();
  const del = useMutation({
    mutationFn: (id: string) => api.del<{ deleted_audio_files: number; cancelled_jobs: number }>(`/projects/${id}`),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: qk.projects });
      toast("ok", `Project deleted (${r.deleted_audio_files} audio files removed${r.cancelled_jobs ? `, ${r.cancelled_jobs} jobs cancelled` : ""}).`);
      setDeleting(null);
    },
    onError: (e) => toast("danger", errorMessage(e)),
  });
  const items = (projects.data?.items ?? []).filter((p) => p.name.toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-8 py-8">
        <div className="mb-6 flex items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold">Projects</h1>
            <p className="text-sm text-muted">Scripts, generated takes and exports are saved automatically.</p>
          </div>
          <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>
            New project
          </Button>
        </div>
        {(projects.data?.total ?? 0) > 0 && (
          <div className="relative mb-4 w-72">
            <Search className="absolute top-2.5 left-3 size-4 text-muted" aria-hidden />
            <Input aria-label="Search projects" className="pl-9" placeholder="Search projects" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
        )}
        {projects.isLoading ? (
          <div className="grid gap-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-20" />
            ))}
          </div>
        ) : projects.isError ? (
          <EmptyState icon={<FolderOpen className="size-6" />} title="Could not load projects" action={<Button onClick={() => projects.refetch()}>Try again</Button>}>
            {errorMessage(projects.error)}
          </EmptyState>
        ) : items.length === 0 ? (
          <Card>
            <EmptyState
              icon={<FolderOpen className="size-6" />}
              title={q ? "No matching projects" : "No projects yet"}
              action={!q && <Button variant="primary" onClick={() => setCreating(true)}>Create your first project</Button>}
            >
              {!q && "A project holds a script, its segments, every generated take and your exports."}
            </EmptyState>
          </Card>
        ) : (
          <div className="grid gap-3">
            {items.map((p) => (
              <Card key={p.id} className="flex items-center gap-4 px-5 py-4 transition-colors hover:border-accent/40">
                <a href={`#/studio/${p.id}`} className="min-w-0 flex-1">
                  <div className="truncate font-medium">{p.name}</div>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
                    <Badge>{langName(p.default_language)}</Badge>
                    <span>
                      {p.generated_count}/{p.segment_count} segments with a selected take
                    </span>
                    <span>· Updated {fmtDate(p.updated_at)}</span>
                  </div>
                </a>
                <Button size="sm" onClick={() => navigate(`/studio/${p.id}`)}>
                  Open
                </Button>
                <Button size="sm" variant="ghost" aria-label={`Delete ${p.name}`} icon={<Trash2 className="size-4" />} onClick={() => setDeleting(p)} />
              </Card>
            ))}
          </div>
        )}
      </div>
      <NewProjectDialog open={creating} onOpenChange={setCreating} />
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`Delete “${deleting?.name}”?`}
        confirmLabel="Delete project"
        busy={del.isPending}
        onConfirm={() => deleting && del.mutate(deleting.id)}
      >
        <p>This permanently deletes the script, all segments, every generated take and their audio files, and this project's exports.</p>
        <p className="text-muted">Queued generation jobs are cancelled. Voice profiles are not affected. This cannot be undone.</p>
      </ConfirmDialog>
    </div>
  );
}
