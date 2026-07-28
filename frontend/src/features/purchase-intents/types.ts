export type PurchaseIntentStatus =
  | "CREATED" | "PRESENTED" | "CLICKED" | "PURCHASED"
  | "EXPIRED" | "ABANDONED" | "UNKNOWN" | "SUPERSEDED";

export type PurchaseIntent = {
  purchaseIntentId: string;
  creatorProfileId: number;
  fanvueAccountId: number;
  telegramIdentityMappingId: number;
  telegramUserId: number;
  telegramChatId: number;
  externalFanvueUserUuid: string | null;
  commercialOfferingId: string;
  commercialPublicationId: string;
  provider: string;
  providerResourceId: string;
  deliveryUrl: string;
  telegramMessageId: number | null;
  conversationId: string | null;
  correlationId: string;
  expectedPriceMinor: number;
  expectedCurrency: string;
  status: PurchaseIntentStatus;
  createdAt: string;
  presentedAt: string | null;
  clickedAt: string | null;
  expiresAt: string;
  abandonedAt: string | null;
  purchasedAt: string | null;
  providerTransactionOrderId: string | null;
  providerPaymentId: string | null;
  providerEventId: string | null;
  attributionResult: "PENDING" | "ATTRIBUTED" | "UNKNOWN";
  attributionReason: string | null;
  createdMetadata: Record<string, unknown>;
  updatedAt: string;
};

export type PurchaseIntentList = {
  items: PurchaseIntent[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
};

export type PurchaseIntentStatistics = {
  total: number;
  active: number;
  purchased: number;
  expired: number;
  abandoned: number;
  unknown: number;
  superseded: number;
};
