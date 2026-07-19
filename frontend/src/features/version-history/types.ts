export type AssetVersion = {
  generationLibraryRecordId: string;
  versionNumber: number;
  isCurrent: boolean;
  approvalTimestamp: string | null;
  providerId: string;
  prompt: string;
  promptPlanId: string;
  generationMetadata: Record<string, unknown>;
  originalFilePath: string;
  archivedFilePath: string | null;
  editSource: string;
  imageUrl: string;
};

export type AssetVersionHistory = {
  generationLibraryRecordId: string;
  creatorProfileId: number | null;
  currentVersion: number;
  versions: AssetVersion[];
};
