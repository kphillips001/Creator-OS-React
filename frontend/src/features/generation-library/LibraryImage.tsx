import { ImageIcon } from "lucide-react";
import { useState } from "react";

import type { GenerationLibraryCard, GenerationRecord } from "./types";

export function LibraryImage({ record, src, alt, priority = false }: {
  record?: GenerationRecord | GenerationLibraryCard | Pick<GenerationRecord, "image_id" | "image_url">;
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
      alt={alt || ("prompt_text" in (record || {}) ? (record as GenerationRecord).prompt_text : "") || `Generated image ${record?.image_id || "version"}`}
      decoding="async"
      loading={priority ? "eager" : "lazy"}
      onError={() => setFailed(true)}
      src={src || record?.image_url?.replace(/\/media(?:\?.*)?$/, "/thumbnail")}
    />
  );
}
