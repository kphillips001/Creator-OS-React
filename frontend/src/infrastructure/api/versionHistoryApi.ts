import type { GenerationLibraryResponse, GenerationRecord } from "../../features/generation-library/types";
import type { AssetVersion, AssetVersionHistory } from "../../features/version-history/types";

type VersionResponse = {
  generation_library_record_id: string;
  current_version: number;
  versions: Array<{
    generation_library_record_id: string;
    version_number: number;
    is_current: boolean;
    approval_timestamp: string | null;
    provider_id: string;
    prompt: string;
    prompt_plan_id: string;
    generation_metadata: Record<string, unknown>;
    original_file_path: string;
    archived_file_path: string | null;
    edit_source: string;
    image_url: string;
  }>;
};

const mapVersion = (version: VersionResponse["versions"][number]): AssetVersion => ({
  generationLibraryRecordId: version.generation_library_record_id,
  versionNumber: version.version_number,
  isCurrent: version.is_current,
  approvalTimestamp: version.approval_timestamp,
  providerId: version.provider_id,
  prompt: version.prompt,
  promptPlanId: version.prompt_plan_id,
  generationMetadata: version.generation_metadata,
  originalFilePath: version.original_file_path,
  archivedFilePath: version.archived_file_path,
  editSource: version.edit_source,
  imageUrl: version.image_url,
});

async function readCurrentGenerationRecords(signal?: AbortSignal): Promise<GenerationRecord[]> {
  const first = await fetch("/api/generation-library?page=1&sort=newest", { signal, cache: "no-store" });
  const firstResult = await first.json() as GenerationLibraryResponse;
  if (!first.ok || firstResult.error) throw new Error(firstResult.error || "Generation Library could not be loaded.");
  const records = [...firstResult.records];
  for (let page = 2; page <= firstResult.totalPages; page += 1) {
    const response = await fetch(`/api/generation-library?page=${page}&sort=newest`, { signal, cache: "no-store" });
    const result = await response.json() as GenerationLibraryResponse;
    if (!response.ok || result.error) throw new Error(result.error || "Generation Library could not be loaded.");
    records.push(...result.records);
  }
  return records;
}

export async function getVersionHistories(signal?: AbortSignal): Promise<AssetVersionHistory[]> {
  const records = await readCurrentGenerationRecords(signal);
  const histories = await Promise.all(records.map(async (record) => {
    const response = await fetch(`/api/v1/generation-library/${encodeURIComponent(record.image_id)}/versions`, {
      signal, cache: "no-store",
    });
    if (!response.ok) throw new Error(`Version history failed for ${record.image_id}.`);
    const result = await response.json() as VersionResponse;
    return {
      generationLibraryRecordId: result.generation_library_record_id,
      creatorProfileId: record.creator_profile_id ?? null,
      currentVersion: result.current_version,
      versions: result.versions.map(mapVersion),
    };
  }));
  return histories.filter((history) => history.versions.some((version) => !version.isCurrent));
}

export async function restoreAssetVersion(
  imageId: string,
  versionNumber: number,
): Promise<AssetVersionHistory> {
  const endpoint = `/api/v1/generation-library/${encodeURIComponent(imageId)}/versions/${versionNumber}/restore`;
  const response = await fetch(endpoint, { method: "POST" });
  const result = await response.json() as {
    message?: string;
    detail?: string;
    version_history?: VersionResponse;
  };
  if (!response.ok || !result.version_history) {
    throw new Error(result.detail || result.message || "Version restore failed.");
  }
  return {
    generationLibraryRecordId: result.version_history.generation_library_record_id,
    creatorProfileId: null,
    currentVersion: result.version_history.current_version,
    versions: result.version_history.versions.map(mapVersion),
  };
}
