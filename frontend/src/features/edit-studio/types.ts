import type { GenerationRecord } from "../generation-library/types";

export type EditStudioProvider = {
  value: string;
  label: string;
};

export type EditStudioContext =
  | { status: "profile_missing"; creatorProfileExists: false; pendingImage: null; candidateImage: null; providers: EditStudioProvider[] }
  | { status: "image_missing"; creatorProfileExists: true; pendingImage: null; candidateImage: null; providers: EditStudioProvider[] }
  | { status: "ready"; creatorProfileExists: true; pendingImage: GenerationRecord; candidateImage: GenerationRecord | null; providers: EditStudioProvider[] };

export type EditMode = "single_image" | "multi_image";
export type ReferenceSource = "upload" | "reference_library";

export type EditStudioReferenceAsset = {
  assetId: number;
  label: string;
  previewUrl: string;
};

export type EditStudioReferenceDraft = {
  id: string;
  source: ReferenceSource;
  assetId: number | null;
  file: File | null;
};
