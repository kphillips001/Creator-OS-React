import { ImagePlus, RefreshCw } from "lucide-react";
import { useState } from "react";
import { LibraryImage } from "../../generation-library/LibraryImage";
import type { PhotoshootTimelineItem } from "../types";
import { PhotoshootImagePreview } from "./PhotoshootImagePreview";

export function PhotoshootTimeline({ items, busy, onReplace }: { items: PhotoshootTimelineItem[]; busy: boolean; onReplace: (requestId: string) => void }) {
  const [selected, setSelected] = useState("");
  const [preview, setPreview] = useState<PhotoshootTimelineItem["image"]>(null);
  const reserved = Math.max(1, 4 - items.length);
  return <section className="photoshoot-card photoshoot-timeline-card" aria-labelledby="photoshoot-timeline-title"><header><h2 id="photoshoot-timeline-title">Photoshoot Timeline</h2><span>This photoshoot grows from left to right.</span></header><div className="photoshoot-timeline">{items.map((item, index) => {
    const invalid = item.status !== "approved";
    const isSelected = selected === item.requestId;
    return <article className={`photoshoot-timeline__shot${index === items.length - 1 ? " photoshoot-timeline__shot--active" : ""}${invalid ? " photoshoot-timeline__shot--invalid" : ""}`} key={`${item.requestId}:${item.image?.image_id || item.status}`}>
      {item.image ? <button aria-label={`Select ${item.label}`} className="photoshoot-timeline__select" onClick={() => { setSelected(isSelected ? "" : item.requestId); if (item.status === "approved") setPreview(item.image); }} type="button"><LibraryImage record={item.image} /></button> : <div className="photoshoot-timeline__replacement"><RefreshCw aria-hidden="true" size={22} /><span>{item.status === "continuity_invalidated" ? "Requires regeneration" : "Replacement in progress"}</span></div>}
      <strong>{item.label}</strong>
      {!item.isSeed && (isSelected || invalid) && <button className="photoshoot-timeline__replace" disabled={busy || item.status === "queued" || item.status === "generating"} onClick={() => onReplace(item.requestId)} type="button">Replace Shot</button>}
    </article>;
  })}{Array.from({ length: reserved }, (_, index) => <div className="photoshoot-timeline__reserved" key={`future-${index}`}><ImagePlus aria-hidden="true" size={22} /><span>Future approved shot</span></div>)}</div>{preview && <PhotoshootImagePreview image={preview} label="Approved Photoshoot image" onClose={() => setPreview(null)} />}</section>;
}
