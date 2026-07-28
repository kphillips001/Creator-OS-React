export type OfferingEvaluation = {
  offeringId: string;
  title: string;
  eligible: boolean;
  exclusionReasons: string[];
  publicationId: string | null;
  publicationProvider: string | null;
  publicationStatus: string | null;
  deliveryUrlAvailable: boolean;
  offeringStatus: string;
  offeringType: string;
  primarySalesChannel: string;
  publishedAt: string | null;
};

export type OfferingSelection = {
  buyer: {
    externalFanvueBuyerUuid: string | null;
    telegramUserId: number | null;
    displayName: string | null;
    handle: string | null;
  };
  selectedOffering: {
    offeringId: string;
    title: string | null;
    publicationId: string;
    publicationProvider: string | null;
    deliveryUrl: string | null;
    offeringType: string | null;
    primarySalesChannel: string | null;
  } | null;
  selectionReason: string;
  exclusionReasons: string[];
  evaluations: OfferingEvaluation[];
  selectorMetadata: Record<string, unknown>;
};

export type OfferingSelectionList = {
  items: OfferingSelection[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
};
