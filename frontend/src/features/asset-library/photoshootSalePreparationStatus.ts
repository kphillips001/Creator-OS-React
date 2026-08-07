import type { BundleSellingReadiness, SalePreparationReadiness } from "./types";

const isBundleReadiness = (value: SalePreparationReadiness): value is BundleSellingReadiness => "imageCount" in value;

export const readinessBadge = (value?: SalePreparationReadiness | null) => value?.status === "READY"
  ? isBundleReadiness(value) && value.bundleSalesChannel === "CHAT"
    ? value.autonomousSales?.status === "READY" ? "Ready" : value.autonomousSales?.statusLabel || "Needs Setup"
    : "Ready"
  : value?.status === "PREPARING"
    ? "Preparing"
    : value?.status === "NEEDS_ATTENTION"
      ? "Needs Attention"
      : "Not Prepared";

export const readinessBadgeStatus = (value?: SalePreparationReadiness | null) => {
  if (value && isBundleReadiness(value) && value.bundleSalesChannel === "CHAT") {
    return value.autonomousSales?.status === "READY" ? "ready" : "needs_attention";
  }
  return (value?.status || "NOT_PREPARED").toLowerCase();
};
