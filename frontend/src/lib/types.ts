export type JobStatus =
  | "queued"
  | "loading_model"
  | "running"
  | "cancelling"
  | "cancelled"
  | "completed"
  | "failed"
  | "interrupted";

export interface Job {
  id: string;
  type: "tts" | "transcribe" | "export" | "model_download";
  lane: string;
  status: JobStatus;
  project_id: string | null;
  segment_id: string | null;
  params: Record<string, unknown>;
  input_revision: number | null;
  progress: number | null;
  progress_stage: string;
  error_code: string | null;
  error_message: string | null;
  retryable: boolean;
  retry_count: number;
  cancel_requested: boolean;
  output_asset_id: string | null;
  result: Record<string, unknown>;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
}

export interface Segment {
  id: string;
  project_id: string;
  chapter_id: string;
  position: number;
  original_text: string;
  normalized_text: string;
  language: string | null;
  text_revision: number;
  voice_profile_id: string | null;
  preset_voice: string | null;
  model_id: string | null;
  speed: number | null;
  pause_after_ms: number;
  selected_take_id: string | null;
  updated_at: string;
  take_count: number;
  selected_take_stale: boolean;
  selected_take_duration: number | null;
  active_job_id: string | null;
  active_job_status: JobStatus | null;
}

export interface Chapter {
  id: string;
  position: number;
  title: string;
  script_text: string;
  segments: Segment[];
}

export interface Pronunciation {
  pattern: string;
  replacement: string;
  language: string | null;
  whole_word: boolean;
  case_sensitive: boolean;
}

export interface ProjectSettings {
  model_id: string | null;
  voice: string | null;
  voice_profile_id: string | null;
  speed: number;
  pause_ms: number;
  segmentation_mode: "paragraph" | "sentence";
  pronunciations: Pronunciation[];
}

export interface Project {
  id: string;
  name: string;
  default_language: string;
  settings: ProjectSettings;
  created_at: string;
  updated_at: string;
  chapters: Chapter[];
}

export interface ProjectSummary {
  id: string;
  name: string;
  default_language: string;
  created_at: string;
  updated_at: string;
  segment_count: number;
  generated_count: number;
}

export interface Take {
  id: string;
  segment_id: string;
  job_id: string | null;
  input_revision: number;
  input_text: string;
  model_id: string;
  model_revision: string;
  voice_label: string;
  generation_parameters: Record<string, unknown>;
  quality: { warnings?: string[]; timings?: Record<string, number>; signal?: Record<string, number> };
  output_asset_id: string;
  created_at: string;
  duration: number | null;
  stale: boolean;
}

export interface VoiceOption {
  id: string;
  label: string;
  language: string;
  gender: string | null;
}

export interface Capabilities {
  kind: "tts" | "asr";
  languages_tested: string[];
  languages_experimental: string[];
  devices: string[];
  preset_voices: VoiceOption[];
  voice_cloning: boolean;
  voice_design: boolean;
  needs_reference_transcript: boolean;
  speed_control: boolean;
  speed_range: [number, number] | null;
  seed_support: boolean;
  deterministic: boolean;
  take_variation: string;
  max_input_chars: number;
  output_sample_rate: number | null;
  progress_reporting: string;
  cancellation: string;
  segment_timestamps: boolean;
  word_timestamps: boolean;
  diarization: boolean;
  notes: string[];
}

export interface ModelInfo {
  id: string;
  name: string;
  kind: "tts" | "asr";
  integration: string;
  verification: string;
  runtime: string | null;
  upstream: { repository: string; model_id: string; version: string } | null;
  revision: string | null;
  license: {
    code: string;
    weights: string;
    third_party?: string;
    gated_terms?: string;
    commercial_use: string;
    commercial_note?: string;
  };
  languages: { verified?: string[]; experimental?: string[]; unevaluated_hidden?: string[]; notes?: string } | null;
  download_size_bytes: number | null;
  installed_size_bytes: number | null;
  reference_audio: string | null;
  status: string;
  integrity_status: string | null;
  bytes_downloaded: number;
  bytes_total: number | null;
  error_message: string | null;
  installed_at: string | null;
  active_job_id: string | null;
  capabilities: Capabilities | null;
  artifact_urls: string[];
}

export interface Voice {
  id: string;
  name: string;
  compatible_engine: string | null;
  compatible_engine_installed: boolean;
  reference_asset_id: string;
  reference_transcript: string;
  language: string;
  tags: string[];
  analysis: {
    warnings?: string[];
    duration?: number;
    peak_dbfs?: number;
    rms_dbfs?: number;
    silence_fraction?: number;
    source?: { codec: string; sample_rate: number; channels: number };
  };
  consent: {
    permission_basis: string;
    statement: string;
    recorded_at: string;
    revoked_at: string | null;
    document_reference: string | null;
  };
  duration: number | null;
  created_at: string;
  updated_at: string;
}

export interface ExportRecord {
  id: string;
  project_id: string | null;
  chapter_id: string | null;
  job_id: string | null;
  file_name: string;
  format: string;
  options: Record<string, unknown>;
  status: string;
  byte_size: number | null;
  duration: number | null;
  sample_rate: number | null;
  details: { warnings?: string[]; error?: string; segments?: number };
  created_at: string;
}

export interface Transcription {
  id: string;
  name: string;
  source_asset_id: string;
  model_id: string;
  language_requested: string | null;
  language_detected: string | null;
  text: string;
  edited_text: string | null;
  segments: { start: number; end: number; text: string }[];
  timestamp_kind: string;
  job_id: string | null;
  job_status: JobStatus | null;
  created_at: string;
  updated_at: string;
}

export interface AppSettings {
  theme: "system" | "light" | "dark";
  default_model_id: string;
  default_voice: string;
  default_language: string;
  default_pause_ms: number;
  segmentation_mode: "paragraph" | "sentence";
  chapter_gap_ms: number;
  show_unevaluated_languages: boolean;
  export_format: "wav" | "mp3";
  mp3_bitrate_kbps: number;
  export_loudnorm: boolean;
  idle_unload_minutes: number;
  analytics_enabled: false;
  log_content: boolean;
}

export interface SystemCapabilities {
  os: string;
  python: string;
  cpu: { name: string; logical_cores: number; physical_cores: number };
  ram: { total_mb: number; available_mb: number };
  gpus: { vendor: string; name: string; vram_total_mb: number; vram_free_mb: number }[];
  cuda_note: string;
  selected_device: string;
  inference_threads: number;
  disk: { free_mb: number; total_mb: number };
  ffmpeg: { ffmpeg: boolean; ffprobe: boolean };
  runtimes: Record<string, string | null>;
  installed_models: string[];
  network_use: string;
  data_dir?: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
