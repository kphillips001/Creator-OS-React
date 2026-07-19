import type { PostedContentItem } from "../../features/posted-content/types";

type PostedContentResponse = {
  content_id: string;
  platform: string;
  posted_at: string;
  caption: string;
  creator: string;
  creator_profile_id: number | null;
  generation_library_id: string;
  provider: string;
  prompt: string;
  file_location: string;
  media_url: string;
};

export async function getPostedContent(signal?: AbortSignal): Promise<PostedContentItem[]> {
  const response = await fetch("/api/v1/posted-content", { signal, cache: "no-store" });
  const result = await response.json() as { items?: PostedContentResponse[]; detail?: string };
  if (!response.ok || !result.items) throw new Error(result.detail || "Posted Content could not be loaded.");
  return result.items.map((item) => ({
    contentId: item.content_id,
    platform: item.platform,
    postedAt: item.posted_at,
    caption: item.caption,
    creator: item.creator,
    creatorProfileId: item.creator_profile_id,
    generationLibraryId: item.generation_library_id,
    provider: item.provider,
    prompt: item.prompt,
    fileLocation: item.file_location,
    mediaUrl: item.media_url,
  }));
}
