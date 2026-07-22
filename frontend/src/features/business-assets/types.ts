export type BusinessAssetMetrics = {
  recommendation_count: number;
  offer_count: number;
  delivery_count: number;
  purchase_count: number;
  revenue_cents: number;
};

export type BusinessAssetItem = {
  asset_id: number;
  itemKind?: "asset" | "photoshoot";
  deliverableId?: string;
  shotCount?: number;
  description?: string | null;
  asset_name: string | null;
  imageUrl: string;
  analysisStatus: "PENDING" | "NUDENET_RUNNING" | "NUDENET_COMPLETE" | "NUDENET_FAILED" | string;
  downstreamStatus: "ANALYSIS_PENDING" | "ANALYSIS_READY" | "AWAITING_DESTINATION" | "AWAITING_FULFILLMENT" | "CHAT_REGISTRATION_BLOCKED" | "CHAT_INVENTORY_READY" | string;
  commerceStatus: CommerceStatus;
  source_workflow: string | null;
  commerce_destination: string | null;
  current_lifecycle: string | null;
  chat_ready: boolean;
  fulfillment_ready: boolean;
  recommendation_ready: boolean;
  fanvue_upload_status: string | null;
  media_link_status: string | null;
  product_ids: string[];
  experience_ids: string[];
  availability: string;
  waiting_for_media_link: boolean;
  awaiting_destination: boolean;
  blocked: boolean;
  block_reasons: string[];
  warnings: string[];
  lifecycle_steps: [string, string][];
  metrics: BusinessAssetMetrics;
};

export type PhotoshootBusinessDetail = {
  item: BusinessAssetItem;
  photoshootIntelligence: Record<string, unknown>;
  members: { assetId: number; shotOrder: number; imageUrl: string }[];
  commerceStatus: string;
  technical: Record<string, unknown>;
};

export type CommerceStatus = "Analyzing" | "Analysis Failed" | "Ready" | "Needs Upload" | "Needs Media Link" | "Chat Ready";

export type BusinessAssetSummary = {
  total_business_assets: number;
  chat_ready: number;
  fulfillment_ready: number;
  awaiting_destination: number;
  waiting_for_media_link: number;
  blocked: number;
  recommendation_ready: number;
};

export type BusinessAssetListResponse = {
  items: BusinessAssetItem[];
  summary: BusinessAssetSummary;
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
};

export type BusinessAssetDetail = {
  item: BusinessAssetItem;
  asset: Record<string, unknown>;
  contentIntelligence: Record<string, unknown> | null;
  analysis: Record<"NUDENET" | "VISION" | "GROK" | "CONTENT_INTELLIGENCE", string>;
  analysisResults: Record<"NUDENET" | "VISION" | "GROK" | "CONTENT_INTELLIGENCE", Record<string, unknown>>;
  commerceRegistration: Record<string, unknown>;
  destination: { history: Record<string, unknown>[]; routingIntents: Record<string, unknown>[] };
  fulfillment: Record<string, unknown> | null;
  chatCommerce: Record<string, unknown> | null;
};
