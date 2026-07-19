import { ImagePlus } from "lucide-react";
import { LibraryImage } from "../../generation-library/LibraryImage";
import type { PhotoshootTimelineItem } from "../types";

export function PhotoshootTimeline({ items }: { items: PhotoshootTimelineItem[] }) {
  const reserved = Math.max(1, 4 - items.length);
  return <section className="photoshoot-card photoshoot-timeline-card" aria-labelledby="photoshoot-timeline-title"><header><h2 id="photoshoot-timeline-title">Photoshoot Timeline</h2><span>This photoshoot grows from left to right.</span></header><div className="photoshoot-timeline">{items.map((item, index) => <article className={`photoshoot-timeline__shot${index === items.length - 1 ? " photoshoot-timeline__shot--active" : ""}`} key={`${item.requestId}:${item.image.image_id}`}><div><LibraryImage record={item.image} /></div><strong>{item.label}</strong></article>)}{Array.from({ length: reserved }, (_, index) => <div className="photoshoot-timeline__reserved" key={`future-${index}`}><ImagePlus aria-hidden="true" size={22} /><span>Future approved shot</span></div>)}</div></section>;
}
