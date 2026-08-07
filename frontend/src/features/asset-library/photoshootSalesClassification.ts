import type { AssetLibraryItem } from "./types";

export type PhotoshootSalesClassification = "CHAT" | "SESSION" | "WALL";

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
