import { environment } from "../config/environment";
import type { ReferenceLibraryContext } from "../../features/reference-library/types";

type ResponseBody = {
  creator: { id: number; name: string };
  active_reference: null | {
    asset_id: number; file_name: string | null; media_type: string; classification: string | null; status: string | null;
    is_active: boolean; is_favorite: boolean; is_canonical: boolean; is_protected: boolean;
    added_at: string | null; last_used_at: string | null; creator_profile_id: number | null; image_url: string;
  };
};

export async function getActiveReference(signal?: AbortSignal): Promise<ReferenceLibraryContext> {
  const response = await fetch(`${environment.apiBaseUrl}/reference-library/active`, { cache: "no-store", signal });
  const body = await response.json().catch(() => ({})) as Partial<ResponseBody> & { detail?: string };
  if (!response.ok || !body.creator) throw new Error(body.detail || "Unable to load Reference Library.");
  const item = body.active_reference;
  return {
    creator: body.creator,
    activeReference: item ? {
      assetId: item.asset_id, fileName: item.file_name || `Asset ${item.asset_id}`, mediaType: item.media_type,
      classification: item.classification || "Reference", status: item.status || "Unknown", isActive: item.is_active,
      isFavorite: item.is_favorite, isCanonical: item.is_canonical, isProtected: item.is_protected,
      addedAt: item.added_at, lastUsedAt: item.last_used_at, creatorProfileId: item.creator_profile_id,
      imageUrl: item.image_url,
    } : null,
  };
}
