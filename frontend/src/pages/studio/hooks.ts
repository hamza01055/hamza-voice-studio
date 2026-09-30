import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage } from "../../lib/api";
import { patchSegmentInCache, qk } from "../../lib/queries";
import type { Segment } from "../../lib/types";

export type SaveState = "saved" | "dirty" | "saving" | "error";

const draftKey = (id: string) => `hvs.draft.${id}`;

function readDraft(id: string): { text: string; rev: number } | null {
  try {
    const raw = localStorage.getItem(draftKey(id));
    return raw ? (JSON.parse(raw) as { text: string; rev: number }) : null;
  } catch {
    return null;
  }
}
function writeDraft(id: string, text: string, rev: number) {
  try {
    localStorage.setItem(draftKey(id), JSON.stringify({ text, rev }));
  } catch {
    /* storage unavailable */
  }
}
function clearDraft(id: string) {
  try {
    localStorage.removeItem(draftKey(id));
  } catch {
    /* ignore */
  }
}

/**
 * Local editing state for one segment: debounced autosave, undo/redo history and a
 * crash-safe local draft that can be restored after a restart.
 */
export function useSegmentEditor(seg: Segment) {
  const qc = useQueryClient();
  const [text, setText] = useState(seg.original_text);
  const [state, setState] = useState<SaveState>("saved");
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<string | null>(() => {
    const d = readDraft(seg.id);
    return d && d.text !== seg.original_text ? d.text : null;
  });
  const past = useRef<string[]>([]);
  const future = useRef<string[]>([]);
  const lastPush = useRef(0);
  const timer = useRef<number | undefined>(undefined);
  const latest = useRef(text);
  latest.current = text;

  // Server-side change (e.g. split, reload) while we have no local edits.
  useEffect(() => {
    if (state === "saved" && seg.original_text !== latest.current) setText(seg.original_text);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seg.original_text]);

  const save = useCallback(
    async (value: string) => {
      setState("saving");
      try {
        const updated = await api.patch<Segment>(`/segments/${seg.id}`, { original_text: value });
        patchSegmentInCache(qc, updated);
        if (latest.current === value) {
          setState("saved");
          clearDraft(seg.id);
        } else setState("dirty");
        setError(null);
        qc.invalidateQueries({ queryKey: qk.takes(seg.id) });
      } catch (e) {
        setState("error");
        setError(errorMessage(e));
      }
    },
    [qc, seg.id],
  );

  const schedule = useCallback(
    (value: string) => {
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => void save(value), 800);
    },
    [save],
  );

  const change = useCallback(
    (value: string) => {
      const now = Date.now();
      if (now - lastPush.current > 700) {
        past.current.push(latest.current);
        if (past.current.length > 200) past.current.shift();
        lastPush.current = now;
      }
      future.current = [];
      setText(value);
      setState("dirty");
      writeDraft(seg.id, value, seg.text_revision);
      schedule(value);
    },
    [schedule, seg.id, seg.text_revision],
  );

  const undo = useCallback(() => {
    const prev = past.current.pop();
    if (prev === undefined) return;
    future.current.push(latest.current);
    setText(prev);
    setState("dirty");
    writeDraft(seg.id, prev, seg.text_revision);
    schedule(prev);
    lastPush.current = 0;
  }, [schedule, seg.id, seg.text_revision]);

  const redo = useCallback(() => {
    const next = future.current.pop();
    if (next === undefined) return;
    past.current.push(latest.current);
    setText(next);
    setState("dirty");
    writeDraft(seg.id, next, seg.text_revision);
    schedule(next);
  }, [schedule, seg.id, seg.text_revision]);

  const flush = useCallback(() => {
    if (state === "dirty") {
      window.clearTimeout(timer.current);
      void save(latest.current);
    }
  }, [save, state]);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const restoreDraft = () => {
    if (draft != null) change(draft);
    setDraft(null);
  };
  const discardDraft = () => {
    clearDraft(seg.id);
    setDraft(null);
  };

  return {
    text,
    state,
    error,
    change,
    undo,
    redo,
    flush,
    canUndo: past.current.length > 0,
    canRedo: future.current.length > 0,
    draft,
    restoreDraft,
    discardDraft,
  };
}

export function useGenerate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { segment_ids: string[]; takes?: number; only_missing?: boolean }) =>
      api.post<{ jobs: { job_id: string; segment_id: string; deduplicated: boolean }[]; skipped: { segment_id: string; reason: string }[] }>(
        "/generations",
        { ...body, idempotency_key: `ui-${Date.now()}-${Math.random().toString(36).slice(2)}` },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["project"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}
