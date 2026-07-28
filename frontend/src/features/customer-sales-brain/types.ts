export type CustomerSalesDecision = {
  creatorProfileId: number;
  fanvueAccountId: number;
  externalFanvueBuyerUuid: string | null;
  telegramUserId: number | null;
  identityResolved: boolean;
  decision: string;
  reasonCode: string;
  reasonSummary: string;
  buyerStage: string;
  commerceSignal: Record<string, unknown>;
  activePurchaseIntentId: string | null;
  activeOfferingId: string | null;
  activeOfferStatus: string | null;
  activeOfferConversionState: string;
  recommendedOfferingId: string | null;
  recommendedPublicationId: string | null;
  recommendedDeliveryUrl: string | null;
  sellAllowed: boolean;
  nudgeAllowed: boolean;
  upsellAllowed: boolean;
  crossSellAllowed: boolean;
  congratulateAllowed: boolean;
  cooldownUntil: string | null;
  evaluatedAt: string;
  decisionMetadata: Record<string, unknown>;
};

export type CustomerSalesDecisionList = {
  items: CustomerSalesDecision[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
};

export type CustomerSalesStatistics = {
  total: number;
  decisionDistribution: Record<string, number>;
  buyerStageDistribution: Record<string, number>;
  currentActiveOffers: number;
  pendingPayments: number;
  unknownAttributions: number;
};
