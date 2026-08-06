import type { SessionSellingReadiness } from "./types";

export const readinessBadge = (value?: SessionSellingReadiness | null) => value?.status === "READY"
  ? "Ready"
  : value?.status === "PREPARING"
    ? "Preparing"
    : value?.status === "NEEDS_ATTENTION"
      ? "Needs Attention"
      : "Not Prepared";
