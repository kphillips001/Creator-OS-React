import { environment } from "../config/environment";
import type {
  CreatorLifestyleDocument,
  CreatorLifestyleUpdate,
} from "../../features/creator-lifestyle/types";

const endpoint = `${environment.apiBaseUrl}/creator/lifestyle`;

async function read(response: Response): Promise<CreatorLifestyleDocument> {
  const body = await response.json().catch(() => ({})) as
    Partial<CreatorLifestyleDocument> & { detail?: string };
  if (!response.ok || typeof body.creator_profile_id !== "number") {
    throw new Error(body.detail || "Unable to load Lifestyle.");
  }
  return body as CreatorLifestyleDocument;
}

export const creatorLifestyleApi = {
  async get(signal?: AbortSignal): Promise<CreatorLifestyleDocument> {
    return read(await fetch(endpoint, { cache: "no-store", signal }));
  },

  async update(
    document: CreatorLifestyleUpdate,
  ): Promise<CreatorLifestyleDocument> {
    return read(await fetch(endpoint, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(document),
    }));
  },
};
