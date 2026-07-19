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
  image: GenerationRecord;
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

export type CreativeDirectorContext = {
  sessionId: string;
  creativeMode: "safe" | "premium" | "explicit";
  creatorGuidance: string;
  workflowStage: string;
  currentPrompt: string;
  ideas: string[];
  selectedInspiration: string;
  recommendation: CreativeDirectorRecommendation | null;
  directionApproved: boolean;
};

export type PhotoshootContext =
  | { status: "profile_missing"; creatorProfileExists: false; seedImage: null; session: null; providers: PhotoshootProvider[]; timeline: [] }
  | { status: "photoshoot_missing"; creatorProfileExists: true; seedImage: null; session: null; providers: PhotoshootProvider[]; timeline: [] }
  | { status: "ready"; creatorProfileExists: true; seedImage: GenerationRecord; session: PhotoshootSessionShell; providers: PhotoshootProvider[]; timeline: PhotoshootTimelineItem[] };
