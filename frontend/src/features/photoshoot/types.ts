import type { GenerationRecord } from "../generation-library/types";

export type PhotoshootProvider = {
  value: string;
  label: string;
};

export type ContinuityLocks = {
  location: boolean;
  wardrobe: boolean;
  lighting: boolean;
  hairstyle: boolean;
  makeup: boolean;
  cameraStyle: boolean;
};

export type PhotoshootSessionShell = {
  sessionId: string;
  title: string;
  providerId: string;
  creativeMode: "safe" | "premium" | "explicit";
  continuityLocks: ContinuityLocks;
  sessionDirection: string;
  creativeHint: string;
  workflowStage: string;
};

export type PhotoshootTimelineItem = {
  requestId: string;
  sequenceIndex: number;
  shotNumber: number;
  label: string;
  isSeed: boolean;
  status: "approved" | "replacement_pending" | "continuity_invalidated" | "queued" | "generating" | string;
  image: GenerationRecord | null;
};

export type CreativeDirectorRecommendation = {
  title: string;
  creative_direction: string;
  reasoning: string;
  continuity_notes: string;
  camera_framing: string;
  lighting: string;
  emotion: string;
  pose_composition: string;
};

export type FreeflowIdeaSet = {
  ideaSetId: string;
  ideas: string[];
  recommendedIdea: string;
  planningShot: number;
  approvedShotCount: number;
  createdAt: string;
  usage: Record<string, string[]>;
};

export type PlanningMode = "frame_by_frame" | "full_plan";

export type PlannedShot = {
  shot_number: number;
  title: string;
  creative_direction: string;
  reasoning?: string;
  emotion?: string;
  camera_framing?: string;
  lighting?: string;
  pose_composition?: string;
  continuity_notes?: string;
  status?: "pending" | "current" | "completed" | string;
};

export type PhotoshootAutoRunState = "READY" | "PREPARING" | "GENERATING" | "WAITING_FOR_REVIEW" |
  "APPROVING" | "ADVANCING" | "PAUSED" | "FAILED" | "PLAN_COMPLETE" | "PHOTOSHOOT_COMPLETE";

export type PhotoshootAutoRunRuntime = {
  session_id: string; auto_run_state: PhotoshootAutoRunState; is_running: boolean; is_paused: boolean;
  is_failed: boolean; plan_complete: boolean; photoshoot_complete: boolean; completed_frames: number;
  total_frames: number; progress_percent: number; current_frame_index: number | null;
  current_frame_number: number | null; current_frame_title: string | null; current_frame_status: string;
  current_request_id: string | null; generation_job_id: string | null; candidate: GenerationRecord | null;
  spinner_active: boolean; waiting_for_review: boolean;
  failure: null | { error_code: string | null; error_message: string; stage: string | null };
  last_updated_at: string | null; auto_approve_enabled: boolean; review_mode: "AUTO_APPROVE" | "MANUAL_REVIEW";
  available_actions: string[];
};

export type PhotoshootDecision = "PENDING" | "APPROVED" | "DECLINED";

export type PhotoshootCurationResult = {
  session_id: string; status: string; already_confirmed: boolean;
  photoshoot_decision: PhotoshootDecision; photoshoot_decided_at: string | null;
  selected_image_ids: string[]; photoshoot_created: boolean;
  photoshoot_deliverable_id: string | null; image_asset_generation_ids: string[];
};

export type PhotoshootCompletionSummary = {
  deliverableId: string | null;
  savedImageCount: number;
};

export type CreativeDirectorContext = {
  sessionId: string;
  creativeMode: "safe" | "premium" | "explicit";
  creatorGuidance: string;
  workflowStage: string;
  currentPrompt: string;
  ideas: string[];
  selectedInspiration: string;
  inspirationEdits: Record<string, string>;
  recommendation: CreativeDirectorRecommendation | null;
  directionApproved: boolean;
  planningMode: PlanningMode;
  planFrameCount: number;
  targetShotCount: number;
  currentShot: number;
  planningShot: number;
  remainingShots: number;
  editorialStage: "Beginning" | "Middle" | "Late" | "Finale" | string;
  plannerExplanation: string;
  sessionPlan: PlannedShot[];
  sessionPlanIndex: number;
  sessionPlanApproved: boolean;
  freeflowIdeaSet: FreeflowIdeaSet | null;
};

export type PhotoshootContext =
  | { status: "profile_missing"; creatorProfileExists: false; seedImage: null; session: null; providers: PhotoshootProvider[]; timeline: [] }
  | { status: "photoshoot_missing"; creatorProfileExists: true; seedImage: null; session: null; providers: PhotoshootProvider[]; timeline: [] }
  | { status: "ready"; creatorProfileExists: true; seedImage: GenerationRecord; session: PhotoshootSessionShell; providers: PhotoshootProvider[]; timeline: PhotoshootTimelineItem[] };
