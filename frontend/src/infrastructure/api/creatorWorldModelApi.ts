import { environment } from "../config/environment";
import type {
  CreatorWorldModelDocument,
  CreatorWorldModelUpdate,
} from "../../features/creator-world-model/types";

const endpoint = `${environment.apiBaseUrl}/creator/world-model`;

async function read(response: Response): Promise<CreatorWorldModelDocument> {
  const body = await response.json().catch(() => ({})) as
    Partial<CreatorWorldModelDocument> & { detail?: string };
  if (!response.ok || typeof body.creator_profile_id !== "number") {
    throw new Error(body.detail || "Unable to load World Model.");
  }
  return body as CreatorWorldModelDocument;
}

export const creatorWorldModelApi = {
  async get(signal?: AbortSignal): Promise<CreatorWorldModelDocument> {
    return read(await fetch(endpoint, { cache: "no-store", signal }));
  },

  async update(
    document: CreatorWorldModelUpdate,
  ): Promise<CreatorWorldModelDocument> {
    return read(await fetch(endpoint, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(document),
    }));
  },
};
