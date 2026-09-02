import type { AssetLibraryItem } from "./types";
import { isPostedToContentWall } from "./contentWallPublication";

export type PhotoshootSalesClassification = "CHAT" | "SESSION" | "WALL";

export type PhotoshootCommercialBadges = {
  channel?: "CHAT" | "WALL";
  sellingMode: "SESSION" | "BUNDLE";
  posted?: boolean;
};

export function photoshootCommercialBadges(
  value: Pick<AssetLibraryItem, "sellingMode" | "bundleSalesChannel" | "sessionSelling">,
): PhotoshootCommercialBadges | null {
  const readiness = value.sessionSelling;
  const sellingMode = value.sellingMode || readiness?.sellingMode;
  if (sellingMode === "SESSION") {
    if (!readiness || ["NOT_PREPARED", "NOT_CONFIGURED", "STRATEGY_REQUIRED"].includes(readiness.status)) {
      return { sellingMode: "SESSION" };
    }
    const persistedPaidSteps = "steps" in readiness
      ? readiness.steps.filter((step) => step.access === "PAID" && Boolean(step.offeringId))
      : [];
    const persistedStepChannels = "steps" in readiness
      ? new Set(persistedPaidSteps
        .map((step) => step.primarySalesChannel)
        .filter(Boolean))
      : new Set();
    const sessionChannel = readiness.salesChannel
      || (persistedStepChannels.size === 1 && persistedStepChannels.has("AI_CHAT") ? "CHAT" : null)
      // Compatibility for the pre-projection Session response currently served
      // by long-running backends. Session preparation only creates AI_CHAT
      // offerings, so persisted paid offering IDs are authoritative evidence.
      || (readiness.status === "READY" && persistedPaidSteps.length > 0 ? "CHAT" : null);
    return sessionChannel === "CHAT"
      ? { channel: "CHAT", sellingMode: "SESSION" }
      : { sellingMode: "SESSION" };
  }
  if (sellingMode !== "BUNDLE") return null;
  if (!readiness || ["NOT_PREPARED", "NOT_CONFIGURED", "STRATEGY_REQUIRED"].includes(readiness.status)) {
    return { sellingMode: "BUNDLE" };
  }
  const channel = value.bundleSalesChannel === "CONTENT_WALL" ? "WALL"
    : value.bundleSalesChannel === "CHAT" ? "CHAT"
      : readiness.salesChannel || null;
  return channel ? {
    channel, sellingMode: "BUNDLE",
    posted: "contentVaultPublication" in readiness
      && isPostedToContentWall(channel, readiness.contentVaultPublication),
  } : null;
}

export function photoshootSalesClassification(value: Pick<AssetLibraryItem, "sellingMode" | "bundleSalesChannel">): PhotoshootSalesClassification | null {
  if (value.sellingMode === "SESSION") return "SESSION";
  if (value.sellingMode !== "BUNDLE") return null;
  if (value.bundleSalesChannel === "CHAT") return "CHAT";
  if (value.bundleSalesChannel === "CONTENT_WALL") return "WALL";
  return null;
}

export const photoshootClassificationOptions: ReadonlyArray<{
  value: "" | PhotoshootSalesClassification;
  label: string;
}> = [
  { value: "", label: "All classifications" },
  { value: "CHAT", label: "Chat" },
  { value: "SESSION", label: "Session" },
  { value: "WALL", label: "Wall" },
];
