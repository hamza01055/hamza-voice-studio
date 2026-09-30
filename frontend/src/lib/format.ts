export const LANGUAGE_NAMES: Record<string, string> = {
  "en-us": "English (US)",
  "en-gb": "English (UK)",
  en: "English",
  es: "Spanish",
  fr: "French",
  hi: "Hindi",
  it: "Italian",
  "pt-br": "Portuguese (Brazil)",
  pt: "Portuguese",
  zh: "Chinese (Mandarin)",
  ja: "Japanese",
  ur: "Urdu",
  "ur-latn": "Roman Urdu",
  ar: "Arabic",
  de: "German",
};

export function langName(code: string | null | undefined): string {
  if (!code) return "Auto";
  return LANGUAGE_NAMES[code] ?? code;
}

export function fmtDuration(sec: number | null | undefined): string {
  if (sec == null || !isFinite(sec)) return "–";
  const s = Math.max(0, sec);
  const m = Math.floor(s / 60);
  const r = s - m * 60;
  if (m >= 60) {
    const h = Math.floor(m / 60);
    return `${h}:${String(m % 60).padStart(2, "0")}:${String(Math.floor(r)).padStart(2, "0")}`;
  }
  return `${m}:${r.toFixed(1).padStart(4, "0")}`;
}

export function fmtBytes(n: number | null | undefined): string {
  if (n == null) return "unknown";
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(0)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(0)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function wordCount(text: string): number {
  const t = text.trim();
  return t ? t.split(/\s+/u).length : 0;
}

export function hasRtl(text: string): boolean {
  return /[֐-ࣿיִ-﷿ﹰ-﻿]/u.test(text);
}

export const JOB_STATUS_LABEL: Record<string, string> = {
  queued: "Queued",
  loading_model: "Loading model",
  running: "Generating",
  cancelling: "Cancelling",
  cancelled: "Cancelled",
  completed: "Completed",
  failed: "Failed",
  interrupted: "Interrupted",
};

export const COMMERCIAL_LABEL: Record<string, string> = {
  permitted: "Commercial use permitted",
  permitted_with_notice: "Commercial use permitted (see notice)",
  research_only_until_clarified: "Research only (licence unclear)",
  prohibited: "Non-commercial only",
};
