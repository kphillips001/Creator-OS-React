export type CommercialOffering = {
  offeringId: string;
  offeringType: string;
  title: string;
  description: string | null;
  heroAssetId: number;
  heroUrl: string;
  primarySalesChannel: string;
  priceMinor: number | null;
  currency: string;
  status: string;
  assetCount: number;
  assets: Array<{ assetId: number; position: number; isHero: boolean }>;
  createdAt: string;
  updatedAt: string;
};

export type CommercialOfferingList = {
  items: CommercialOffering[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
};

export type CommercialPublication = {
  publicationId: string;
  commercialOfferingId: string;
  provider: string;
  status: string;
  externalProductId: string | null;
  publishedAt: string | null;
  createdAt: string;
  updatedAt: string;
  lastError: string | null;
  retryCount: number;
  publicationMetadata: Record<string, unknown>;
  providerResourceStatus: string;
  lastReconciledAt: string | null;
  reconciliationResult: string | null;
};

export type CommercialFulfillment = {
  offeringId: string;
  offeringType: string;
  primarySalesChannel: string;
  priceMinor: number | null;
  currency: string;
  provider: string | null;
  providerResourceId: string | null;
  deliveryUrl: string | null;
  publicationStatus: string | null;
  providerResourceStatus: string;
  lastReconciledAt: string | null;
  publishedAt: string | null;
  fulfillable: boolean;
  ineligibilityReason: string | null;
  eligibleForAiChat: boolean;
  eligibleForTelegramWall: boolean;
};
