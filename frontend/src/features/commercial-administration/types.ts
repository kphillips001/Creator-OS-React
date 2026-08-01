export type AdminArea = "overview" | "customers" | "catalog" | "sales" | "delivery" | "diagnostics";

export type ExceptionItem = {
  id: string;
  authority: string;
  type: string;
  severity: "Critical" | "High" | "Medium" | "Information";
  explanation: string;
  state: string;
  timestamp?: string | null;
  destination: string;
};

export type SalesSession = {
  salesSessionId: string;
  creatorProfileId: number;
  fanvueUserId: number;
  commercialFoundationType: "PHOTOSHOOT" | "CONVERSATION";
  commercialFoundationReference?: string | null;
  conversationThreadId?: number | null;
  state: string;
  progressionStage: string;
  outcome?: string | null;
  terminalReason?: string | null;
  lastActivityAt?: string | null;
  updatedAt?: string | null;
};

export type Publication = {
  publicationId: string;
  commercialOfferingId: string;
  provider: string;
  status: string;
  externalProductId?: string | null;
  updatedAt: string;
  lastError?: string | null;
  retryCount: number;
  publicationMetadata: Record<string, unknown>;
  providerResourceStatus: string;
  lastReconciledAt?: string | null;
  reconciliationResult?: string | null;
};

export type RoleAssignment = {
  assignmentId: string;
  assetId: number;
  role: string;
  state: string;
  origin: string;
  rationale?: string | null;
  suggestionConfidence?: number | null;
  evidence: Record<string, unknown>;
  updatedAt?: string | null;
};

export type LineageDiagnostics = {
  asset_id: number;
  classification: string;
  roots: { asset_id: number; depth: number }[];
  parents: { asset_id: number; depth: number }[];
  children: { asset_id: number; depth: number }[];
  siblings: { asset_id: number; depth: number }[];
  ancestors: { asset_id: number; depth: number }[];
  descendants: { asset_id: number; depth: number }[];
  family_asset_ids: number[];
  relationships: Record<string, unknown>[];
  photoshoot_contexts: Record<string, unknown>[];
  ambiguous: boolean;
  complete: boolean;
  integrity_status: string;
  provenance_complete: boolean;
  completeness_issues: string[];
};

export type PurchaseIntent = {
  purchaseIntentId: string; creatorProfileId: number; fanvueAccountId: number;
  externalFanvueUserUuid?: string | null; telegramUserId?: number | null;
  commercialOfferingId: string; commercialPublicationId: string;
  provider: string; providerResourceId?: string | null; deliveryUrl?: string | null;
  status: string; attributionResult: string; attributionReason?: string | null;
  createdMetadata: Record<string, unknown>; createdAt?: string | null;
  updatedAt?: string | null; expiresAt?: string | null; purchasedAt?: string | null;
};

export type Fulfillment = {
  offeringId: string; title: string; offeringType: string;
  primarySalesChannel: string; orderedAssetIds: number[]; heroAssetId: number;
  publicationId?: string | null; provider?: string | null;
  providerResourceId?: string | null; deliveryUrl?: string | null;
  publicationStatus?: string | null; providerResourceStatus?: string | null;
  lastReconciledAt?: string | null; fulfillable: boolean;
  ineligibilityReason?: string | null; eligibleForAiChat: boolean;
  eligibleForTelegramWall: boolean;
};

export type SalesDecision = {
  decisionId: string; timestamp?: string | null; customerId: string;
  customerName: string; sellDecision: boolean; productId?: string | null;
  assetId?: string | null; authorizationState: string; reason: string;
  deliveryState: string; outcomeState: string; dataStatus: string;
  warnings: string[]; partialSections: string[];
  [key: string]: unknown;
};

export type AssetAuthority = {
  assetId: number; roles: RoleAssignment[]; lineage?: LineageDiagnostics;
  unavailable?: string;
};
