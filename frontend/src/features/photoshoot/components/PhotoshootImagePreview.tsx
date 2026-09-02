import { X } from "lucide-react";
import { useEffect } from "react";

import { LibraryImage } from "../../generation-library/LibraryImage";
import type { GenerationRecord } from "../../generation-library/types";

export function PhotoshootImagePreview({ image, label, onClose }: { image: GenerationRecord; label: string; onClose: () => void }) {
  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onClose]);

  return <div aria-label={`${label} fullscreen preview`} aria-modal="true" className="photoshoot-image-preview" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }} role="dialog"><button aria-label="Close preview" className="photoshoot-image-preview__close" onClick={onClose} type="button"><X /></button><LibraryImage alt={`${label} preview`} priority src={image.image_url.replace(/\/media(?:\?.*)?$/, "/preview")} /></div>;
}
