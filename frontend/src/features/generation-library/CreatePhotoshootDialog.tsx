import { Check, X } from "lucide-react";
import { useEffect, useState } from "react";

import type { GenerationLibraryCard } from "./types";

export type PhotoshootAssembly = {
  imageIds: string[];
  heroImageId: string;
};

export function CreatePhotoshootDialog({ images, busy, error, onCancel, onCreate }: {
  images: GenerationLibraryCard[];
  busy: boolean;
  error?: string;
  onCancel: () => void;
  onCreate: (value: PhotoshootAssembly) => void;
}) {
  const [heroId, setHeroId] = useState(images[0]?.image_id || "");
  const ordered = images;

  useEffect(() => {
    setHeroId(images[0]?.image_id || "");
  }, [images]);

  return <div className="photoshoot-assembly" role="dialog" aria-modal="true" aria-labelledby="photoshoot-assembly-title">
    <div className="photoshoot-assembly__panel">
      <header>
        <div><small>Asset Library</small><h2 id="photoshoot-assembly-title">Create Photoshoot</h2><p>{images.length} images selected</p></div>
        <button aria-label="Close Create Photoshoot" disabled={busy} onClick={onCancel} type="button"><X size={18} /></button>
      </header>
      <section aria-labelledby="photoshoot-order-title">
        <div><h3 id="photoshoot-order-title">Selected images</h3><p>Images become Shot 1 through Shot {ordered.length} in their current Generation Library order.</p></div>
        <ol className="photoshoot-assembly__images">
          {ordered.map((image, index) => <li key={image.image_id}>
            <div className="photoshoot-assembly__thumbnail"><img alt={`Photoshoot image ${index + 1}`} src={image.image_url} /></div>
            <span>Shot {index + 1}</span>
            <button className={heroId === image.image_id ? "is-cover" : ""} disabled={busy} onClick={() => setHeroId(image.image_id)} type="button">
              {heroId === image.image_id ? <><Check size={14} /> Cover</> : "Use as Cover"}
            </button>
          </li>)}
        </ol>
      </section>
      {error && <p className="photoshoot-assembly__error" role="alert">{error}</p>}
      <footer>
        <button disabled={busy} onClick={onCancel} type="button">Cancel</button>
        <button className="photoshoot-assembly__submit" disabled={busy || ordered.length < 2 || !heroId} onClick={() => onCreate({ imageIds: ordered.map((item) => item.image_id), heroImageId: heroId })} type="button">{busy ? "Creating…" : "Create Photoshoot"}</button>
      </footer>
    </div>
  </div>;
}
