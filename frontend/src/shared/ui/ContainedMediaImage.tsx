import type { ImgHTMLAttributes } from "react";
import "./shared-ui.css";

export function ContainedMediaImage({ className = "", ...props }: ImgHTMLAttributes<HTMLImageElement>) {
  return <img loading="lazy" decoding="async" className={["contained-media-image", className].filter(Boolean).join(" ")} {...props} />;
}
