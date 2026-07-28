import { environment } from "../config/environment";
import type {
  SocialCreativeDirectionDocument,
  SocialCreativeDirectionUpdate,
} from "../../features/social-creative-direction/types";

const endpoint = `${environment.apiBaseUrl}/creator/social-creative-direction`;

async function read(response: Response): Promise<SocialCreativeDirectionDocument> {
  const body = await response.json().catch(() => ({})) as
    Partial<SocialCreativeDirectionDocument> & { detail?: string };
  if (!response.ok || typeof body.creator_profile_id !== "number") {
    throw new Error(body.detail || "Unable to load Social Creative Direction.");
  }
  return body as SocialCreativeDirectionDocument;
}

export const socialCreativeDirectionApi = {
  async get(signal?: AbortSignal): Promise<SocialCreativeDirectionDocument> {
    return read(await fetch(endpoint, { cache: "no-store", signal }));
  },

  async update(
    document: SocialCreativeDirectionUpdate,
  ): Promise<SocialCreativeDirectionDocument> {
    return read(await fetch(endpoint, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(document),
    }));
  },
};
