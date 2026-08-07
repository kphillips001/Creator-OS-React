export type VideoSource = {
  type: "asset" | "generation" | "photoshoot_shot" | "edit_result" | "generated_video" | "upload";
  id: string;
  previewUrl?: string;
  label?: string;
  context?: string;
};

export type VideoSettings = {
  desired_runtime: number;
  aspect_ratio: string;
  resolution: string;
  generate_audio: boolean;
  video_provider: string;
};

export type TimelineBeat = {
  start_second: number; end_second: number; phase: string; creative_beat: string;
  subject_direction?: string; expression_direction?: string; camera_direction?: string;
  environment_direction?: string; audio_direction?: string; continuity_intent?: string;
};

export type VideoConcept = {
  concept_id: string; title: string; overall_theme: string; experience_summary: string;
  tone: string; viewer_experience: string; pacing: string; narrative_arc: string;
  requested_runtime: number; timeline: TimelineBeat[]; origin: string;
};

export type VideoSession = {
  session_id: string; status: string; source_type: string; source_id: string;
  source_asset_id: number | null; source_media_type: string; source_snapshot: Record<string, unknown>;
  settings: VideoSettings; settings_version: number; provider_id: string;
  concept_batches: Array<{ batch_id: string; concepts: VideoConcept[] }>;
  selected_concept: VideoConcept | null; execution_plan: Record<string, unknown> | null;
  current_generation_run: string | null; final_generated_media_id: string | null;
  final_asset_id: number | null; created_at: string; updated_at: string;
};

export type VideoProvider = {
  provider_id: string; display_name: string; model_family: string;
  min_native_duration: number; max_native_duration: number;
  supported_resolutions: string[]; supported_aspect_ratios: string[];
  native_audio: boolean;
};
