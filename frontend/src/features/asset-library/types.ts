export type AssetLibraryItem = {
  libraryItemId: string;
  itemKind: "staged_generation" | "registered_asset" | "photoshoot";
  assetId: number | null;
  generationId: string | null;
  fileName: string | null;
  mediaType: string;
  classification: string | null;
  status: string | null;
  createdAt: string | null;
  tags: string[];
  themes: string[];
  isReference: boolean;
  isCanonicalReference: boolean;
  mediaAvailable: boolean;
  imageUrl: string | null;
  registrationSource?: string | null;
  prompt?: string | null;
  provider?: string | null;
  deliverableId?: string | null;
  description?: string | null;
  shotCount?: number | null;
  sessionSelling?: SalePreparationReadiness | null;
  sellingMode?: PhotoshootSellingMode;
  bundleSalesChannel?: BundleSalesChannel | null;
};

export type PhotoshootSellingMode = "SESSION" | "BUNDLE";
export type BundleSalesChannel = "CHAT" | "CONTENT_WALL";

export type SessionSellingStep = {
  assetId: number; shotOrder: number; position: number; role: string;
  access: "FREE" | "PAID"; ready: boolean; deliveryMethod?: string;
  imageUrl?: string | null; priceLocked?: boolean; priceConflict?: string | null;
  offeringId?: string | null; offeringStatus?: string | null;
  publicationId?: string | null; publicationStatus?: string | null;
  providerResourceStatus?: string | null; mediaUuid?: string | null;
  mediaLinkUuid?: string | null; deliveryUrl?: string | null;
  priceMinor?: number | null; currency?: string; publishedAt?: string | null;
  updatedAt?: string | null; error?: string | null;
};

export type SessionSellingReadiness = {
  deliverableId: string; photoshootSessionId: string; strategyVersion: string;
  sellingMode: PhotoshootSellingMode;
  status: "STRATEGY_REQUIRED" | "NOT_PREPARED" | "PREPARING" | "READY" | "NEEDS_ATTENTION" | "NOT_CONFIGURED";
  strategyExists?: boolean; strategyStatus?: "MISSING" | "READY";
  statusLabel: string; paidStepCount: number; readyPaidStepCount: number;
  teaserReady: boolean; steps: SessionSellingStep[];
};

export type BundleSellingReadiness = {
  deliverableId: string; photoshootSessionId: string; sellingMode: "BUNDLE";
  bundleSalesChannel?: BundleSalesChannel;
  status: "NOT_CONFIGURED" | "PREPARING" | "READY" | "NEEDS_ATTENTION";
  statusLabel: string; imageCount: number; priceMinor: number | null; currency: string;
  offeringId?: string | null; publicationId?: string | null;
  publicationStatus?: string | null; providerResourceStatus?: string | null;
  mediaLinkUuid?: string | null; deliveryUrl?: string | null;
  publishedAt?: string | null; updatedAt?: string | null; error?: string | null;
  promotionalTeaser?: BundleTeaserReadiness;
  autonomousSales?: {
    status: "READY" | "NEEDS_SETUP" | "DISABLED";
    statusLabel: string; reason: string | null;
  };
};

export type BundleTeaserReadiness = {
  status: "NOT_CONFIGURED" | "READY" | "NEEDS_ATTENTION"; statusLabel: string;
  commercialRole: "BUNDLE_PROMOTIONAL_TEASER"; sourceAssetId: number | null;
  teaserAssetId: number | null; blurStrength: number; maskWidth: number | null;
  maskHeight: number | null; maskVersion: string; maskUrl: string | null;
  previewUrl: string | null; error: string | null;
  candidates: { assetId: number; shotOrder: number; imageUrl: string }[];
};

export type SalePreparationReadiness = SessionSellingReadiness | BundleSellingReadiness;

export type AssetLibraryResponse = {
  assets: AssetLibraryItem[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
  classifications: string[];
};
