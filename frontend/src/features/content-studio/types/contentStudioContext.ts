export type ContentStudioContextStatus =
  | "profile_missing"
  | "reference_missing"
  | "ready";

export type ContentStudioContext = {
  status: ContentStudioContextStatus;
  creatorProfileExists: boolean;
  activeReference: {
    assetId: number;
    lastUsedAt: string | null;
  } | null;
};
