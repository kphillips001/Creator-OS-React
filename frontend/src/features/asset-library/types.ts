export type AssetLibraryItem = {
  libraryItemId: string;
  itemKind: "staged_generation" | "registered_asset" | "photoshoot";
  assetId: number | null;
  displayName?: string;
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
  intelligenceStatus?: string | null;
  intelligenceError?: string | null;
  intelligenceDetails?: AssetIntelligenceDetails;
  standaloneSalePreparation?: StandaloneSalePreparation | null;
  commercialAssets?: CommercialAsset[];
  deliverableId?: string | null;
  description?: string | null;
  shotCount?: number | null;
  sessionSelling?: SalePreparationReadiness | null;
  sellingMode?: PhotoshootSellingMode;
  bundleSalesChannel?: BundleSalesChannel | null;
};

export type AssetIntelligenceDetails = {
  status: "ANALYZING" | "READY" | "PARTIAL" | "FAILED";
  title?: string;
  summary?: string;
  setting?: string;
  environment?: string;
  activity?: string;
  pose?: string;
  expression?: string;
  mood?: string;
  framing?: string;
  cameraAngle?: string;
  lighting?: string;
  atmosphere?: string;
  visualStyle?: string;
  emotionalTone?: string;
  lifestyleContext?: string;
  safetyClassification?: string;
  nudityLevel?: string;
  themes?: string[];
  tags?: string[];
};

export type CommercialAsset = {
  assetId?: number;
  kind: "PROMOTIONAL_TEASER" | "BLURRED_PREVIEW";
  label: string;
  status: string;
  previewUrl: string;
  styleLabel?: string;
  distributionUse?: "CHAT" | "CONTENT_VAULT";
};

export type CommercialTeaser = {
  id: string; distributionUse: "CHAT" | "CONTENT_VAULT";
  teaserStyle: "SELECTIVE_BLUR" | "FULL_BLUR"; status: "READY" | "NEEDS_ATTENTION";
  derivedAssetId?: number | null; previewUrl: string; maskUrl?: string | null;
  maskWidth?: number | null; maskHeight?: number | null; maskVersion?: string | null;
  blurStrength?: number | null;
};

export type StandaloneSalePreparation = {
  assetId: number;
  status: "NOT_PREPARED" | "PREPARING" | "READY" | "NEEDS_ATTENTION";
  statusLabel: string;
  intelligenceReady: boolean;
  blurredTeaserReady: boolean;
  destinations: ("CHAT" | "CONTENT_VAULT")[];
  teaserStyle?: "SELECTIVE_BLUR" | "FULL_BLUR" | null;
  foundationReady: boolean; chatReady: boolean; vaultReady: boolean;
  teasers: CommercialTeaser[]; priceMinor?: number | null; currency?: string | null;
  offeringId?: string | null;
  publicationId?: string | null;
  deliveryUrl?: string | null;
  contentVaultCaption?: ContentVaultCaptionDraft | null;
  contentVaultPublication?: ContentVaultPublicationState | null;
  error?: string | null;
};

export type ContentVaultPublicationState = {
  status: "NOT_PUBLISHED" | "PUBLISHING" | "PUBLISHED" | "FAILED" | "ARCHIVED" | null;
  publishedAt?: string | null;
  providerMessageId?: string | null;
  lastError?: string | null;
  canPublish: boolean;
  configured: boolean;
  readinessError?: string | null;
};

export type ContentVaultCaptionDraft = {
  text: string; style?: string | null; source: "GROK" | "MANUAL";
  updatedAt: string; assetId?: number; photoshootDeliverableId?: string;
  paidImageCount?: number; offeringId: string;
};

export type ContentVaultCaptionTone = "CLASSY" | "RAUNCHY";

export type ContentVaultCaptionOption = {
  text: string;
  style?: string | null;
};

export type PhotoshootSellingMode = "SESSION" | "BUNDLE";
export type BundleSalesChannel = "CHAT" | "CONTENT_WALL";

export type SessionSellingStep = {
  assetId: number; shotOrder: number; position: number; role: string;
  access: "FREE" | "PAID"; ready: boolean; deliveryMethod?: string;
  imageUrl?: string | null; priceLocked?: boolean; priceConflict?: string | null;
  offeringId?: string | null; offeringStatus?: string | null;
  primarySalesChannel?: "AI_CHAT" | "TELEGRAM_WALL" | null;
  publicationId?: string | null; publicationStatus?: string | null;
  providerResourceStatus?: string | null; mediaUuid?: string | null;
  mediaLinkUuid?: string | null; deliveryUrl?: string | null;
  priceMinor?: number | null; currency?: string; publishedAt?: string | null;
  updatedAt?: string | null; error?: string | null;
};

export type SessionSellingReadiness = {
  deliverableId: string; photoshootSessionId: string; strategyVersion: string;
  sellingMode: PhotoshootSellingMode;
  salesChannel?: "CHAT" | "WALL" | null;
  status: "STRATEGY_REQUIRED" | "NOT_PREPARED" | "PREPARING" | "READY" | "NEEDS_ATTENTION" | "NOT_CONFIGURED";
  strategyExists?: boolean; strategyStatus?: "MISSING" | "READY";
  statusLabel: string; paidStepCount: number; readyPaidStepCount: number;
  teaserReady: boolean; steps: SessionSellingStep[];
  strategyOperation?: {
    operationId: string;
    status: "QUEUED" | "RUNNING" | "WAITING_EXTERNAL" | "SUCCEEDED" | "PARTIAL" | "FAILED" | "CANCEL_REQUESTED" | "CANCELLED";
    currentStage?: string | null; stageMessage?: string | null;
    errorCode?: string | null; errorMessage?: string | null;
  } | null;
};

export type BundleSellingReadiness = {
  deliverableId: string; photoshootSessionId: string; sellingMode: "BUNDLE";
  bundleSalesChannel?: BundleSalesChannel;
  salesChannel?: "CHAT" | "WALL" | null;
  status: "NOT_CONFIGURED" | "PREPARING" | "READY" | "NEEDS_ATTENTION";
  statusLabel: string; imageCount: number; priceMinor: number | null; currency: string;
  offeringId?: string | null; publicationId?: string | null;
  publicationStatus?: string | null; providerResourceStatus?: string | null;
  mediaLinkUuid?: string | null; deliveryUrl?: string | null;
  publishedAt?: string | null; updatedAt?: string | null; error?: string | null;
  promotionalTeaser?: BundleTeaserReadiness;
  contentVaultCaption?: ContentVaultCaptionDraft | null;
  contentVaultPublication?: ContentVaultPublicationState | null;
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
