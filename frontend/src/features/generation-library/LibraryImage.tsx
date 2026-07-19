import { ImageIcon } from "lucide-react";
import { useState } from "react";

import type { GenerationRecord } from "./types";

export function LibraryImage({ record, src, alt, priority = false }: {
  record?: GenerationRecord;
  src?: string;
  alt?: string;
  priority?: boolean;
}) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <div className="generation-card__image-error">
        <ImageIcon size={24} />
        <span>Image unavailable</span>
      </div>
    );
  }

  return (
    <img
      alt={alt || record?.prompt_text || `Generated image ${record?.image_id || "version"}`}
      decoding="async"
      loading={priority ? "eager" : "lazy"}
      onError={() => setFailed(true)}
      src={src || record?.image_url}
    />
  );
}
