import clsx from "clsx";
import { Pause, Play, Square, Volume2 } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { assetUrl } from "../lib/api";
import { fmtDuration } from "../lib/format";

export interface PlayItem {
  assetId: string;
  title: string;
  subtitle?: string;
}

interface PlayerApi {
  current: PlayItem | null;
  playing: boolean;
  play: (item: PlayItem) => void;
  toggle: () => void;
  stop: () => void;
}

const Ctx = createContext<PlayerApi>({ current: null, playing: false, play: () => {}, toggle: () => {}, stop: () => {} });
export const usePlayer = () => useContext(Ctx);

const peaksCache = new Map<string, Float32Array>();

async function loadPeaks(assetId: string, bars: number): Promise<Float32Array> {
  const key = `${assetId}:${bars}`;
  const hit = peaksCache.get(key);
  if (hit) return hit;
  const res = await fetch(assetUrl(assetId));
  const buf = await res.arrayBuffer();
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  const ctx = new Ctor();
  try {
    const audio = await ctx.decodeAudioData(buf);
    const data = audio.getChannelData(0);
    const step = Math.max(1, Math.floor(data.length / bars));
    const peaks = new Float32Array(bars);
    for (let i = 0; i < bars; i++) {
      let m = 0;
      const end = Math.min(data.length, (i + 1) * step);
      for (let j = i * step; j < end; j++) m = Math.max(m, Math.abs(data[j]));
      peaks[i] = m;
    }
    peaksCache.set(key, peaks);
    return peaks;
  } finally {
    void ctx.close();
  }
}

function Waveform({ assetId, progress, onSeek }: { assetId: string; progress: number; onSeek: (f: number) => void }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [peaks, setPeaks] = useState<Float32Array | null>(null);
  useEffect(() => {
    let alive = true;
    setPeaks(null);
    loadPeaks(assetId, 240)
      .then((p) => alive && setPeaks(p))
      .catch(() => alive && setPeaks(new Float32Array(0)));
    return () => {
      alive = false;
    };
  }, [assetId]);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    const w = c.clientWidth;
    const h = c.clientHeight;
    c.width = w * dpr;
    c.height = h * dpr;
    const g = c.getContext("2d");
    if (!g) return;
    g.scale(dpr, dpr);
    g.clearRect(0, 0, w, h);
    const styles = getComputedStyle(document.documentElement);
    const accent = styles.getPropertyValue("--accent").trim() || "#4f46e5";
    const dim = styles.getPropertyValue("--border").trim() || "#ccc";
    if (!peaks || peaks.length === 0) {
      g.fillStyle = dim;
      g.fillRect(0, h / 2 - 1, w, 2);
      g.fillStyle = accent;
      g.fillRect(0, h / 2 - 1, w * progress, 2);
      return;
    }
    const max = Math.max(0.01, ...peaks);
    const bw = w / peaks.length;
    peaks.forEach((p, i) => {
      const bh = Math.max(2, (p / max) * (h - 4));
      g.fillStyle = i / peaks.length < progress ? accent : dim;
      g.fillRect(i * bw + 0.5, (h - bh) / 2, Math.max(1, bw - 1), bh);
    });
  }, [peaks, progress]);
  return (
    <canvas
      ref={ref}
      className="h-10 w-full cursor-pointer"
      aria-hidden
      onClick={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        onSeek((e.clientX - r.left) / r.width);
      }}
    />
  );
}

export function PlayerProvider({ children }: { children: ReactNode }) {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [current, setCurrent] = useState<PlayItem | null>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [dur, setDur] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const a = new Audio();
    a.preload = "auto";
    audio.current = a;
    const upd = () => setTime(a.currentTime);
    a.addEventListener("timeupdate", upd);
    a.addEventListener("loadedmetadata", () => setDur(a.duration));
    a.addEventListener("play", () => setPlaying(true));
    a.addEventListener("pause", () => setPlaying(false));
    a.addEventListener("ended", () => setPlaying(false));
    a.addEventListener("error", () => {
      setPlaying(false);
      setError("This audio could not be played.");
    });
    return () => {
      a.pause();
      a.src = "";
    };
  }, []);

  const play = useCallback((item: PlayItem) => {
    const a = audio.current;
    if (!a) return;
    setError(null);
    setCurrent(item);
    setTime(0);
    setDur(0);
    a.src = assetUrl(item.assetId);
    void a.play().catch(() => setPlaying(false));
  }, []);
  const toggle = useCallback(() => {
    const a = audio.current;
    if (!a || !a.src) return;
    if (a.paused) void a.play();
    else a.pause();
  }, []);
  const stop = useCallback(() => {
    const a = audio.current;
    if (!a) return;
    a.pause();
    a.currentTime = 0;
  }, []);

  const seek = (f: number) => {
    const a = audio.current;
    if (a && dur) a.currentTime = Math.max(0, Math.min(dur, f * dur));
  };

  return (
    <Ctx.Provider value={{ current, playing, play, toggle, stop }}>
      {children}
      <div
        className="flex h-16 shrink-0 items-center gap-3 border-t border-line bg-panel px-4"
        role="region"
        aria-label="Audio player"
      >
        <button
          onClick={toggle}
          disabled={!current}
          aria-label={playing ? "Pause" : "Play"}
          className="flex size-9 items-center justify-center rounded-full bg-accent text-accent-fg disabled:opacity-40"
        >
          {playing ? <Pause className="size-4" /> : <Play className="size-4 translate-x-px" />}
        </button>
        <button
          onClick={stop}
          disabled={!current}
          aria-label="Stop"
          className="flex size-8 items-center justify-center rounded-full text-muted hover:bg-panel-2 disabled:opacity-40"
        >
          <Square className="size-3.5" />
        </button>
        <div className="w-52 min-w-0 shrink-0">
          <div className="truncate text-sm font-medium">{current?.title ?? "Nothing playing"}</div>
          <div className={clsx("truncate text-xs", error ? "text-danger" : "text-muted")}>
            {error ?? current?.subtitle ?? "Select a take to preview it"}
          </div>
        </div>
        <div className="min-w-0 flex-1">
          {current ? (
            <Waveform assetId={current.assetId} progress={dur ? time / dur : 0} onSeek={seek} />
          ) : (
            <div className="h-0.5 w-full rounded bg-line" />
          )}
        </div>
        <input
          type="range"
          min={0}
          max={dur || 0}
          step={0.01}
          value={time}
          disabled={!current}
          onChange={(e) => audio.current && (audio.current.currentTime = Number(e.target.value))}
          aria-label="Seek"
          className="sr-only focus:not-sr-only"
        />
        <div className="w-32 shrink-0 text-right font-mono text-xs tabular-nums text-muted">
          {fmtDuration(time)} / {fmtDuration(dur)}
        </div>
        <Volume2 className="size-4 text-muted" aria-hidden />
      </div>
    </Ctx.Provider>
  );
}
