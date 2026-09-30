import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Button, Field, Modal, Notice, Select, Textarea, useToast } from "../../components/ui";
import { api, errorMessage } from "../../lib/api";
import { wordCount } from "../../lib/format";
import { qk } from "../../lib/queries";
import type { Chapter, Project } from "../../lib/types";

export function ScriptDialog({
  open,
  onOpenChange,
  project,
  chapter,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  project: Project;
  chapter: Chapter;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"paragraph" | "sentence">(project.settings.segmentation_mode);
  const [how, setHow] = useState<"append" | "replace">("append");
  useEffect(() => {
    if (open) {
      setText(chapter.segments.length ? "" : chapter.script_text);
      setHow(chapter.segments.length ? "append" : "replace");
    }
  }, [open, chapter]);
  const save = useMutation({
    mutationFn: () =>
      api.post<{ created: string[]; project: Project }>(`/projects/${project.id}/segments`, {
        chapter_id: chapter.id,
        script: text,
        mode,
        replace: how === "replace",
      }),
    onSuccess: (r) => {
      qc.setQueryData(qk.project(project.id), r.project);
      toast("ok", `${r.created.length} segment(s) created.`);
      onOpenChange(false);
    },
    onError: (e) => toast("danger", errorMessage(e)),
  });
  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      wide
      title={`Add script to “${chapter.title}”`}
      description="Paste text and split it into segments. Blank lines separate paragraphs."
      footer={
        <>
          <Button onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="primary" disabled={!text.trim()} loading={save.isPending} onClick={() => save.mutate()}>
            Create segments
          </Button>
        </>
      }
    >
      <div className="grid gap-3">
        <Textarea dir="auto" rows={12} value={text} onChange={(e) => setText(e.target.value)} aria-label="Script" placeholder="Paste your script…" />
        <div className="text-xs text-muted">
          {text.length} characters · {wordCount(text)} words
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Split into" htmlFor="sd-mode">
            <Select id="sd-mode" value={mode} onChange={(e) => setMode(e.target.value as "paragraph" | "sentence")}>
              <option value="paragraph">Paragraphs</option>
              <option value="sentence">Sentences</option>
            </Select>
          </Field>
          <Field label="Existing segments" htmlFor="sd-how">
            <Select id="sd-how" value={how} onChange={(e) => setHow(e.target.value as "append" | "replace")}>
              <option value="append">Keep them, add new segments at the end</option>
              <option value="replace">Replace chapter contents</option>
            </Select>
          </Field>
        </div>
        {how === "replace" && chapter.segments.length > 0 && (
          <Notice tone="warn">
            Segments whose text is unchanged keep their takes. Other existing segments in this chapter, and their takes, are deleted.
          </Notice>
        )}
      </div>
    </Modal>
  );
}
