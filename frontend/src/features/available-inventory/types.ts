export type AvailableInventoryItem = {
  assetId: number;
  displayName: string;
  thumbnailUrl: string;
  previewUrl: string;
  mediaType: string;
  createdAt: string | null;
  registrationState: string;
  readiness: string;
  contentDestination: string;
  sourceWorkflow: string;
  sourceName: string;
  sourceSessionId: string | null;
  shortDescription: string | null;
};

export type AvailableInventoryResponse = {
  items: AvailableInventoryItem[];
  total: number;
  ready: number;
  pending: number;
  page: number;
  pageSize: number;
  totalPages: number;
};
