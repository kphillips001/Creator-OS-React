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
  sessionSelling?: SessionSellingReadiness | null;
};

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
  status: "NOT_PREPARED" | "PREPARING" | "READY" | "NEEDS_ATTENTION";
  statusLabel: string; paidStepCount: number; readyPaidStepCount: number;
  teaserReady: boolean; steps: SessionSellingStep[];
};

export type AssetLibraryResponse = {
  assets: AssetLibraryItem[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
  classifications: string[];
};
