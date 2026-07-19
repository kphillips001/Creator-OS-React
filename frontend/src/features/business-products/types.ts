export type ProductSummary = {
  total: number;
  drafts: number;
  needsReview: number;
  readyToPublish: number;
  active: number;
  available: number;
  waitingForMediaLink: number;
  needsAttention: number;
  recommendationEligible: number;
};

export type ProductCompositionAsset = {
  assetId: number;
  fileName: string | null;
  mediaType: string;
  classification: string | null;
  imageUrl: string | null;
};

export type ProductWorkspaceItem = {
  productId: string;
  creatorProfileId: number | null;
  internalName: string;
  displayName: string;
  description: string | null;
  productType: string;
  deliveryType: string;
  productStatus: string;
  approvalStatus: string;
  reviewStatus: string;
  productOrigin: string;
  priceCents: number | null;
  basePriceCents: number | null;
  minPriceCents: number | null;
  maxPriceCents: number | null;
  currency: string;
  tags: string[];
  themes: string[];
  fulfillmentStrategy: string | null;
  fulfillmentStatus: string | null;
  mediaLink: string | null;
  activationSource: string | null;
  activationReason: string | null;
  assetCount: number;
  coverAssetId: number | null;
  previewAssetId: number | null;
  imageUrl: string | null;
  publishingStatus: string;
  publishingDetail: string;
  lifecycleStage: string;
  lifecycle: Record<string, unknown>;
  availabilityStatus: string;
  availability: Record<string, unknown>;
  recommendationEligibility: { eligible: boolean; reason: string | null };
  businessHealth: string;
  business: Record<string, unknown>;
  performance: Record<string, unknown>;
  review: Record<string, unknown>;
  aiPricingRecommendation: Record<string, unknown>;
  composition: ProductCompositionAsset[];
  experience: Record<string, unknown> | null;
  warnings: string[];
};

export type ProductListResponse = {
  items: ProductWorkspaceItem[];
  summary: ProductSummary;
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
};
