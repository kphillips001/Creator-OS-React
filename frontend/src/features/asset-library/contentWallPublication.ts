import type { ContentVaultPublicationState } from "./types";

export const isPostedToContentWall = (
  channel: "CHAT" | "WALL" | null | undefined,
  publication: ContentVaultPublicationState | null | undefined,
) => channel === "WALL" && publication?.status === "PUBLISHED";
