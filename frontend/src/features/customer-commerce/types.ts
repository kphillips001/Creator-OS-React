export type CustomerCommerceProfile = {
  profileId: string;
  creatorProfileId: number;
  fanvueAccountId: number;
  externalFanvueUserUuid: string;
  telegramIdentityMappingId: number | null;
  telegramUserId: number | null;
  displayName: string | null;
  handle: string | null;
  firstSeenAt: string;
  lastSeenAt: string;
  firstPurchaseAt: string | null;
  lastPurchaseAt: string | null;
  lifetimeGrossMinor: number;
  lifetimeNetMinor: number;
  purchaseCount: number;
  averageOrderValueMinor: number;
  largestPurchaseMinor: number;
  lastTransactionOrderId: string | null;
  lastPaymentStatus: string | null;
  lastPurchaseSource: string | null;
  lastSyncedAt: string | null;
  profileState:
    | "UNKNOWN" | "PROSPECT" | "LEAD" | "FIRST_PURCHASE"
    | "REPEAT_BUYER" | "VIP" | "HIGH_VALUE" | "INACTIVE";
  createdAt: string;
  updatedAt: string;
};

export type CustomerCommerceListResponse = {
  items: CustomerCommerceProfile[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
};

export type CustomerCommerceStatistics = {
  profileCount: number;
  buyerCount: number;
  lifetimeGrossMinor: number;
  lifetimeNetMinor: number;
  purchaseCount: number;
  averageOrderValueMinor: number;
  largestPurchaseMinor: number;
};

export type CommerceSignal = {
  buyerUuid: string;
  telegramUserId: number | null;
  identityResolved: boolean;
  lifetimeSpendMinor: number;
  purchaseCount: number;
  lastPurchaseAt: string | null;
  currentActiveOfferId: string | null;
  currentOfferStatus: string | null;
  conversionState: string;
  latestTransaction: string | null;
  attributionState: string;
  reconciliationState: string | null;
};
