import type { CreatorIntelligence } from "./types";

export async function loadCreatorIntelligence(signal?: AbortSignal): Promise<CreatorIntelligence> {
  const response = await fetch("/api/v1/creator-intelligence", { cache: "no-store", signal });
  const body = await response.json() as CreatorIntelligence & { detail?: string };
  if (!response.ok) throw new Error(body.detail || "Unable to load Creator Intelligence.");
  return body;
}
