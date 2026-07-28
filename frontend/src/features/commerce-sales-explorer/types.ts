export type CommerceSale = {
  offeringId: string;
  title: string;
  description: string | null;
  offeringType: "SINGLE_IMAGE" | "PHOTOSET" | "VIDEO";
  priceMinor: number;
  currency: string;
  primarySalesChannel: "AI_CHAT";
  heroAssetId: number;
  heroUrl: string;
  deliveryUrl: string;
  provider: string;
  providerResourceId: string;
  publishedAt: string;
  status: "FULFILLABLE";
};

export type CommerceSalesResponse = {
  items: CommerceSale[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
};

