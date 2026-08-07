import { ArrowLeft, Camera, ChevronLeft, ChevronRight, Image as ImageIcon, ImageOff, MoveRight, PackagePlus, Search, Trash2, Video, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { PageHeader } from "../../shared/ui/PageHeader";
import { LibraryActionButton, LibraryActionGroup } from "../../shared/ui/LibraryActionButton";
import { ContainedMediaImage } from "../../shared/ui/ContainedMediaImage";
import { PhotoshootViewer } from "../photoshoot-gallery/PhotoshootViewer";
import { readinessBadge, readinessBadgeStatus } from "./photoshootSalePreparationStatus";
import { photoshootClassificationOptions, photoshootSalesClassification } from "./photoshootSalesClassification";
import type { AssetLibraryItem, AssetLibraryResponse } from "./types";
import "./asset-library.css";
import { videoStudioLink } from "../../infrastructure/api/videoStudioApi";

const emptyResponse: AssetLibraryResponse = {
  assets: [], total: 0, page: 1, pageSize: 18, totalPages: 1, classifications: [],
};

const dateLabel = (value: string | null) => value
  ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value))
  : "Not recorded";

const originalImageUrl = (imageUrl: string | null) => imageUrl
  ?.replace(/\/thumbnail(?:\?.*)?$/, "/media") || null;

type RegistrationResponse = { message?: string; detail?: string; error?: string };
type AssetType = "images" | "photoshoots" | "videos";

const assetTypes = [
  { id: "images" as const, label: "Images", countLabel: "Assets", mediaType: "image", icon: ImageIcon },
  { id: "photoshoots" as const, label: "Photoshoots", countLabel: "Photoshoots", mediaType: "photoshoot", icon: Camera },
  { id: "videos" as const, label: "Videos", countLabel: "Videos", mediaType: "video", icon: Video },
];

const assetTypeFromLocation = (): AssetType | null => {
  const value = new URLSearchParams(window.location.search).get("assetType");
  return assetTypes.some((item) => item.id === value) ? value as AssetType : null;
};

async function readRegistrationResponse(response: Response): Promise<RegistrationResponse> {
  const body = await response.text();
  if (!response.ok) {
    let message = "Unable to register Business Asset.";
    if (body.trim()) {
      try {
        const error = JSON.parse(body) as RegistrationResponse;
        message = error.detail || error.message || error.error || message;
      } catch {
        message = body.trim().startsWith("<")
          ? `Registration service returned HTTP ${response.status}.`
          : body.trim();
      }
    }
    throw new Error(message);
  }
  if (!body.trim()) return {};
  try {
    return JSON.parse(body) as RegistrationResponse;
  } catch {
    throw new Error("Registration service returned an invalid response.");
  }
}

export function AssetLibraryPage() {
  const [data, setData] = useState<AssetLibraryResponse>(emptyResponse);
  const [search, setSearch] = useState("");
  const [assetType, setAssetType] = useState<AssetType | null>(assetTypeFromLocation);
  const [counts, setCounts] = useState<Partial<Record<AssetType, number>>>({});
  const [countsLoading, setCountsLoading] = useState(true);
  const [countsError, setCountsError] = useState(false);
  const [classification, setClassification] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<AssetLibraryItem | null>(null);
  const [preview, setPreview] = useState<AssetLibraryItem | null>(null);
  const [openPhotoshootId, setOpenPhotoshootId] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const [actionMessage, setActionMessage] = useState("");
  const [registeringId, setRegisteringId] = useState<string | null>(null);
  const [archivingId, setArchivingId] = useState<string | null>(null);

  const selectedAssetType = assetTypes.find((item) => item.id === assetType) || null;

  useEffect(() => {
    const onPopState = () => {
      setAssetType(assetTypeFromLocation());
      setPage(1);
      setSearch("");
      setClassification("");
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setCountsLoading(true);
    setCountsError(false);
    Promise.all(assetTypes.map(async (item) => {
      const params = new URLSearchParams({ page: "1", page_size: "1", media_type: item.mediaType });
      const response = await fetch(`/api/v1/assets?${params}`, { cache: "no-store", signal: controller.signal });
      const result = await response.json() as AssetLibraryResponse & { detail?: string };
      if (!response.ok) throw new Error(result.detail || "Unable to load Asset Library counts.");
      return [item.id, result.total] as const;
    }))
      .then((values) => { setCounts(Object.fromEntries(values)); setCountsLoading(false); })
      .catch((reason: unknown) => {
        if ((reason as { name?: string }).name === "AbortError") return;
        setCountsError(true);
        setCountsLoading(false);
      });
    return () => controller.abort();
  }, [version]);

  useEffect(() => {
    if (!selectedAssetType) {
      setData(emptyResponse);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    const params = new URLSearchParams({ page: String(page), page_size: "18" });
    if (search.trim()) params.set("search", search.trim());
    params.set("media_type", selectedAssetType.mediaType);
    if (classification) params.set("classification", classification);
    setLoading(true); setError("");
    fetch(`/api/v1/assets?${params}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const result = await response.json() as AssetLibraryResponse & { detail?: string };
        if (!response.ok) throw new Error(result.detail || "Unable to load Asset Library.");
        return result;
      })
      .then((result) => { setData(result); setLoading(false); })
      .catch((reason: unknown) => {
        if ((reason as { name?: string }).name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Unable to load Asset Library.");
        setLoading(false);
      });
    return () => controller.abort();
  }, [classification, page, search, selectedAssetType, version]);

  const chooseAssetType = (type: AssetType) => {
    const url = new URL(window.location.href);
    url.searchParams.set("assetType", type);
    window.history.pushState({ assetLibraryType: type }, "", url);
    setAssetType(type);
    setPage(1);
    setSearch("");
    setClassification("");
    setSelected(null);
  };

  const backToAssetTypes = () => {
    const url = new URL(window.location.href);
    url.searchParams.delete("assetType");
    window.history.pushState({ assetLibraryType: null }, "", url);
    setAssetType(null);
    setPage(1);
    setSearch("");
    setClassification("");
    setSelected(null);
  };

  const archiveAsset = async (asset: AssetLibraryItem) => {
    const identity = asset.deliverableId || asset.generationId || String(asset.assetId || "");
    if (!identity || archivingId) return;
    setArchivingId(identity); setError(""); setActionMessage("");
    try {
      const endpoint = asset.itemKind === "photoshoot"
        ? `/api/v1/assets/photoshoots/${encodeURIComponent(identity)}/archive`
        : asset.itemKind === "staged_generation"
          ? `/api/v1/assets/staged/${encodeURIComponent(identity)}/archive`
          : `/api/v1/assets/${encodeURIComponent(identity)}/archive`;
      const response = await fetch(endpoint, { method: "POST" });
      const result = await response.json() as { message?: string; detail?: string };
      if (!response.ok) throw new Error(result.detail || "Unable to archive Asset.");
      setSelected(null);
      setActionMessage(result.message || "Asset archived.");
      setVersion((current) => current + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to archive Asset.");
    } finally {
      setArchivingId(null);
    }
  };

  const openAsset = (asset: AssetLibraryItem) => {
    if (asset.itemKind === "photoshoot" && asset.deliverableId) setOpenPhotoshootId(asset.deliverableId);
    else if (asset.itemKind === "registered_asset") void openDetails(asset);
    else setPreview(asset);
  };

  const registerAsset = async (asset: AssetLibraryItem) => {
    const registrationKey = asset.itemKind === "photoshoot" ? asset.deliverableId : asset.generationId;
    if (!registrationKey || registeringId || asset.itemKind === "registered_asset") return;
    setRegisteringId(registrationKey); setError(""); setActionMessage("");
    try {
      const endpoint = asset.itemKind === "photoshoot"
        ? `/api/v1/assets/photoshoots/${encodeURIComponent(registrationKey)}/register`
        : `/api/v1/assets/staged/${encodeURIComponent(registrationKey)}/register`;
      const response = await fetch(endpoint, { method: "POST" });
      const result = await readRegistrationResponse(response);
      setSelected(null);
      setActionMessage(result.message || (asset.itemKind === "photoshoot" ? "Photoshoot registered for Commerce." : "Asset registered. Analysis is pending."));
      setVersion((current) => current + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to register Business Asset.");
    } finally {
      setRegisteringId(null);
    }
  };

  const openDetails = async (asset: AssetLibraryItem) => {
    setSelected(asset); setError("");
    if (asset.itemKind === "staged_generation" || asset.itemKind === "photoshoot" || asset.assetId === null) return;
    try {
      const response = await fetch(`/api/v1/assets/${asset.assetId}`, { cache: "no-store" });
      const result = await response.json() as AssetLibraryItem & { detail?: string };
      if (!response.ok) throw new Error(result.detail || "Unable to load Asset details.");
      setSelected(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load Asset details.");
    }
  };

  const range = useMemo(() => {
    if (!data.total) return "0 assets";
    const first = (data.page - 1) * data.pageSize + 1;
    return `${first}-${Math.min(first + data.assets.length - 1, data.total)} of ${data.total}`;
  }, [data]);

  const synchronizeSessionSelling = useCallback((readiness: NonNullable<AssetLibraryItem["sessionSelling"]>) => {
    setData((current) => ({
      ...current,
      assets: current.assets.map((asset) => asset.deliverableId === readiness.deliverableId
        ? { ...asset, sessionSelling: readiness }
        : asset),
    }));
  }, []);
  const synchronizeSellingMode = useCallback((deliverableId: string, sellingMode: NonNullable<AssetLibraryItem["sellingMode"]>) => {
    setData((current) => ({ ...current, assets: current.assets.map((asset) => asset.deliverableId === deliverableId
      ? { ...asset, sellingMode, sessionSelling: null } : asset) }));
  }, []);

  if (openPhotoshootId) return <PhotoshootViewer deliverableId={openPhotoshootId} enableSessionSelling
    onSessionSellingChange={synchronizeSessionSelling}
    onSellingModeChange={(sellingMode) => synchronizeSellingMode(openPhotoshootId, sellingMode)}
    onClose={() => setOpenPhotoshootId(null)} />;

  return <section className="asset-library-page">
    <PageHeader title="Asset Library" description="Curated generations and registered Creator Assets." />

    {!assetType && <section className="asset-type-dashboard" aria-labelledby="asset-type-heading">
      <header><span>Asset workspace</span><h2 id="asset-type-heading">Choose Asset Type</h2><p>Select a library to manage its assets.</p></header>
      <div className="asset-type-grid">
        {assetTypes.map((item) => <button className="asset-type-card" key={item.id} onClick={() => chooseAssetType(item.id)} type="button">
          <span className="asset-type-card__icon"><item.icon size={34} /></span>
          <span><strong>{item.label}</strong><small>{countsLoading ? "Loading…" : countsError ? "Count unavailable" : `${counts[item.id]} ${item.countLabel}`}</small></span>
        </button>)}
        <a className="asset-type-card" href="/library/bundles">
          <span className="asset-type-card__icon asset-type-card__icon--emoji" aria-hidden="true">📦</span>
          <span><strong>Bundles</strong><small>0 Bundles</small></span>
        </a>
      </div>
    </section>}

    {assetType && <>
      <div className="asset-library-section-header">
        <button onClick={backToAssetTypes} type="button"><ArrowLeft size={17} />Back to Asset Types</button>
        <h2>{selectedAssetType?.label}</h2>
      </div>
      <div className="asset-library-toolbar asset-library-toolbar--section">
        <label className="asset-library-search"><Search size={16} /><span className="sr-only">Search assets</span><input aria-label="Search assets" onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder={`Search ${selectedAssetType?.label.toLowerCase()}`} value={search} /></label>
        <label><span>Classification</span><select aria-label="Classification" onChange={(event) => { setClassification(event.target.value); setPage(1); }} value={classification}>{(assetType === "photoshoots" ? photoshootClassificationOptions : [{ value: "", label: "All classifications" }, ...data.classifications.map((value) => ({ value, label: value }))]).map((option) => <option key={option.value || "all"} value={option.value}>{option.label}</option>)}</select></label>
        <span className="asset-library-range">{range}</span>
      </div>

    {error && <div className="asset-library-state asset-library-state--error" role="alert">{error}</div>}
    {actionMessage && <div className="asset-library-state" role="status">{actionMessage}</div>}
    {loading && <div className="asset-library-state">Loading assets...</div>}
    {!loading && !error && data.assets.length === 0 && <div className="asset-library-state"><ImageOff size={24} /><strong>No assets found.</strong><span>Move an image from Generation Library or adjust the filters.</span></div>}
    {!loading && data.assets.length > 0 && <div className={`asset-library-layout${selected ? "" : " asset-library-layout--cards-only"}`}>
      <div className="asset-library-grid">
        {data.assets.map((asset) => <article className={selected?.libraryItemId === asset.libraryItemId ? "asset-card asset-card--selected" : "asset-card"} key={asset.libraryItemId}>
          <button className="asset-card__image" disabled={!asset.mediaAvailable} onClick={() => openAsset(asset)} type="button" aria-label={`Open ${asset.itemKind === "photoshoot" ? "Photoshoot cover" : selectedAssetType?.label.slice(0, -1) || "Asset"}`}>
            {asset.imageUrl ? <ContainedMediaImage alt={asset.itemKind === "photoshoot" ? asset.fileName || "Photoshoot" : `${selectedAssetType?.label.slice(0, -1) || "Asset"} preview`} loading="lazy" src={asset.imageUrl} /> : <span><ImageOff /><small>Media unavailable</small></span>}
          </button>
          {asset.itemKind === "photoshoot" ? (
            <div className="asset-card__photoshoot"><strong>{asset.fileName}</strong><span>Photoshoot • {asset.shotCount} Images</span><div className="asset-card__photoshoot-badges"><em className={`session-selling-badge session-selling-badge--${readinessBadgeStatus(asset.sessionSelling)}`}>{readinessBadge(asset.sessionSelling)}</em>{photoshootSalesClassification(asset) && <em className="session-selling-badge photoshoot-sales-classification">{photoshootSalesClassification(asset)}</em>}</div></div>
          ) : asset.itemKind === "registered_asset" ? (
            <div className="asset-card__summary">
              <span><strong>Asset #{asset.assetId}</strong>{asset.isCanonicalReference && <em>Canonical reference - Protected</em>}</span>
              <dl><div><dt>Type</dt><dd>{asset.mediaType}</dd></div><div><dt>Classification</dt><dd>{asset.classification || "Unclassified"}</dd></div><div><dt>Registered</dt><dd>{dateLabel(asset.createdAt)}</dd></div></dl>
            </div>
          ) : null}
          <LibraryActionGroup label="Asset actions">
            <LibraryActionButton icon={MoveRight} onClick={() => openAsset(asset)} tooltip={asset.itemKind === "photoshoot" ? "Open Photoshoot" : "Move to Generation Library"} />
            {asset.itemKind !== "photoshoot" && <LibraryActionButton disabled={asset.itemKind === "registered_asset" || Boolean(registeringId)} icon={PackagePlus} onClick={() => void registerAsset(asset)} tooltip="Register Asset" />}
            <LibraryActionButton disabled={Boolean(archivingId)} icon={Trash2} onClick={() => void archiveAsset(asset)} tooltip="Delete" />
            {asset.mediaType === "image" && asset.assetId && <LibraryActionButton icon={Video} onClick={() => { window.location.href = videoStudioLink({ type: "asset", id: String(asset.assetId), previewUrl: asset.imageUrl, label: asset.fileName || `Asset ${asset.assetId}` }); }} tooltip="Create Video" />}
            {asset.mediaType === "video" && asset.assetId && <LibraryActionButton icon={Video} onClick={() => { window.location.href = videoStudioLink({ type: "asset", id: String(asset.assetId), previewUrl: asset.imageUrl, label: asset.fileName || `Video ${asset.assetId}` }); }} tooltip="Extend Video" />}
          </LibraryActionGroup>
        </article>)}
      </div>
      {selected && <aside className="asset-details" aria-label="Selected asset details"><header><div><small>Selected Asset</small><h2>Asset #{selected.assetId}</h2></div><button aria-label="Close asset details" onClick={() => setSelected(null)} type="button"><X size={17} /></button></header><dl><div><dt>Filename</dt><dd>{selected.fileName || "Not recorded"}</dd></div><div><dt>Media type</dt><dd>{selected.mediaType}</dd></div><div><dt>Classification</dt><dd>{selected.classification || "Unclassified"}</dd></div><div><dt>Created</dt><dd>{dateLabel(selected.createdAt)}</dd></div><div><dt>Registration source</dt><dd>{selected.registrationSource || "Existing Creator Asset"}</dd></div><div><dt>Status</dt><dd>{selected.status || "Not recorded"}</dd></div><div><dt>Canonical reference</dt><dd>{selected.isCanonicalReference ? "Yes - Protected" : "No"}</dd></div><div><dt>Tags</dt><dd>{selected.tags.length ? selected.tags.join(", ") : "None"}</dd></div><div><dt>Themes</dt><dd>{selected.themes.length ? selected.themes.join(", ") : "None"}</dd></div></dl></aside>}
    </div>}

    {!loading && data.totalPages > 1 && <nav className="asset-pagination" aria-label="Asset Library pagination"><button disabled={data.page <= 1} onClick={() => setPage((current) => current - 1)} type="button"><ChevronLeft size={16} />Previous</button><span>Page {data.page} of {data.totalPages}</span><button disabled={data.page >= data.totalPages} onClick={() => setPage((current) => current + 1)} type="button">Next<ChevronRight size={16} /></button></nav>}
    {preview && <div className="asset-preview" role="dialog" aria-modal="true" aria-label={`Asset ${preview.assetId} preview`} onMouseDown={(event) => { if (event.target === event.currentTarget) setPreview(null); }}><button aria-label="Close preview" onClick={() => setPreview(null)} type="button"><X /></button><div>{preview.imageUrl ? <ContainedMediaImage alt={`${preview.fileName || `Asset ${preview.assetId}`} preview`} src={originalImageUrl(preview.imageUrl) || preview.imageUrl} /> : <span>Media unavailable</span>}<p>Asset #{preview.assetId}</p></div></div>}
    </>}
  </section>;
}
