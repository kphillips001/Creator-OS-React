export type AssetLibraryItem = {
  libraryItemId: string;
  itemKind: "staged_generation" | "registered_asset" | "photoshoot";
  assetId: number | null;
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
  deliverableId?: string | null;
  description?: string | null;
  shotCount?: number | null;
};

export type AssetLibraryResponse = {
  assets: AssetLibraryItem[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
  classifications: string[];
};
