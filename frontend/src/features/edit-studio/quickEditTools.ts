import { Crop } from "lucide-react";

export const quickEditTools = [{ id: "crop" as const, title: "Crop", description: "Trim and reframe the image", icon: Crop }];
export type CropBox = { x: number; y: number; width: number; height: number };
export type CropHandle = "move" | "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";

export function calculateCropDrag(start: CropBox, handle: CropHandle, dx: number, dy: number, bounds: { width: number; height: number }): CropBox {
  let { x, y, width, height } = start; const min = 16;
  if (handle === "move") {
    x = Math.max(0, Math.min(bounds.width - width, x + dx));
    y = Math.max(0, Math.min(bounds.height - height, y + dy));
  } else {
    if (handle.includes("e")) width = Math.max(min, Math.min(bounds.width - x, start.width + dx));
    if (handle.includes("s")) height = Math.max(min, Math.min(bounds.height - y, start.height + dy));
    if (handle.includes("w")) { const nx = Math.max(0, Math.min(start.x + start.width - min, start.x + dx)); width = start.width + start.x - nx; x = nx; }
    if (handle.includes("n")) { const ny = Math.max(0, Math.min(start.y + start.height - min, start.y + dy)); height = start.height + start.y - ny; y = ny; }
  }
  return { x, y, width, height };
}
