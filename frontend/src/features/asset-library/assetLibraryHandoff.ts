const MOVED_ASSET_HANDOFF_KEY = "creator-os.asset-library.moved-asset-id";

export const storeMovedAssetHandoff = (assetId: number) => {
  window.sessionStorage.setItem(MOVED_ASSET_HANDOFF_KEY, String(assetId));
};

export const consumeMovedAssetHandoff = (): number | null => {
  const value = window.sessionStorage.getItem(MOVED_ASSET_HANDOFF_KEY);
  window.sessionStorage.removeItem(MOVED_ASSET_HANDOFF_KEY);
  if (!value || !/^\d+$/.test(value)) return null;
  const assetId = Number(value);
  return Number.isSafeInteger(assetId) && assetId > 0 ? assetId : null;
};
