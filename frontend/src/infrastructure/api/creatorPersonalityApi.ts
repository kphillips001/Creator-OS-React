import { environment } from "../config/environment";
import type {
  CreatorPersonality,
  CreatorPersonalityUpdate,
} from "../../features/creator-personality/types";

const endpoint = `${environment.apiBaseUrl}/creator/personality`;

async function readResponse(response: Response): Promise<CreatorPersonality> {
  const body = await response.json().catch(() => ({})) as
    Partial<CreatorPersonality> & { detail?: string };
  if (!response.ok || typeof body.id !== "number") {
    throw new Error(body.detail || "Unable to load Creator Personality.");
  }
  return body as CreatorPersonality;
}

export const creatorPersonalityApi = {
  async get(signal?: AbortSignal): Promise<CreatorPersonality> {
    return readResponse(await fetch(endpoint, {
      cache: "no-store",
      signal,
    }));
  },

  async update(
    profile: CreatorPersonalityUpdate,
  ): Promise<CreatorPersonality> {
    return readResponse(await fetch(endpoint, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(profile),
    }));
  },
};
