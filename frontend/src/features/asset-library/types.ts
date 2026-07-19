export type AssetLibraryItem = {
  assetId: number;
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
};

export type AssetLibraryResponse = {
  assets: AssetLibraryItem[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
  classifications: string[];
};
