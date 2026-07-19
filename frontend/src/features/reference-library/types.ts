export type ActiveReference = {
  assetId: number;
  fileName: string;
  mediaType: string;
  classification: string;
  status: string;
  isActive: boolean;
  isFavorite: boolean;
  isCanonical: boolean;
  isProtected: boolean;
  addedAt: string | null;
  lastUsedAt: string | null;
  creatorProfileId: number | null;
  imageUrl: string;
};

export type ReferenceLibraryContext = {
  creator: { id: number; name: string };
  activeReference: ActiveReference | null;
};
