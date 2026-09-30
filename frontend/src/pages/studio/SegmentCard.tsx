import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  ArrowDown,
  ArrowUp,
  ChevronDown,
  ChevronRight,
  CircleStop,
  Play,
  Redo2,
  RefreshCw,
  Scissors,
  Sparkles,
  Trash2,
  Undo2,
  Wand2,
} from "lucide-react";
import { useRef, useState } from "react";
import { usePlayer } from "../../components/Player";
import { Badge, Button, IconButton, Notice, Progress, useToast } from "../../components/ui";
import { api, errorMessage } from "../../lib/api";
import { isActive, useLiveJob } from "../../lib/events";
import { fmtDuration, JOB_STATUS_LABEL, wordCount } from "../../lib/format";
import { patchSegmentInCache, qk } from "../../lib/queries";
import type { Segment } from "../../lib/types";
import { useGenerate, useSegmentEditor } from "./hooks";
import { TakesPanel } from "./TakesPanel";

export function SegmentCard({
  seg,
  index,
  total,
  focused,
  onFocus,
  checked,
  onCheck,
  maxChars,
  voiceLabel,
  takeVariation,
}: {
  seg: Segment;
  index: number;
  total: number;
  focused: boolean;
  onFocus: () => void;
  checked: boolean;
  onCheck: (v: boolean) => void;
  maxChars: number;
  voiceLabel: string;
  takeVariation: string;
}) {
  const ed = useSegmentEditor(seg);
  const qc = useQueryClient();
  const toast = useToast();
  const player = usePlayer();
  const gen = useGenerate();
  const [showTakes, setShowTakes] = useState(false);
  const [showNorm, setShowNorm] = useState(false);
  const ta = useRef<HTMLTextAreaElement>(null);
  const live = useLiveJob(seg.active_job_id);
  const jobStatus = live?.status ?? seg.active_job_status;
  const running = isActive(jobStatus);

  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.patch<Segment>(`/segments/${seg.id}`, body),
    onSuccess: (s) => {
      patchSegmentInCache(qc, s);
      qc.invalidateQueries({ queryKey: qk.project(seg.project_id) });
    },
    onError: (e) => toast("danger", errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: () => api.del(`/segments/${seg.id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.project(seg.project_id) }),
    onError: (e) => toast("danger", errorMessage(e)),
  });
  const split = useMutation({
    mutationFn: (at: number) => api.post(`/segments/${seg.id}/split`, { at }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.project(seg.project_id) }),
    onError: (e) => toast("danger", errorMessage(e)),
  });
  const cancel = useMutation({
    mutationFn: (jobId: string) => api.post(`/jobs/${jobId}/cancel`),
    onError: (e) => toast("danger", errorMessage(e)),
  });

  const generate = (takes = 1) => {
    ed.flush();
    gen.mutate(
      { segment_ids: [seg.id], takes },
      {
        onSuccess: (r) => {
          if (r.skipped.length) toast("warn", r.skipped[0].reason);
          else setShowTakes(true);
        },
        onError: (e) => toast("danger", errorMessage(e)),
      },
    );
  };

  const over = ed.text.length > maxChars;
  let statusBadge;
  if (running) {
    statusBadge = <Badge tone="accent">{JOB_STATUS_LABEL[jobStatus!]}</Badge>;
  } else if (seg.selected_take_id && seg.selected_take_stale) {
    statusBadge = (
      <Badge tone="warn" title="The text changed after the selected take was generated. Regenerate to update it.">
        Text changed since take
      </Badge>
    );
  } else if (seg.selected_take_id) {
    statusBadge = <Badge tone="ok">Take selected · {fmtDuration(seg.selected_take_duration)}</Badge>;
  } else if (seg.take_count > 0) {
    statusBadge = <Badge tone="warn">No take selected</Badge>;
  } else {
    statusBadge = <Badge>Not generated</Badge>;
  }

  return (
    <article
      id={`seg-${seg.id}`}
      aria-label={`Segment ${index + 1}`}
      onFocusCapture={onFocus}
      className={clsx(
        "group rounded-xl border bg-panel transition-colors",
        focused ? "border-accent/60 shadow-[0_0_0_3px_var(--accent-soft)]" : "border-line",
      )}
    >
      <header className="flex items-center gap-2 px-3 pt-2.5">
        <input
          type="checkbox"
          aria-label={`Select segment ${index + 1}`}
          checked={checked}
          onChange={(e) => onCheck(e.target.checked)}
          className="size-4 accent-[var(--accent)]"
        />
        <span className="font-mono text-xs text-muted tabular-nums">#{index + 1}</span>
        {statusBadge}
        <span className="truncate text-xs text-muted">{voiceLabel}</span>
        <span className="ml-auto text-xs text-muted" aria-live="polite">
          {ed.state === "saving" ? "Saving…" : ed.state === "dirty" ? "Unsaved changes" : ed.state === "error" ? "" : "Saved"}
        </span>
        <div className="flex items-center opacity-70 group-focus-within:opacity-100 group-hover:opacity-100">
          <IconButton label="Undo (Ctrl+Z)" icon={<Undo2 className="size-4" />} onClick={ed.undo} disabled={!ed.canUndo} />
          <IconButton label="Redo (Ctrl+Shift+Z)" icon={<Redo2 className="size-4" />} onClick={ed.redo} disabled={!ed.canRedo} />
          <IconButton label="Move up" icon={<ArrowUp className="size-4" />} disabled={index === 0} onClick={() => patch.mutate({ position: index - 1 })} />
          <IconButton label="Move down" icon={<ArrowDown className="size-4" />} disabled={index === total - 1} onClick={() => patch.mutate({ position: index + 1 })} />
          <IconButton
            label="Split at cursor"
            icon={<Scissors className="size-4" />}
            onClick={() => {
              const at = ta.current?.selectionStart ?? 0;
              if (ed.state !== "saved") {
                toast("info", "Wait for the text to save, then split.");
                ed.flush();
                return;
              }
              if (at <= 0 || at >= ed.text.length) toast("info", "Place the cursor inside the text where you want to split.");
              else split.mutate(at);
            }}
          />
          <IconButton
            label="Delete segment"
            icon={<Trash2 className="size-4" />}
            onClick={() => {
              const msg = seg.take_count
                ? `Delete segment ${index + 1} and its ${seg.take_count} take(s)? Their audio files are removed.`
                : `Delete segment ${index + 1}?`;
              if (window.confirm(msg)) remove.mutate();
            }}
          />
        </div>
      </header>

      {ed.draft != null && (
        <div className="px-3 pt-2">
          <Notice tone="warn" title="Unsaved edit found">
            An edit to this segment was not saved before the studio closed.{" "}
            <button className="font-medium text-accent underline" onClick={ed.restoreDraft}>
              Restore it
            </button>{" "}
            or{" "}
            <button className="underline" onClick={ed.discardDraft}>
              discard
            </button>
            .
          </Notice>
        </div>
      )}

      <div className="px-3 pt-2">
        <textarea
          ref={ta}
          dir="auto"
          aria-label={`Text of segment ${index + 1}`}
          value={ed.text}
          onChange={(e) => ed.change(e.target.value)}
          onBlur={ed.flush}
          onKeyDown={(e) => {
            const mod = e.ctrlKey || e.metaKey;
            if (mod && e.key.toLowerCase() === "z") {
              e.preventDefault();
              if (e.shiftKey) ed.redo();
              else ed.undo();
            } else if (mod && e.key.toLowerCase() === "y") {
              e.preventDefault();
              ed.redo();
            } else if (mod && e.key === "Enter") {
              e.preventDefault();
              generate();
            }
          }}
          rows={Math.min(10, Math.max(2, Math.ceil(ed.text.length / 95) + (ed.text.match(/\n/g)?.length ?? 0)))}
          className="w-full resize-y rounded-lg border border-transparent bg-transparent px-1 py-1 text-[15px] leading-relaxed focus:border-line focus:bg-panel-2/40 focus:outline-none"
        />
        {ed.error && <p className="text-xs text-danger">Not saved: {ed.error}</p>}
      </div>

      {running && (
        <div className="px-4 pb-1">
          <div className="mb-1 flex justify-between text-xs text-muted">
            <span>{live?.progress_stage ?? JOB_STATUS_LABEL[jobStatus!]}</span>
            {live?.progress != null && <span>{Math.round(live.progress * 100)}%</span>}
          </div>
          <Progress value={jobStatus === "queued" ? null : (live?.progress ?? null)} label={`Segment ${index + 1} generation`} />
        </div>
      )}

      <footer className="flex flex-wrap items-center gap-2 px-3 pt-1 pb-2.5">
        <span className={clsx("text-xs tabular-nums", over ? "font-medium text-danger" : "text-muted")}>
          {ed.text.length}/{maxChars} chars · {wordCount(ed.text)} words
        </span>
        <button
          className="flex items-center gap-1 text-xs text-muted hover:text-fg"
          onClick={() => setShowNorm((v) => !v)}
          aria-expanded={showNorm}
        >
          <Wand2 className="size-3.5" /> {showNorm ? "Hide" : "Show"} spoken text
        </button>
        <label className="flex items-center gap-1 text-xs text-muted">
          Pause after
          <input
            type="number"
            min={0}
            max={20000}
            step={100}
            defaultValue={seg.pause_after_ms}
            onBlur={(e) => {
              const v = Number(e.target.value);
              if (v !== seg.pause_after_ms && v >= 0 && v <= 20000) patch.mutate({ pause_after_ms: v });
            }}
            className="w-16 rounded border border-line bg-panel px-1 py-0.5 text-right text-xs"
            aria-label={`Pause after segment ${index + 1} in milliseconds`}
          />
          ms
        </label>
        <div className="ml-auto flex items-center gap-1.5">
          {seg.selected_take_id && !running && (
            <Button
              size="sm"
              variant="ghost"
              icon={<Play className="size-4" />}
              onClick={async () => {
                const t = await api.get<{ items: { id: string; output_asset_id: string }[] }>(`/segments/${seg.id}/takes`);
                const take = t.items.find((x) => x.id === seg.selected_take_id);
                if (take) player.play({ assetId: take.output_asset_id, title: `Segment ${index + 1}`, subtitle: "Selected take" });
              }}
            >
              Play
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setShowTakes((v) => !v)}
            aria-expanded={showTakes}
            icon={showTakes ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
          >
            Takes ({seg.take_count})
          </Button>
          {running && seg.active_job_id ? (
            <Button
              size="sm"
              icon={<CircleStop className="size-4" />}
              disabled={jobStatus === "cancelling"}
              loading={cancel.isPending}
              onClick={() => cancel.mutate(seg.active_job_id!)}
              title="Cancellation takes effect after the current sentence."
            >
              {jobStatus === "cancelling" ? "Cancelling…" : "Cancel"}
            </Button>
          ) : (
            <Button
              size="sm"
              variant={seg.take_count ? "secondary" : "primary"}
              icon={seg.take_count ? <RefreshCw className="size-4" /> : <Sparkles className="size-4" />}
              loading={gen.isPending}
              disabled={over || !ed.text.trim()}
              onClick={() => generate()}
              title="Ctrl+Enter"
            >
              {seg.take_count ? "New take" : "Generate"}
            </Button>
          )}
        </div>
      </footer>

      {showNorm && (
        <div className="mx-3 mb-2.5 rounded-lg bg-panel-2 px-3 py-2 text-sm">
          <div className="mb-1 text-xs font-medium text-muted">
            Spoken text (normalised, revision {seg.text_revision}) — your script above is never changed
          </div>
          <p dir="auto" className="rtl-text">
            {seg.normalized_text || <span className="text-muted">Empty</span>}
          </p>
        </div>
      )}
      {showTakes && (
        <div className="border-t border-line px-3 py-2.5">
          <TakesPanel seg={seg} index={index} />
          {takeVariation === "subtle" && seg.take_count > 0 && (
            <p className="mt-2 text-xs text-muted">
              With this model, new takes at the same settings differ only subtly. Change the voice or speed for a clearly different
              read.
            </p>
          )}
        </div>
      )}
    </article>
  );
}
