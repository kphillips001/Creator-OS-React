export type CustomerSummaryMetrics = {
  total: number;
  active: number;
  purchasers: number;
  highValue: number;
  atRisk: number;
  activeSessions: number;
};

export type CustomerWorkspaceItem = {
  customerId: string;
  displayName: string;
  providerIdentities: Array<Record<string, unknown>>;
  relationshipStatus: string;
  relationshipStage: string;
  buyerTier: string | null;
  valueTier: string | null;
  customerHealth: string;
  lifecycleStage: string;
  totalSpendCents: number;
  purchaseCount: number;
  lastActivityAt: string | null;
  retentionRisk: string;
  activeBuyerSession: boolean;
  nextRecommendedAction: string;
  isSubscriber: boolean;
  isFollower: boolean;
  identity?: Record<string, unknown>;
  relationship?: Record<string, unknown>;
  customerValue?: Record<string, unknown>;
  journey?: Record<string, unknown>;
  commerceAndOwnership?: Record<string, unknown>;
  recommendationHistory?: Record<string, unknown>;
  conversationSummary?: Record<string, unknown>;
  buyerSession?: Record<string, unknown>;
  salesSessions?: Record<string, unknown>[];
  retentionAndGrowth?: Record<string, unknown>;
  businessGuidance?: Record<string, unknown>;
  customerIntelligenceProfile?: Record<string, unknown>;
};

export type CustomerListResponse = {
  items: CustomerWorkspaceItem[];
  summary: CustomerSummaryMetrics;
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
};
