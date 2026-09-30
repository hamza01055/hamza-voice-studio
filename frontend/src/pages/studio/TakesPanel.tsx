import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Circle, Info, Pause, Play, Trash2 } from "lucide-react";
import { useState } from "react";
import { usePlayer } from "../../components/Player";
import { Badge, IconButton, Modal, Skeleton, Spinner, useToast } from "../../components/ui";
import { api, errorMessage } from "../../lib/api";
import { fmtDate, fmtDuration } from "../../lib/format";
import { patchSegmentInCache, qk, useTakes } from "../../lib/queries";
import type { Segment, Take } from "../../lib/types";

export function TakesPanel({ seg, index }: { seg: Segment; index: number }) {
  const takes = useTakes(seg.id);
  const qc = useQueryClient();
  const toast = useToast();
  const player = usePlayer();
  const [details, setDetails] = useState<Take | null>(null);
  const select = useMutation({
    mutationFn: (takeId: string | null) => api.post<Segment>(`/segments/${seg.id}/selected-take`, { take_id: takeId }),
    onSuccess: (s) => {
      patchSegmentInCache(qc, s);
      qc.invalidateQueries({ queryKey: qk.takes(seg.id) });
    },
    onError: (e) => toast("danger", errorMessage(e)),
  });
  const del = useMutation({
    mutationFn: (takeId: string) => api.del(`/takes/${takeId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.takes(seg.id) });
      qc.invalidateQueries({ queryKey: qk.project(seg.project_id) });
    },
    onError: (e) => toast("danger", errorMessage(e)),
  });

  if (takes.isLoading) return <Skeleton className="h-10" />;
  const items = [...(takes.data?.items ?? [])].reverse();
  if (items.length === 0) return <div className="px-1 py-2 text-xs text-muted">No takes yet.</div>;
  return (
    <>
      <ul className="flex flex-col gap-1" aria-label={`Takes for segment ${index + 1}`}>
        {items.map((t, i) => {
          const selected = takes.data?.selected_take_id === t.id;
          const isPlaying = player.playing && player.current?.assetId === t.output_asset_id;
          const warnings = t.quality?.warnings ?? [];
          return (
            <li
              key={t.id}
              className={`flex items-center gap-2 rounded-lg border px-2 py-1.5 text-sm ${selected ? "border-accent/50 bg-accent-soft/60" : "border-line bg-panel"}`}
            >
              <IconButton
                label={isPlaying ? "Pause take" : "Play take"}
                icon={isPlaying ? <Pause className="size-4" /> : <Play className="size-4" />}
                onClick={() =>
                  isPlaying
                    ? player.toggle()
                    : player.play({
                        assetId: t.output_asset_id,
                        title: `Segment ${index + 1} · Take ${items.length - i}`,
                        subtitle: `${t.voice_label} · ${fmtDuration(t.duration)}`,
                      })
                }
              />
              <span className="w-14 font-medium">Take {items.length - i}</span>
              <span className="font-mono text-xs text-muted tabular-nums">{fmtDuration(t.duration)}</span>
              <span className="truncate text-xs text-muted">{t.voice_label}</span>
              {t.stale && (
                <Badge tone="warn" title="The segment text changed after this take was generated">
                  Older text
                </Badge>
              )}
              {warnings.length > 0 && (
                <Badge tone="warn" title={warnings.join("\n")}>
                  {warnings.length} warning{warnings.length > 1 ? "s" : ""}
                </Badge>
              )}
              <div className="ml-auto flex items-center gap-0.5">
                <IconButton label="Take details" icon={<Info className="size-4" />} onClick={() => setDetails(t)} />
                <IconButton
                  label={selected ? "Used in export (click to unselect)" : "Use this take in export"}
                  icon={
                    select.isPending && select.variables === t.id ? (
                      <Spinner />
                    ) : selected ? (
                      <CheckCircle2 className="size-4 text-accent" />
                    ) : (
                      <Circle className="size-4" />
                    )
                  }
                  onClick={() => select.mutate(selected ? null : t.id)}
                />
                <IconButton
                  label="Delete take"
                  icon={<Trash2 className="size-4" />}
                  onClick={() => {
                    if (window.confirm("Delete this take and its audio file?")) del.mutate(t.id);
                  }}
                />
              </div>
            </li>
          );
        })}
      </ul>
      <Modal open={!!details} onOpenChange={(o) => !o && setDetails(null)} title="Take details" wide>
        {details && (
          <div className="grid gap-3 text-sm">
            <div>
              <div className="text-xs font-medium text-muted">Text used for generation (revision {details.input_revision})</div>
              <p dir="auto" className="rtl-text mt-1 rounded-lg bg-panel-2 p-3">
                {details.input_text}
              </p>
              {details.stale && <p className="mt-1 text-xs text-warn">The segment text has changed since this take was made.</p>}
            </div>
            <dl className="grid grid-cols-[160px_1fr] gap-x-3 gap-y-1.5">
              <dt className="text-muted">Model</dt>
              <dd>{details.model_id}</dd>
              <dt className="text-muted">Model revision</dt>
              <dd className="break-all">{details.model_revision}</dd>
              <dt className="text-muted">Voice</dt>
              <dd>{details.voice_label}</dd>
              <dt className="text-muted">Parameters</dt>
              <dd className="font-mono text-xs break-all">{JSON.stringify(details.generation_parameters)}</dd>
              <dt className="text-muted">Seed</dt>
              <dd>Not supported by this model (repeat takes can differ slightly).</dd>
              <dt className="text-muted">Timings</dt>
              <dd className="font-mono text-xs">{JSON.stringify(details.quality?.timings ?? {})}</dd>
              <dt className="text-muted">Created</dt>
              <dd>{fmtDate(details.created_at)}</dd>
            </dl>
            {(details.quality?.warnings ?? []).length > 0 && (
              <ul className="list-disc pl-5 text-warn">
                {details.quality.warnings!.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </Modal>
    </>
  );
}
