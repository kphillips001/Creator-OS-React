import {
  ArrowLeft,
  ArrowRightLeft,
  ArrowRight,
  BadgeDollarSign,
  Camera,
  ChevronLeft,
  ChevronRight,
  Copy,
  ExternalLink,
  Image as ImageIcon,
  ImageOff,
  Megaphone,
  Heart,
  MessageCircle,
  MoveRight,
  PackagePlus,
  Search,
  Trash2,
  Video,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { PageHeader } from "../../shared/ui/PageHeader";
import {
  LibraryActionButton,
  LibraryActionGroup,
} from "../../shared/ui/LibraryActionButton";
import { ContainedMediaImage } from "../../shared/ui/ContainedMediaImage";
import { PhotoshootViewer } from "../photoshoot-gallery/PhotoshootViewer";
import {
  readinessBadge,
  readinessBadgeStatus,
} from "./photoshootSalePreparationStatus";
import {
  photoshootClassificationOptions,
  photoshootCommercialBadges,
} from "./photoshootSalesClassification";
import { StandaloneSalePreparationDialog } from "./StandaloneSalePreparationDialog";
import { isPostedToContentWall } from "./contentWallPublication";
import type { AssetLibraryItem, AssetLibraryResponse, ContentVaultCaptionDraft, ContentVaultCaptionOption, ContentVaultCaptionTone, ContentVaultPublicationState, StandaloneSalePreparation } from "./types";
import "./asset-library.css";
import { videoStudioLink } from "../../infrastructure/api/videoStudioApi";
import { consumeMovedAssetHandoff } from "./assetLibraryHandoff";

const emptyResponse: AssetLibraryResponse = {
  assets: [],
  total: 0,
  page: 1,
  pageSize: 18,
  totalPages: 1,
  classifications: [],
};

const photoshootFromLocation = () => new URLSearchParams(window.location.search).get("photoshoot");

const CAPTION_TONE_STORAGE_KEY = "creator-os.content-vault-caption-tone";

const readStoredCaptionTone = (): ContentVaultCaptionTone => {
  try {
    const value = window.sessionStorage.getItem(CAPTION_TONE_STORAGE_KEY);
    if (value === "CLASSY" || value === "RAUNCHY") return value;
  } catch {
    // Ignore sessionStorage failures (private mode / blocked storage).
  }
  return "CLASSY";
};

const dateLabel = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(
        new Date(value),
      )
    : "Not recorded";

const moneyLabel = (minor: number, currency?: string | null) => {
  const code = String(currency || "USD").trim().toUpperCase();
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency: code }).format(minor / 100);
  } catch {
    return `${code} ${(minor / 100).toFixed(2)}`;
  }
};

const commercialPriceLabel = (asset: AssetLibraryItem) => {
  const price = asset.commercialPrice;
  if (price?.status === "PRICED" && price.amountMinor != null) {
    return `${moneyLabel(price.amountMinor, price.currency)}${price.kind === "SESSION_TOTAL" ? " Total" : ""}`;
  }
  if (price?.status === "INCOMPLETE") return "Pricing Incomplete";
  if (asset.itemKind === "registered_asset") {
    const preparation = asset.standaloneSalePreparation;
    if (preparation?.status === "READY" && preparation.priceMinor != null && preparation.priceMinor > 0) {
      return moneyLabel(preparation.priceMinor, preparation.currency);
    }
  }
  return "Not Priced";
};

const assetClassificationLabel = (value: string | null) =>
  value
    ? value
        .toLowerCase()
        .split("_")
        .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
        .join(" ")
    : "Unclassified";

const NON_TERMINAL_INTELLIGENCE_STATES = new Set([
  "REGISTERED",
  "PENDING",
  "NUDENET_PENDING",
  "NUDENET_RUNNING",
  "NUDENET_COMPLETE",
  "VISION_PENDING",
  "VISION_RUNNING",
  "VISION_COMPLETE",
  "GROK_PENDING",
  "GROK_RUNNING",
  "GROK_COMPLETE",
  "CONTENT_INTELLIGENCE_PENDING",
  "CONTENT_INTELLIGENCE_RUNNING",
  "CONTENT_INTELLIGENCE_COMPLETE",
  "ANALYZING",
]);

const isIntelligenceInProgress = (status?: string | null) =>
  NON_TERMINAL_INTELLIGENCE_STATES.has(
    String(status || "PENDING").trim().toUpperCase(),
  );

const intelligenceStatusLabel = (status?: string | null) => {
  const normalized = String(status || "PENDING").trim().toUpperCase();
  if (NON_TERMINAL_INTELLIGENCE_STATES.has(normalized)) return "ANALYZING";
  if (normalized === "READY") return "READY";
  if (normalized === "PARTIAL") return "PARTIAL";
  if (normalized === "FAILED" || normalized.endsWith("_FAILED")) return "FAILED";
  return normalized
    .toLowerCase()
    .split("_")
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(" ");
};

const standalonePreparationLabel = (
  status: NonNullable<AssetLibraryItem["standaloneSalePreparation"]>["status"],
) =>
  ({
    NOT_PREPARED: "Not Prepared",
    PREPARING: "Preparing",
    READY: "Ready",
    NEEDS_ATTENTION: "Needs Attention",
  })[status];

const StandaloneDestinationBadges = ({
  destinations,
  posted = false,
}: {
  destinations: NonNullable<
    AssetLibraryItem["standaloneSalePreparation"]
  >["destinations"];
  posted?: boolean;
}) => {
  const destination = destinations.length === 1 ? destinations[0] : null;
  return destination ? (
    <div
      className="standalone-destination-badges"
      aria-label="Selling and publishing destinations"
    >
      {destination === "CHAT" && <span>Chat</span>}
      {destination === "CONTENT_VAULT" && <span>{posted ? "✓ WALL" : "WALL"}</span>}
    </div>
  ) : null;
};

const SingleImageDetailPanel = ({ asset, onClose, onEdit, onReassign, onPreview, onPreparationRefresh }: {
  asset: AssetLibraryItem; onClose: () => void; onEdit: () => void; onReassign: () => void;
  onPreview: (imageUrl: string, label: string) => void;
  onPreparationRefresh: (preparation: StandaloneSalePreparation) => void;
}) => {
  const preparation = asset.standaloneSalePreparation;
  const intelligence = asset.intelligenceDetails;
  const unprepared = !preparation || preparation.status === "NOT_PREPARED";
  const deliveryReady = Boolean(preparation?.foundationReady && preparation.deliveryUrl);
  const [copied, setCopied] = useState(false);
  const [caption, setCaption] = useState<ContentVaultCaptionDraft | null>(preparation?.contentVaultCaption || null);
  const [captionOptions, setCaptionOptions] = useState<ContentVaultCaptionOption[]>([]);
  const [captionModalOpen, setCaptionModalOpen] = useState(false);
  const [selectedCaption, setSelectedCaption] = useState<number | null>(null);
  const [captionLoading, setCaptionLoading] = useState(false);
  const [captionSaving, setCaptionSaving] = useState(false);
  const [captionError, setCaptionError] = useState("");
  const [editingCaption, setEditingCaption] = useState(false);
  const [captionEdit, setCaptionEdit] = useState("");
  const [captionGuidance, setCaptionGuidance] = useState("");
  const [manualCaptionDraft, setManualCaptionDraft] = useState("");
  const [captionTone, setCaptionTone] = useState<ContentVaultCaptionTone>(() => readStoredCaptionTone());
  const [publication, setPublication] = useState<ContentVaultPublicationState | null>(preparation?.contentVaultPublication || null);
  const [publishing, setPublishing] = useState(false);
  const [publishError, setPublishError] = useState("");
  useEffect(() => setCopied(false), [asset.assetId, preparation?.deliveryUrl]);
  useEffect(() => {
    setCaption(preparation?.contentVaultCaption || null);
    setEditingCaption(false);
  }, [asset.assetId, preparation?.contentVaultCaption]);
  useEffect(() => {
    setPublication(preparation?.contentVaultPublication || null);
    setPublishError("");
  }, [asset.assetId, preparation?.contentVaultPublication]);
  useEffect(() => {
    if (!captionModalOpen) return;
    setSelectedCaption(null);
  }, [captionModalOpen, asset.assetId]);
  const copyDeliveryUrl = async () => {
    if (!preparation?.deliveryUrl) return;
    await navigator.clipboard.writeText(preparation.deliveryUrl);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };
  const openCaptionChooser = () => {
    setCaptionModalOpen(true);
    setCaptionError("");
    setSelectedCaption(null);
    setManualCaptionDraft(caption?.text || "");
  };
  const selectCaptionTone = (tone: ContentVaultCaptionTone) => {
    setCaptionTone(tone);
    try {
      window.sessionStorage.setItem(CAPTION_TONE_STORAGE_KEY, tone);
    } catch {
      // Ignore sessionStorage failures (private mode / blocked storage).
    }
  };
  const generateCaptions = async () => {
    setCaptionModalOpen(true); setCaptionLoading(true); setCaptionError(""); setSelectedCaption(null);
    try {
      const guidance = captionGuidance.trim();
      const response = await fetch(`/api/v1/assets/${asset.assetId}/content-vault/captions/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tone: captionTone,
          ...(guidance ? { guidance } : {}),
        }),
      });
      const result = await response.json() as { captions?: ContentVaultCaptionOption[]; detail?: string };
      if (!response.ok) throw new Error(result.detail || "Unable to generate captions.");
      setCaptionOptions(result.captions || []);
    } catch (reason) { setCaptionError(reason instanceof Error ? reason.message : "Unable to generate captions."); }
    finally { setCaptionLoading(false); }
  };
  const persistCaption = async (text: string, style: string | null, source: "GROK" | "MANUAL") => {
    setCaptionSaving(true); setCaptionError("");
    try {
      const response = await fetch(`/api/v1/assets/${asset.assetId}/content-vault/caption`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, style, source }),
      });
      const result = await response.json() as { caption?: ContentVaultCaptionDraft; detail?: string };
      if (!response.ok || !result.caption) throw new Error(result.detail || "Unable to save caption.");
      setCaption(result.caption);
      await refreshPublication();
      setCaptionModalOpen(false); setEditingCaption(false);
    } catch (reason) { setCaptionError(reason instanceof Error ? reason.message : "Unable to save caption."); }
    finally { setCaptionSaving(false); }
  };
  const isWallReady = preparation?.status === "READY" && preparation.destinations?.length === 1 && preparation.destinations[0] === "CONTENT_VAULT";
  const refreshPublication = async () => {
    const response = await fetch(`/api/v1/assets/${asset.assetId}/sale-preparation`);
    const result = await response.json() as StandaloneSalePreparation & { detail?: string };
    if (!response.ok) throw new Error(result.detail || "Unable to refresh publication status.");
    if (Object.prototype.hasOwnProperty.call(result, "contentVaultCaption")) {
      setCaption(result.contentVaultCaption || null);
    }
    setPublication(result.contentVaultPublication || null);
    if (result.assetId === asset.assetId && result.status) {
      onPreparationRefresh(result);
    }
  };
  const publishToContentVault = async () => {
    if (!preparation?.offeringId) return;
    setPublishing(true); setPublishError("");
    try {
      const response = await fetch(`/api/v1/commerce-authoring/${preparation.offeringId}/telegram-content-vault`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}),
      });
      const result = await response.json() as { detail?: string | { message?: string } };
      if (!response.ok) {
        const detail = typeof result.detail === "string" ? result.detail : result.detail?.message;
        throw new Error(detail || "Unable to publish to Content Vault.");
      }
    } catch (reason) {
      setPublishError(reason instanceof Error ? reason.message : "Unable to publish to Content Vault.");
    } finally {
      try { await refreshPublication(); } catch (reason) {
        if (!publishError) setPublishError(reason instanceof Error ? reason.message : "Unable to refresh publication status.");
      }
      setPublishing(false);
    }
  };
  const publicationStatus = publishing ? "PUBLISHING" : publication?.status || "NOT_PUBLISHED";
  const currentDestination = preparation?.destinations?.length === 1
    ? preparation.destinations[0] : null;
  const reassignmentBlocked = currentDestination === "CONTENT_VAULT"
    && (publicationStatus === "PUBLISHING" || publicationStatus === "PUBLISHED");
  const canPublish = Boolean(publication?.canPublish
    && publicationStatus !== "PUBLISHING" && publicationStatus !== "PUBLISHED");
  return <aside className="asset-details single-image-commercial-detail" aria-label="Selected asset details">
    <header><div><h2>{asset.displayName || `Asset #${asset.assetId}`}</h2><span>Single Image</span></div><button aria-label="Close asset details" onClick={onClose} type="button"><X size={17} /></button></header>
    {preparation && <div className="single-image-detail-status"><em className={`session-selling-badge session-selling-badge--${preparation.status.toLowerCase()}`}>{standalonePreparationLabel(preparation.status)}</em><StandaloneDestinationBadges destinations={preparation.destinations || []} /></div>}
    <section className="single-image-commercial-detail__sale" aria-labelledby="sale-preparation-title">
      <h3 id="sale-preparation-title">Sale Preparation</h3>
      {unprepared ? <div className="single-image-commercial-detail__empty"><p>This image has not been prepared for sale.</p><button className="sale-preparation-primary" onClick={onEdit} type="button">Prepare for Sale</button></div> : <>
        {preparation.priceMinor != null && <div className="single-image-detail-price"><span>Price</span><strong>{moneyLabel(preparation.priceMinor, preparation.currency)}</strong></div>}
        {asset.commercialAssets?.map((commercialAsset) => <article className="single-image-detail-teaser" key={`${commercialAsset.kind}:${commercialAsset.label}`}><header><strong>{commercialAsset.label.replace(/\s+—\s+(Selective Blur|Full Blur)$/i, "")}</strong><em>{commercialAsset.status}</em></header><button aria-label={`Open ${commercialAsset.label} preview`} onClick={() => onPreview(commercialAsset.previewUrl, commercialAsset.label)} type="button"><ContainedMediaImage src={commercialAsset.previewUrl} alt={commercialAsset.label} /></button><div><strong>{commercialAsset.styleLabel || (commercialAsset.kind === "PROMOTIONAL_TEASER" ? "Selective Blur" : "Full Blur")}</strong><span>{commercialAsset.distributionUse === "CONTENT_VAULT" ? "Used for Content Vault" : "Used for Chat Selling"}</span></div></article>)}
        <div className="single-image-detail-delivery"><div className="single-image-detail-delivery__heading"><div><strong>Paid Delivery</strong><span>Fanvue Media Link</span></div><em className={deliveryReady ? "is-ready" : "needs-attention"}>{deliveryReady ? "Ready" : preparation.status === "PREPARING" ? "Preparing" : "Needs Attention"}</em></div>{deliveryReady && preparation.deliveryUrl && <div className="single-image-detail-delivery__link"><code title={preparation.deliveryUrl}>{preparation.deliveryUrl}</code><div><a href={preparation.deliveryUrl} target="_blank" rel="noopener noreferrer">Open <ExternalLink size={13} /></a><button onClick={() => void copyDeliveryUrl()} type="button"><Copy size={13} />{copied ? "Copied" : "Copy"}</button></div></div>}</div>
        {preparation.error && <p className="sale-preparation-error">{preparation.error}</p>}
        <div className="single-image-detail-sale-actions">
          <button className="sale-preparation-secondary" onClick={onEdit} type="button">{preparation.status === "NEEDS_ATTENTION" ? "Retry Sale Preparation" : "Edit Sale Preparation"}</button>
          {currentDestination && <button
            className="sale-preparation-secondary"
            disabled={reassignmentBlocked}
            onClick={onReassign}
            title={reassignmentBlocked ? "Images publishing or published to TG Wall cannot be reassigned." : undefined}
            type="button"
          >Reassign Destination</button>}
        </div>
      </>}
    </section>
    {isWallReady && <section className="content-vault-publishing" aria-labelledby="content-vault-publishing-title">
      <h3 id="content-vault-publishing-title">Content Vault Publishing</h3>
      {publication?.previewUrl && <ContainedMediaImage src={publication.previewUrl} alt="Content Vault publication preview" />}
      <strong>Caption</strong>
      {!caption ? <><p className="content-vault-publishing__empty">No caption selected.</p><button className="sale-preparation-primary" onClick={openCaptionChooser} type="button">Choose Caption</button></> : editingCaption ? <>
        <textarea aria-label="Content Vault caption" value={captionEdit} onChange={(event) => setCaptionEdit(event.target.value)} rows={6} />
        <div className="content-vault-publishing__actions"><button disabled={!captionEdit.trim() || captionSaving} onClick={() => void persistCaption(captionEdit.trim(), caption.style || null, "MANUAL")} type="button">Save</button><button onClick={() => { setEditingCaption(false); setCaptionError(""); }} type="button">Cancel</button></div>
      </> : <><blockquote>{caption.text}</blockquote><div className="content-vault-publishing__actions"><button onClick={() => { setCaptionEdit(caption.text); setEditingCaption(true); }} type="button">Edit</button><button onClick={openCaptionChooser} type="button">Choose Another</button></div></>}
      {captionError && !captionModalOpen && <p className="sale-preparation-error">{captionError}</p>}
      <dl className="content-vault-publishing__preview"><div><dt>Teaser</dt><dd>{preparation.vaultReady ? "READY" : "NEEDS ATTENTION"}</dd></div><div><dt>Unlock</dt><dd>{preparation.priceMinor != null ? moneyLabel(preparation.priceMinor, preparation.currency) : "Not set"}</dd></div><div><dt>Fanvue Media Link</dt><dd>{deliveryReady ? "READY" : "NEEDS ATTENTION"}</dd></div></dl>
      {publicationStatus === "PUBLISHED" && <div className="content-vault-publishing__published"><strong>Published</strong>{publication?.publishedAt && <span>{dateLabel(publication.publishedAt)}</span>}{publication?.providerMessageId && <small>Telegram message {publication.providerMessageId}</small>}</div>}
      {(publishError || publication?.lastError) && <p className="sale-preparation-error" role="alert">{publishError || publication?.lastError}</p>}
      {publication?.readinessError && publicationStatus !== "PUBLISHED" && <small>{publication.readinessError}</small>}
      <button className="sale-preparation-primary" disabled={!canPublish} onClick={() => void publishToContentVault()} type="button">{publicationStatus === "PUBLISHING" ? "Publishing…" : publicationStatus === "PUBLISHED" ? "Published to Content Vault" : publicationStatus === "FAILED" ? "Retry Publish" : "Publish to Content Vault"}</button>
    </section>}
    {captionModalOpen && <div className="caption-chooser-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !captionSaving) setCaptionModalOpen(false); }}><div className="caption-chooser" role="dialog" aria-modal="true" aria-label="Choose Content Vault Caption">
      <header><div>{asset.imageUrl && <ContainedMediaImage src={asset.imageUrl} alt="" />}<div><small>Choose Content Vault Caption</small><h2>{asset.displayName || `Asset #${asset.assetId}`}</h2></div></div><button aria-label="Close caption chooser" onClick={() => setCaptionModalOpen(false)} type="button"><X size={18} /></button></header>
      <section className="caption-chooser__manual" aria-labelledby="manual-caption-title">
        <label className="caption-chooser__field">
          <span id="manual-caption-title">Your Caption</span>
          <textarea aria-label="Your Content Vault caption" disabled={captionSaving} maxLength={2000} onChange={(event) => { setManualCaptionDraft(event.target.value); setSelectedCaption(null); }} placeholder="Write your own Content Vault caption…" rows={4} value={manualCaptionDraft} />
          <small>{manualCaptionDraft.length} / 2000</small>
        </label>
        <button disabled={!manualCaptionDraft.trim() || captionSaving} onClick={() => { setSelectedCaption(null); void persistCaption(manualCaptionDraft.trim(), null, "MANUAL"); }} type="button">{captionSaving && selectedCaption === null ? "Saving…" : "Use My Caption"}</button>
      </section>
      <div className="caption-chooser__divider"><span>Or generate with AI</span></div>
      <div className="caption-tone-toggle" role="radiogroup" aria-label="Caption tone">
        <span className="caption-tone-toggle__label">Tone</span>
        <div className="caption-tone-toggle__options">
          <button
            type="button"
            role="radio"
            aria-checked={captionTone === "CLASSY"}
            className={captionTone === "CLASSY" ? "is-selected" : ""}
            disabled={captionLoading || captionSaving}
            onClick={() => selectCaptionTone("CLASSY")}
          >
            <strong>Classy</strong>
            <small>Seductive &amp; elevated</small>
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={captionTone === "RAUNCHY"}
            className={captionTone === "RAUNCHY" ? "is-selected" : ""}
            disabled={captionLoading || captionSaving}
            onClick={() => selectCaptionTone("RAUNCHY")}
          >
            <strong>Raunchy</strong>
            <small>Direct &amp; dirty</small>
          </button>
        </div>
      </div>
      <label className="caption-chooser__field">
        <span>Guidance for Grok <em>(optional)</em></span>
        <textarea
          aria-label="Caption generation guidance"
          value={captionGuidance}
          onChange={(event) => setCaptionGuidance(event.target.value.slice(0, 500))}
          rows={2}
          maxLength={500}
          placeholder="Example: she's spreading her pussy with her fingers, tongue out, staring at camera"
          disabled={captionLoading || captionSaving}
        />
        <small>Used when you generate. Tell Grok what to emphasize if the auto analysis is soft.</small>
      </label>
      {captionLoading ? <p className="caption-chooser__loading">Generating 5 captions…</p> : captionError ? <div className="caption-chooser__error"><p>{captionError}</p><button onClick={() => void generateCaptions()} type="button">Retry</button></div> : captionOptions.length ? <div className="caption-options">{captionOptions.map((option, index) => <button className={selectedCaption === index ? "is-selected" : ""} key={`${option.text}:${index}`} onClick={() => setSelectedCaption(index)} type="button"><small>Option {index + 1}</small><span>{option.text}</span></button>)}</div> : <p className="caption-chooser__empty">No generated options yet. Add optional guidance, then generate.</p>}
      <footer>
        <button disabled={captionLoading || captionSaving} onClick={() => void generateCaptions()} type="button">{captionOptions.length ? "Generate 5 More" : "Generate Caption with Grok"}</button>
        <button disabled={selectedCaption === null || captionSaving || captionLoading} onClick={() => { const option = selectedCaption === null ? null : captionOptions[selectedCaption]; if (option) void persistCaption(option.text, null, "GROK"); }} type="button">{captionSaving && selectedCaption !== null ? "Saving…" : "Use Selected Caption"}</button>
        <button disabled={captionSaving} onClick={() => setCaptionModalOpen(false)} type="button">Cancel</button>
      </footer>
    </div></div>}
    <details className="single-image-asset-details">
      <summary>Asset Details</summary>
      <dl><div><dt>Asset ID</dt><dd>#{asset.assetId}</dd></div><div><dt>Filename</dt><dd>{asset.fileName || "Not recorded"}</dd></div><div><dt>Media type</dt><dd>{asset.mediaType}</dd></div><div><dt>Classification</dt><dd>{assetClassificationLabel(asset.classification)}</dd></div><div><dt>Created</dt><dd>{dateLabel(asset.createdAt)}</dd></div><div><dt>Registration source</dt><dd>{asset.registrationSource || "Existing Creator Asset"}</dd></div><div><dt>Status</dt><dd>{asset.status || "Not recorded"}</dd></div><div><dt>Intelligence</dt><dd>{intelligenceStatusLabel(asset.intelligenceStatus)}</dd></div>{asset.intelligenceError && <div><dt>Intelligence error</dt><dd>{asset.intelligenceError}</dd></div>}<div><dt>Canonical reference</dt><dd>{asset.isCanonicalReference ? "Yes - Protected" : "No"}</dd></div></dl>
      {intelligence && Object.keys(intelligence).length > 0 && <section className="single-image-intelligence" aria-labelledby="single-image-intelligence-title">
        <h3 id="single-image-intelligence-title">Image Intelligence <em>{intelligence.status}</em></h3>
        <dl>
          {intelligence.title && <div><dt>Title</dt><dd>{intelligence.title}</dd></div>}
          {intelligence.summary && <div className="is-wide"><dt>Summary</dt><dd>{intelligence.summary}</dd></div>}
          {intelligence.setting && <div><dt>Setting</dt><dd>{intelligence.setting}</dd></div>}
          {intelligence.environment && <div><dt>Environment</dt><dd>{intelligence.environment}</dd></div>}
          {intelligence.activity && <div><dt>Activity</dt><dd>{intelligence.activity}</dd></div>}
          {intelligence.pose && <div><dt>Pose</dt><dd>{intelligence.pose}</dd></div>}
          {intelligence.expression && <div><dt>Expression</dt><dd>{intelligence.expression}</dd></div>}
          {intelligence.mood && <div><dt>Mood</dt><dd>{intelligence.mood}</dd></div>}
          {intelligence.framing && <div><dt>Framing</dt><dd>{intelligence.framing}</dd></div>}
          {intelligence.cameraAngle && <div><dt>Camera angle</dt><dd>{intelligence.cameraAngle}</dd></div>}
          {intelligence.lighting && <div><dt>Lighting</dt><dd>{intelligence.lighting}</dd></div>}
          {intelligence.atmosphere && <div><dt>Atmosphere</dt><dd>{intelligence.atmosphere}</dd></div>}
          {intelligence.visualStyle && <div><dt>Visual style</dt><dd>{intelligence.visualStyle}</dd></div>}
          {intelligence.emotionalTone && <div><dt>Emotional tone</dt><dd>{intelligence.emotionalTone}</dd></div>}
          {intelligence.lifestyleContext && <div className="is-wide"><dt>Lifestyle context</dt><dd>{intelligence.lifestyleContext}</dd></div>}
          {intelligence.safetyClassification && <div><dt>Content classification</dt><dd>{assetClassificationLabel(intelligence.safetyClassification)}</dd></div>}
          {intelligence.nudityLevel && <div><dt>Nudity level</dt><dd>{assetClassificationLabel(intelligence.nudityLevel)}</dd></div>}
          {intelligence.themes?.length && <div className="is-wide"><dt>Themes</dt><dd className="single-image-intelligence__pills">{intelligence.themes.map((theme) => <span key={theme}>{theme}</span>)}</dd></div>}
          {intelligence.tags?.length && <div className="is-wide"><dt>Tags</dt><dd className="single-image-intelligence__pills">{intelligence.tags.map((tag) => <span key={tag}>{tag}</span>)}</dd></div>}
        </dl>
      </section>}
    </details>
  </aside>;
};

const originalImageUrl = (imageUrl: string | null) =>
  imageUrl?.replace(/\/thumbnail(?:\?.*)?$/, "/media") || null;
const previewImageUrl = (imageUrl: string | null) =>
  imageUrl?.replace(/\/thumbnail(?:\?.*)?$/, "/preview") || null;

type RegistrationResponse = {
  message?: string;
  detail?: string;
  error?: string;
};
type AssetType = "images" | "photoshoots" | "videos" | "teasers";
type SalesDestination = "CHAT" | "WALL";
type SalesCommerceType = "ALL" | "SINGLE" | "BUNDLE" | "SESSION";
type DestinationCounts = { chat: number; wall: number; unassigned: number };
type AssetLibraryCounts = Record<AssetType | "bundles", number> & {
  destinationBreakdown?: Partial<Record<AssetType, DestinationCounts>> & {
    totals?: { chat: number; wall: number };
    chatCommerceTypes?: { single: number; bundle: number; session: number };
  };
};

const assetTypes = [
  {
    id: "images" as const,
    label: "Images",
    countLabel: "Assets",
    mediaType: "image",
    icon: ImageIcon,
  },
  {
    id: "photoshoots" as const,
    label: "Photoshoots",
    countLabel: "Photoshoots",
    mediaType: "photoshoot",
    icon: Camera,
  },
  {
    id: "videos" as const,
    label: "Videos",
    countLabel: "Videos",
    mediaType: "video",
    icon: Video,
  },
];

const teaserAssetType = {
  id: "teasers" as const,
  label: "Teasers",
  countLabel: "Assets",
  mediaType: "image",
  icon: Heart,
};
const allAssetTypes = [...assetTypes, teaserAssetType];

const assetTypeFromLocation = (): AssetType | null => {
  const value = new URLSearchParams(window.location.search).get("assetType");
  return allAssetTypes.some((item) => item.id === value)
    ? (value as AssetType)
    : null;
};
const salesDestinationFromLocation = (): SalesDestination | null => {
  const value = new URLSearchParams(window.location.search).get("sales")?.toUpperCase();
  return value === "CHAT" || value === "WALL" ? value : null;
};
const salesCommerceTypeFromLocation = (): SalesCommerceType => {
  const destination = salesDestinationFromLocation();
  const value = new URLSearchParams(window.location.search).get("salesType")?.toUpperCase();
  if (value === "SINGLE" || value === "BUNDLE") return value;
  if (value === "SESSION" && destination === "CHAT") return value;
  return "ALL";
};

async function readRegistrationResponse(
  response: Response,
): Promise<RegistrationResponse> {
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
  const [requestedAssetId] = useState<number | null>(consumeMovedAssetHandoff);
  const [data, setData] = useState<AssetLibraryResponse>(emptyResponse);
  const [search, setSearch] = useState("");
  const [assetType, setAssetType] = useState<AssetType | null>(
    assetTypeFromLocation,
  );
  const [salesDestination, setSalesDestination] = useState<SalesDestination | null>(salesDestinationFromLocation);
  const [salesCommerceType, setSalesCommerceType] = useState<SalesCommerceType>(salesCommerceTypeFromLocation);
  const [counts, setCounts] = useState<Partial<AssetLibraryCounts>>({});
  const [countsLoading, setCountsLoading] = useState(true);
  const [countsError, setCountsError] = useState(false);
  const [classification, setClassification] = useState("");
  const [destination, setDestination] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<AssetLibraryItem | null>(null);
  const [preview, setPreview] = useState<AssetLibraryItem | null>(null);
  const [previewNavigable, setPreviewNavigable] = useState(false);
  const [openPhotoshootId, setOpenPhotoshootId] = useState<string | null>(photoshootFromLocation);
  const [version, setVersion] = useState(0);
  const [actionMessage, setActionMessage] = useState("");
  const [registeringId, setRegisteringId] = useState<string | null>(null);
  const [archivingId, setArchivingId] = useState<string | null>(null);
  const [returningId, setReturningId] = useState<string | null>(null);
  const [teaserControlId, setTeaserControlId] = useState<number | null>(null);
  const [sellingModeAsset, setSellingModeAsset] = useState<AssetLibraryItem | null>(null);
  const [sellingModeSelection, setSellingModeSelection] = useState<"SESSION" | "BUNDLE">("SESSION");
  const [sellingChannelSelection, setSellingChannelSelection] = useState<"CHAT" | "CONTENT_WALL">("CHAT");
  const [sellingModeSaving, setSellingModeSaving] = useState(false);
  const [salePreparationAsset, setSalePreparationAsset] =
    useState<AssetLibraryItem | null>(null);
  const [reassignDestinationAsset, setReassignDestinationAsset] =
    useState<AssetLibraryItem | null>(null);

  const selectedAssetType =
    allAssetTypes.find((item) => item.id === assetType) || null;

  const setTeaserChatEnabled = async (asset: AssetLibraryItem) => {
    if (asset.assetId === null) return;
    setTeaserControlId(asset.assetId);
    setActionMessage("");
    try {
      const response = await fetch(`/api/v1/assets/${asset.assetId}/engagement-teaser/chat-control`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !asset.chatEnabled }),
      });
      const result = await response.json() as { chatEnabled?: boolean; detail?: string };
      if (!response.ok) throw new Error(result.detail || "Unable to update Chat availability.");
      setVersion((current) => current + 1);
    } catch (reason) {
      setActionMessage(reason instanceof Error ? reason.message : "Unable to update Chat availability.");
    } finally {
      setTeaserControlId(null);
    }
  };

  useEffect(() => {
    if (requestedAssetId === null) return;
    const controller = new AbortController();
    setError("");
    fetch(`/api/v1/assets/${requestedAssetId}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const result = await response.json() as AssetLibraryItem & { detail?: string };
        if (!response.ok) throw new Error(result.detail || "Unable to locate the moved Asset.");
        return result;
      })
      .then(setSelected)
      .catch((reason: unknown) => {
        if ((reason as { name?: string }).name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Unable to locate the moved Asset.");
      });
    return () => controller.abort();
  }, [requestedAssetId]);

  useEffect(() => {
    const onPopState = () => {
      setAssetType(assetTypeFromLocation());
      setSalesDestination(salesDestinationFromLocation());
      setSalesCommerceType(salesCommerceTypeFromLocation());
      setPage(1);
      setSearch("");
      setClassification("");
      setDestination("");
      setOpenPhotoshootId(photoshootFromLocation());
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setCountsLoading(true);
    setCountsError(false);
    fetch("/api/v1/assets/counts", { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const result = (await response.json()) as AssetLibraryCounts & { detail?: string };
        if (!response.ok) throw new Error(result.detail || "Unable to load Asset Library counts.");
        return result;
      })
      .then((values) => {
        setCounts(values);
        setCountsLoading(false);
      })
      .catch((reason: unknown) => {
        if ((reason as { name?: string }).name === "AbortError") return;
        setCountsError(true);
        setCountsLoading(false);
      });
    return () => controller.abort();
  }, [version]);

  useEffect(() => {
    if (!selectedAssetType && !salesDestination) {
      setData(emptyResponse);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    const params = new URLSearchParams({ page: String(page), page_size: "18" });
    if (search.trim()) params.set("search", search.trim());
    if (salesDestination) {
      params.set("sales_destination", salesDestination);
      params.set("sales_commerce_type", salesCommerceType);
    } else if (selectedAssetType) {
      params.set("media_type", selectedAssetType.mediaType);
      if (assetType === "teasers") params.set("asset_purpose", "TEASER");
    }
    if (classification) params.set("classification", classification);
    if (assetType === "images" && destination) params.set("destination", destination);
    setLoading(true);
    setError("");
    fetch(`/api/v1/assets?${params}`, {
      cache: "no-store",
      signal: controller.signal,
    })
      .then(async (response) => {
        const result = (await response.json()) as AssetLibraryResponse & {
          detail?: string;
        };
        if (!response.ok)
          throw new Error(result.detail || "Unable to load Asset Library.");
        return result;
      })
      .then((result) => {
        setData(result);
        setLoading(false);
      })
      .catch((reason: unknown) => {
        if ((reason as { name?: string }).name === "AbortError") return;
        setError(
          reason instanceof Error
            ? reason.message
            : "Unable to load Asset Library.",
        );
        setLoading(false);
      });
    return () => controller.abort();
  }, [assetType, classification, destination, page, salesCommerceType, salesDestination, search, selectedAssetType, version]);

  useEffect(() => {
    const analyzing = data.assets.filter(
      (item) =>
        item.itemKind === "registered_asset" &&
        item.assetId !== null &&
        isIntelligenceInProgress(item.intelligenceStatus),
    );
    if (!analyzing.length) return;
    const controller = new AbortController();
    let requestInFlight = false;
    const refreshIntelligence = async () => {
      if (requestInFlight) return;
      requestInFlight = true;
      try {
        const updates = await Promise.all(
          analyzing.map(async (item) => {
            const response = await fetch(`/api/v1/assets/${item.assetId}`, {
              cache: "no-store",
              signal: controller.signal,
            });
            const result = (await response.json()) as AssetLibraryItem & {
              detail?: string;
            };
            if (!response.ok)
              throw new Error(
                result.detail || "Unable to refresh Asset Intelligence.",
              );
            return [item.assetId!, result] as const;
          }),
        );
        const byId = new Map(updates);
        setData((current) => ({
          ...current,
          assets: current.assets.map((item) => {
            const update = item.assetId ? byId.get(item.assetId) : undefined;
            return update ? { ...item, ...update } : item;
          }),
        }));
        setSelected((current) => {
          if (!current?.assetId) return current;
          const update = byId.get(current.assetId);
          return update ? { ...current, ...update } : current;
        });
      } catch (reason) {
        if ((reason as { name?: string }).name !== "AbortError") {
          // Keep the current status and let the next targeted poll retry.
        }
      } finally {
        requestInFlight = false;
      }
    };
    const timer = window.setInterval(() => void refreshIntelligence(), 3000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [data.assets]);

  useEffect(() => {
    const preparing = data.assets.filter(
      (item) =>
        item.assetId && item.standaloneSalePreparation?.status === "PREPARING",
    );
    if (!preparing.length) return;
    let active = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void Promise.all(
        preparing.map(async (item) => {
          const response = await fetch(
            `/api/v1/assets/${item.assetId}/sale-preparation`,
            { cache: "no-store", signal: controller.signal },
          );
          const result = (await response.json()) as NonNullable<
            AssetLibraryItem["standaloneSalePreparation"]
          > & { detail?: string };
          if (!response.ok)
            throw new Error(
              result.detail || "Unable to refresh preparation state.",
            );
          return [item.assetId!, result] as const;
        }),
      )
        .then((updates) => {
          if (!active) return;
          const byId = new Map(updates);
          setData((current) => ({
            ...current,
            assets: current.assets.map((item) => {
              const preparation = item.assetId
                ? byId.get(item.assetId)
                : undefined;
              return preparation
                ? { ...item, standaloneSalePreparation: preparation }
                : item;
            }),
          }));
          setSelected((current) => {
            if (!current?.assetId) return current;
            const preparation = byId.get(current.assetId);
            return preparation
              ? { ...current, standaloneSalePreparation: preparation }
              : current;
          });
        })
        .catch((reason: unknown) => {
          if (active)
            setError(
              reason instanceof Error
                ? reason.message
                : "Unable to refresh preparation state.",
            );
        });
    }, 4000);
    return () => {
      active = false;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [data.assets]);

  const chooseAssetType = (type: AssetType) => {
    const url = new URL(window.location.href);
    url.searchParams.delete("sales");
    url.searchParams.delete("salesType");
    url.searchParams.set("assetType", type);
    window.history.pushState({ assetLibraryType: type }, "", url);
    setAssetType(type);
    setSalesDestination(null);
    setPage(1);
    setSearch("");
    setClassification("");
    setDestination("");
    setSelected(null);
  };

  const chooseSalesDestination = (sales: SalesDestination) => {
    const url = new URL(window.location.href);
    url.searchParams.delete("assetType");
    url.searchParams.set("sales", sales.toLowerCase());
    url.searchParams.delete("salesType");
    window.history.pushState({ assetLibrarySales: sales }, "", url);
    setAssetType(null);
    setSalesDestination(sales);
    setSalesCommerceType("ALL");
    setPage(1);
    setSearch("");
    setClassification("");
    setDestination("");
    setSelected(null);
  };

  const chooseSalesCommerceType = (type: SalesCommerceType) => {
    const url = new URL(window.location.href);
    if (type === "ALL") url.searchParams.delete("salesType");
    else url.searchParams.set("salesType", type.toLowerCase());
    window.history.pushState({ assetLibrarySalesType: type }, "", url);
    setSalesCommerceType(type);
    setPage(1);
    setSelected(null);
  };

  const backToAssetTypes = () => {
    const url = new URL(window.location.href);
    url.searchParams.delete("assetType");
    url.searchParams.delete("sales");
    url.searchParams.delete("salesType");
    window.history.pushState({ assetLibraryType: null }, "", url);
    setAssetType(null);
    setSalesDestination(null);
    setSalesCommerceType("ALL");
    setPage(1);
    setSearch("");
    setClassification("");
    setDestination("");
    setSelected(null);
  };

const archiveAsset = async (asset: AssetLibraryItem) => {
    const identity = asset.itemKind === "photoshoot"
      ? asset.deliverableId
      : asset.itemKind === "staged_generation"
        ? asset.generationId
        : asset.assetId != null
          ? String(asset.assetId)
          : null;
    if (!identity || archivingId) return;
    setArchivingId(identity);
    setError("");
    setActionMessage("");
    try {
      const endpoint =
        asset.itemKind === "photoshoot"
          ? `/api/v1/assets/photoshoots/${encodeURIComponent(identity)}/archive`
          : asset.itemKind === "staged_generation"
            ? `/api/v1/assets/staged/${encodeURIComponent(identity)}/archive`
            : `/api/v1/assets/${encodeURIComponent(identity)}/archive`;
      const response = await fetch(endpoint, { method: "POST" });
      const result = (await response.json()) as {
        message?: string;
        detail?: unknown;
      };
      if (!response.ok) {
        const detail = typeof result.detail === "string"
          ? result.detail
          : Array.isArray(result.detail)
            ? result.detail.map((item) => typeof item === "object" && item && "msg" in item
              ? String((item as { msg: unknown }).msg) : String(item)).join("; ")
            : result.detail && typeof result.detail === "object" && "message" in result.detail
              ? String((result.detail as { message: unknown }).message)
              : "Unable to archive Asset.";
        throw new Error(detail);
      }
      setSelected(null);
      setActionMessage(result.message || "Asset archived.");
      setVersion((current) => current + 1);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Unable to archive Asset.",
      );
    } finally {
      setArchivingId(null);
    }
  };

  const openAsset = (asset: AssetLibraryItem) => {
    if (asset.itemKind === "photoshoot" && asset.deliverableId)
      setOpenPhotoshootId(asset.deliverableId);
    else if (asset.itemKind === "registered_asset") void openDetails(asset);
    else setPreview(asset);
  };

  const displayedSingleImages = useMemo(() => data.assets.filter((item) =>
    assetType === "images" && item.itemKind === "registered_asset" &&
    item.classification === "SINGLE_IMAGE" && Boolean(item.imageUrl)), [assetType, data.assets]);

  const openSingleImagePreview = (asset: AssetLibraryItem) => {
    void openDetails(asset);
    setPreview(asset);
    setPreviewNavigable(true);
  };

  const closePreview = useCallback(() => {
    setPreview(null);
    setPreviewNavigable(false);
  }, []);

  const movePreview = useCallback((direction: number) => {
    if (!previewNavigable || !preview) return;
    const index = displayedSingleImages.findIndex((item) => item.libraryItemId === preview.libraryItemId);
    const next = displayedSingleImages[index + direction];
    if (next) {
      setPreview(next);
    }
  }, [displayedSingleImages, preview, previewNavigable]);

  useEffect(() => {
    if (!preview) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closePreview();
      else if (previewNavigable && event.key === "ArrowLeft") movePreview(-1);
      else if (previewNavigable && event.key === "ArrowRight") movePreview(1);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [closePreview, movePreview, preview, previewNavigable]);

  const returnToGenerationLibrary = async (asset: AssetLibraryItem) => {
    if (!asset.generationId || returningId) {
      setError("This Asset has no linked Generation Library source to return.");
      return;
    }
    setReturningId(asset.generationId);
    setError("");
    setActionMessage("");
    try {
      const response = await fetch(
        `/api/v1/generation-library/${encodeURIComponent(asset.generationId)}/move-back-to-generation-library`,
        { method: "POST" },
      );
      const result = (await response.json()) as { message?: string; detail?: string };
      if (!response.ok) throw new Error(result.detail || "Unable to return image.");
      setSelected(null);
      setActionMessage(result.message || "Image returned to Generation Library.");
      setVersion((current) => current + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to return image.");
    } finally {
      setReturningId(null);
    }
  };

  const registerAsset = async (asset: AssetLibraryItem) => {
    const registrationKey =
      asset.itemKind === "photoshoot"
        ? asset.deliverableId
        : asset.generationId;
    if (
      !registrationKey ||
      registeringId ||
      asset.itemKind === "registered_asset"
    )
      return;
    setRegisteringId(registrationKey);
    setError("");
    setActionMessage("");
    try {
      const endpoint =
        asset.itemKind === "photoshoot"
          ? `/api/v1/assets/photoshoots/${encodeURIComponent(registrationKey)}/register`
          : `/api/v1/assets/staged/${encodeURIComponent(registrationKey)}/register`;
      const response = await fetch(endpoint, { method: "POST" });
      const result = await readRegistrationResponse(response);
      setSelected(null);
      setActionMessage(
        result.message ||
          (asset.itemKind === "photoshoot"
            ? "Photoshoot registered for Commerce."
            : "Asset registered. Analysis is pending."),
      );
      setVersion((current) => current + 1);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Unable to register Business Asset.",
      );
    } finally {
      setRegisteringId(null);
    }
  };

  const standalonePreparationStarted = (
    assetId: number,
    result: NonNullable<AssetLibraryItem["standaloneSalePreparation"]>,
  ) => {
    setData((current) => ({
      ...current,
      assets: current.assets.map((item) =>
        item.assetId === assetId
          ? { ...item, standaloneSalePreparation: result }
          : item,
      ),
    }));
    setSelected((current) => current?.assetId === assetId
      ? { ...current, standaloneSalePreparation: result }
      : current);
    setActionMessage(
      result.status === "READY"
        ? "Asset is ready for sale."
        : "Asset preparation started.",
    );
  };

  const standalonePreparationRefreshed = (
    assetId: number,
    result: NonNullable<AssetLibraryItem["standaloneSalePreparation"]>,
  ) => {
    setData((current) => ({
      ...current,
      assets: current.assets.map((item) => item.assetId === assetId
        ? { ...item, standaloneSalePreparation: result }
        : item),
    }));
    setSelected((current) => current?.assetId === assetId
      ? { ...current, standaloneSalePreparation: result }
      : current);
  };

  const openDetails = async (asset: AssetLibraryItem) => {
    setSelected(asset);
    setError("");
    if (
      asset.itemKind === "staged_generation" ||
      asset.itemKind === "photoshoot" ||
      asset.assetId === null
    )
      return;
    try {
      const response = await fetch(`/api/v1/assets/${asset.assetId}`, {
        cache: "no-store",
      });
      const result = (await response.json()) as AssetLibraryItem & {
        detail?: string;
      };
      if (!response.ok)
        throw new Error(result.detail || "Unable to load Asset details.");
      setSelected(result);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Unable to load Asset details.",
      );
    }
  };

  const range = useMemo(() => {
    if (!data.total) return "0 assets";
    const first = (data.page - 1) * data.pageSize + 1;
    return `${first}-${Math.min(first + data.assets.length - 1, data.total)} of ${data.total}`;
  }, [data]);

  const synchronizeSessionSelling = useCallback(
    (readiness: NonNullable<AssetLibraryItem["sessionSelling"]>) => {
      setData((current) => ({
        ...current,
        assets: current.assets.map((asset) =>
          asset.deliverableId === readiness.deliverableId
            ? { ...asset, sessionSelling: readiness }
            : asset,
        ),
      }));
    },
    [],
  );
  const synchronizeSellingMode = useCallback(
    (
      deliverableId: string,
      sellingMode: NonNullable<AssetLibraryItem["sellingMode"]>,
      bundleSalesChannel?: AssetLibraryItem["bundleSalesChannel"],
    ) => {
      setData((current) => ({
        ...current,
        assets: current.assets.map((asset) =>
          asset.deliverableId === deliverableId
            ? { ...asset, sellingMode, bundleSalesChannel: sellingMode === "BUNDLE" ? (bundleSalesChannel || "CHAT") : null, sessionSelling: null }
            : asset,
        ),
      }));
    },
    [],
  );

  const openSellingModeReassignment = (asset: AssetLibraryItem) => {
    setSellingModeAsset(asset);
    setSellingModeSelection(asset.sellingMode || "SESSION");
    setSellingChannelSelection(asset.bundleSalesChannel || "CHAT");
    setError("");
  };

  const reassignSellingMode = async () => {
    if (!sellingModeAsset?.deliverableId || sellingModeSaving) return;
    const currentMode = sellingModeAsset.sellingMode || "SESSION";
    const currentChannel = sellingModeAsset.bundleSalesChannel || "CHAT";
    if (sellingModeSelection === currentMode
        && (sellingModeSelection !== "BUNDLE" || sellingChannelSelection === currentChannel)) {
      setSellingModeAsset(null);
      return;
    }
    setSellingModeSaving(true);
    setError("");
    try {
      const response = await fetch(
        `/api/v1/assets/photoshoots/${encodeURIComponent(sellingModeAsset.deliverableId)}/commerce-assignment`,
        { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
          sellingMode: sellingModeSelection,
          bundleSalesChannel: sellingModeSelection === "BUNDLE" ? sellingChannelSelection : null,
        }) },
      );
      const result = await response.json() as { sellingMode?: "SESSION" | "BUNDLE"; bundleSalesChannel?: "CHAT" | "CONTENT_WALL" | null; detail?: string };
      if (!response.ok) throw new Error(result.detail || "Unable to reassign selling mode.");
      const mode = result.sellingMode || sellingModeSelection;
      synchronizeSellingMode(sellingModeAsset.deliverableId, mode, result.bundleSalesChannel);
      setActionMessage(`Photoshoot reassigned to ${mode === "BUNDLE" ? `${result.bundleSalesChannel === "CONTENT_WALL" ? "Wall" : "Chat"} Bundle` : "Session"} selling.`);
      setSellingModeAsset(null);
      setVersion((current) => current + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to reassign selling mode.");
    } finally {
      setSellingModeSaving(false);
    }
  };

  if (openPhotoshootId)
    return (
      <PhotoshootViewer
        deliverableId={openPhotoshootId}
        enableSessionSelling
        onSessionSellingChange={synchronizeSessionSelling}
        onSellingModeChange={(sellingMode) =>
          synchronizeSellingMode(openPhotoshootId, sellingMode)
        }
        onMembersChanged={(detail) => setData((current) => ({ ...current,
          assets: current.assets.map((asset) => asset.deliverableId === detail.deliverableId
            ? { ...asset, shotCount: detail.shotCount, imageUrl: detail.imageUrl }
            : asset) }))}
        onClose={() => {
          setOpenPhotoshootId(null);
          // Session pricing is persisted while the viewer replaces the grid.
          // Reconcile the card from the canonical projection when returning.
          setVersion((current) => current + 1);
        }}
      />
    );

  return (
    <section className="asset-library-page">
      <PageHeader
        title="Asset Library"
        description="Curated generations and registered Creator Assets."
      />

      {!assetType && !salesDestination && (
        <section
          className="asset-type-dashboard"
          aria-labelledby="asset-type-heading"
        >
          <header>
            <span>Asset workspace</span>
            <h2 id="asset-type-heading">Browse Inventory</h2>
            <p>Browse by asset type or current sales destination.</p>
          </header>
          <h3 className="asset-dashboard-label">ASSET TYPE</h3>
          <div className="asset-type-grid">
            {assetTypes.map((item) => (
              <button
                className="asset-type-card"
                key={item.id}
                onClick={() => chooseAssetType(item.id)}
                type="button"
              >
                <span className="asset-type-card__icon">
                  <item.icon size={34} />
                </span>
                <span>
                  <strong>{item.label}</strong>
                  <small>
                    {countsLoading
                      ? "Loading…"
                      : countsError
                        ? "Count unavailable"
                        : `${counts[item.id]} ${item.countLabel}`}
                  </small>
                </span>
              </button>
            ))}
          </div>
          <h3 className="asset-dashboard-label">SALES</h3>
          <div className="asset-type-grid asset-type-grid--sales">
            <button className="asset-type-card" onClick={() => chooseSalesDestination("CHAT")} type="button">
              <span className="asset-type-card__icon"><MessageCircle size={34} /></span>
              <span><strong>Chat</strong><small>{countsLoading ? "Loading…" : countsError ? "Count unavailable" : `${counts.destinationBreakdown?.totals?.chat ?? 0} Assets`}</small></span>
            </button>
            <button className="asset-type-card" onClick={() => chooseSalesDestination("WALL")} type="button">
              <span className="asset-type-card__icon"><Megaphone size={34} /></span>
              <span><strong>TG Wall</strong><small>{countsLoading ? "Loading…" : countsError ? "Count unavailable" : `${counts.destinationBreakdown?.totals?.wall ?? 0} Assets`}</small></span>
            </button>
          </div>
          <h3 className="asset-dashboard-label">ENGAGEMENT</h3>
          <div className="asset-type-grid asset-type-grid--engagement">
            <button className="asset-type-card" onClick={() => chooseAssetType("teasers")} type="button">
              <span className="asset-type-card__icon"><Heart size={34} /></span>
              <span><strong>Teasers</strong><small>{countsLoading ? "Loading…" : countsError ? "Count unavailable" : `${counts.teasers ?? 0} Assets`}</small></span>
            </button>
          </div>
        </section>
      )}

      {(assetType || salesDestination) && (
        <>
          <div className="asset-library-section-header">
            <button onClick={backToAssetTypes} type="button">
              <ArrowLeft size={17} />
              Back to Asset Types
            </button>
            <h2>{salesDestination ? (salesDestination === "CHAT" ? "Chat" : "TG Wall") : selectedAssetType?.label}</h2>
          </div>
          {salesDestination && (
            <div className="asset-sales-type-filter" aria-label="Sales commerce type">
              {(salesDestination === "CHAT" ? ["ALL", "SINGLE", "BUNDLE", "SESSION"] as const : ["ALL", "SINGLE", "BUNDLE"] as const).map((type) => (
                <button className={salesCommerceType === type ? "is-active" : ""} key={type} onClick={() => chooseSalesCommerceType(type)} type="button">
                  {{ ALL: "All", SINGLE: "Single", BUNDLE: "Bundle", SESSION: "Session" }[type]}
                  {salesDestination === "CHAT" && <span className="asset-sales-type-filter__count"> · {type === "ALL"
                    ? counts.destinationBreakdown?.totals?.chat ?? 0
                    : counts.destinationBreakdown?.chatCommerceTypes?.[type.toLowerCase() as "single" | "bundle" | "session"] ?? 0}</span>}
                </button>
              ))}
            </div>
          )}
          <div className={`asset-library-toolbar asset-library-toolbar--section${salesDestination ? " asset-library-toolbar--sales" : ""}`}>
            <label className="asset-library-search">
              <Search size={16} />
              <span className="sr-only">Search assets</span>
              <input
                aria-label="Search assets"
                onChange={(event) => {
                  setSearch(event.target.value);
                  setPage(1);
                }}
                placeholder={`Search ${salesDestination ? (salesDestination === "CHAT" ? "Chat" : "TG Wall") : selectedAssetType?.label.toLowerCase()}`}
                value={search}
              />
            </label>
            {!salesDestination && assetType !== "teasers" && <label>
              <span>{assetType === "images" ? "Destination" : "Classification"}</span>
              <select
                aria-label={assetType === "images" ? "Destination" : "Classification"}
                onChange={(event) => {
                  if (assetType === "images") setDestination(event.target.value);
                  else setClassification(event.target.value);
                  setPage(1);
                }}
                value={assetType === "images" ? destination : classification}
              >
                {(assetType === "images"
                  ? [
                      { value: "", label: "All destinations" },
                      { value: "CHAT", label: "Chat" },
                      { value: "CONTENT_VAULT", label: "Wall" },
                      { value: "NOT_PREPARED", label: "Not Prepared" },
                    ]
                  : assetType === "photoshoots"
                  ? photoshootClassificationOptions
                  : [
                      { value: "", label: "All classifications" },
                      ...data.classifications.map((value) => ({
                        value,
                        label: assetClassificationLabel(value),
                      })),
                    ]
                ).map((option) => (
                  <option key={option.value || "all"} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>}
            <span className="asset-library-range">{range}</span>
          </div>

          {error && (
            <div
              className="asset-library-state asset-library-state--error"
              role="alert"
            >
              {error}
            </div>
          )}
          {actionMessage && (
            <div className="asset-library-state" role="status">
              {actionMessage}
            </div>
          )}
          {loading && (
            <div className="asset-library-state">Loading assets...</div>
          )}
          {!loading && !error && data.assets.length === 0 && (
            <div className="asset-library-state">
              <ImageOff size={24} />
              <strong>No assets found.</strong>
              <span>
                Move an image from Generation Library or adjust the filters.
              </span>
            </div>
          )}
          {!loading && data.assets.length > 0 && (
            <div
              className={`asset-library-layout${selected ? "" : " asset-library-layout--cards-only"}`}
            >
              <div className="asset-library-grid">
                {data.assets.map((asset) => (
                  <article
                    className={
                      selected?.libraryItemId === asset.libraryItemId
                        ? "asset-card asset-card--selected"
                        : "asset-card"
                    }
                    key={asset.libraryItemId}
                  >
                    <button
                      className={`asset-card__image${assetType === "images" && asset.classification === "SINGLE_IMAGE" ? " asset-card__image--zoomable" : ""}`}
                      disabled={!asset.mediaAvailable}
                      onClick={() => assetType === "images" && asset.classification === "SINGLE_IMAGE"
                        ? openSingleImagePreview(asset) : openAsset(asset)}
                      type="button"
                      aria-label={`Open ${asset.itemKind === "photoshoot" ? "Photoshoot cover" : selectedAssetType?.label.slice(0, -1) || "Asset"}`}
                    >
                      {asset.imageUrl ? (
                        <ContainedMediaImage
                          alt={
                            asset.itemKind === "photoshoot"
                              ? asset.fileName || "Photoshoot"
                              : `${selectedAssetType?.label.slice(0, -1) || "Asset"} preview`
                          }
                          loading="lazy"
                          src={asset.imageUrl}
                        />
                      ) : (
                        <span>
                          <ImageOff />
                          <small>Media unavailable</small>
                        </span>
                      )}
                    </button>
                    {asset.itemKind === "photoshoot" ? (
                      <div className="asset-card__photoshoot">
                        <strong>{asset.fileName}</strong>
                        <span>Photoshoot • {asset.shotCount} Images</span>
                        <dl>
                          <div><dt>Registered</dt><dd>{dateLabel(asset.createdAt)}</dd></div>
                          <div><dt>Price</dt><dd>{commercialPriceLabel(asset)}</dd></div>
                        </dl>
                        <div className="asset-card__photoshoot-badges">
                          <em
                            className={`session-selling-badge session-selling-badge--${readinessBadgeStatus(asset.sessionSelling)}`}
                          >
                            {readinessBadge(asset.sessionSelling)}
                          </em>
                          {photoshootCommercialBadges(asset)?.channel && (
                            <em className="session-selling-badge photoshoot-sales-classification photoshoot-badge--channel">
                              {photoshootCommercialBadges(asset)?.posted
                                && photoshootCommercialBadges(asset)?.channel === "WALL"
                                ? "✓ WALL"
                                : photoshootCommercialBadges(asset)?.channel}
                            </em>
                          )}
                          {photoshootCommercialBadges(asset)?.sellingMode && (
                            <em className={`session-selling-badge photoshoot-sales-classification photoshoot-badge--${photoshootCommercialBadges(asset)?.sellingMode.toLowerCase()}`}>
                              {photoshootCommercialBadges(asset)?.sellingMode}
                            </em>
                          )}
                        </div>
                      </div>
                    ) : asset.itemKind === "registered_asset" ? (
                      <div className="asset-card__summary" onClick={() => void openDetails(asset)}>
                        <span>
                          <strong>
                            {asset.displayName || `Asset #${asset.assetId}`}
                          </strong>
                          {asset.isCanonicalReference && (
                            <em>Canonical reference - Protected</em>
                          )}
                        </span>
                        <dl>
                          <div>
                            <dt>Type</dt>
                            <dd>{asset.mediaType}</dd>
                          </div>
                          {assetType !== "images" && <div>
                            <dt>Classification</dt>
                            <dd>{assetClassificationLabel(asset.classification)}</dd>
                          </div>}
                          <div>
                            <dt>Intelligence</dt>
                            <dd>{intelligenceStatusLabel(asset.intelligenceStatus)}</dd>
                          </div>
                          <div>
                            <dt>Registered</dt>
                            <dd>{dateLabel(asset.createdAt)}</dd>
                          </div>
                          {assetType !== "teasers" && asset.mediaType === "image" && !asset.isReference && (
                            <div>
                              <dt>Price</dt>
                              <dd>{commercialPriceLabel(asset)}</dd>
                            </div>
                          )}
                        </dl>
                        {asset.contentDestination === "TEASER" ? (
                          <>
                            <div className="standalone-commercial-badges">
                              <em className="session-selling-badge photoshoot-sales-classification photoshoot-badge--single">TEASER</em>
                            </div>
                            <div className="engagement-teaser-chat-control" onClick={(event) => event.stopPropagation()}>
                              <button
                                aria-label={`${asset.chatEnabled ? "Disable" : "Enable"} ${asset.displayName || `Asset ${asset.assetId}`} for Chat`}
                                disabled={teaserControlId === asset.assetId}
                                onClick={() => void setTeaserChatEnabled(asset)} type="button"
                              >
                                Chat {asset.chatEnabled ? "Enabled" : "Disabled"}
                              </button>
                              <span>Times Sent <strong>{asset.timesSent ?? 0}</strong></span>
                              <span>Last Sent <strong>{asset.lastSent ? dateLabel(asset.lastSent) : "Never"}</strong></span>
                            </div>
                          </>
                        ) : asset.mediaType === "image" &&
                          !asset.isReference &&
                          asset.standaloneSalePreparation && (
                            <div className="standalone-commercial-badges">
                              <em
                                className={`session-selling-badge session-selling-badge--${asset.standaloneSalePreparation.status.toLowerCase()}`}
                              >
                                {standalonePreparationLabel(
                                  asset.standaloneSalePreparation.status,
                                )}
                              </em>
                              {salesDestination && (
                                <em className="session-selling-badge photoshoot-sales-classification photoshoot-badge--single">SINGLE</em>
                              )}
                              <StandaloneDestinationBadges
                                destinations={
                                  asset.standaloneSalePreparation.destinations ||
                                  []
                                }
                                posted={isPostedToContentWall(
                                  asset.standaloneSalePreparation.destinations?.length === 1 &&
                                    asset.standaloneSalePreparation.destinations[0] === "CONTENT_VAULT"
                                    ? "WALL" : null,
                                  asset.standaloneSalePreparation.contentVaultPublication,
                                )}
                              />
                            </div>
                          )}
                      </div>
                    ) : null}
                    <LibraryActionGroup label="Asset actions">
                      <LibraryActionButton
                        disabled={asset.itemKind === "registered_asset" && Boolean(returningId)}
                        icon={MoveRight}
                        onClick={() => asset.itemKind === "registered_asset" && asset.generationId
                          ? void returnToGenerationLibrary(asset)
                          : openAsset(asset)}
                        tooltip={
                          asset.itemKind === "photoshoot"
                            ? "Open Photoshoot"
                            : "Move to Generation Library"
                        }
                      />
                      {asset.itemKind !== "photoshoot" && (
                        <LibraryActionButton
                          disabled={
                            asset.itemKind === "registered_asset" ||
                            Boolean(registeringId)
                          }
                          icon={PackagePlus}
                          onClick={() => void registerAsset(asset)}
                          tooltip="Register Asset"
                        />
                      )}
                      {asset.itemKind === "registered_asset" &&
                        assetType !== "teasers" && asset.mediaType === "image" &&
                        !asset.isReference && (
                          <LibraryActionButton
                            accent={
                              asset.standaloneSalePreparation?.status ===
                              "READY"
                            }
                            disabled={
                              asset.standaloneSalePreparation?.status ===
                              "PREPARING"
                            }
                            icon={BadgeDollarSign}
                            onClick={() => setSalePreparationAsset(asset)}
                            tooltip={
                              asset.standaloneSalePreparation?.status ===
                              "READY"
                                ? "Edit Sale Preparation"
                                : asset.standaloneSalePreparation?.status ===
                                    "NEEDS_ATTENTION"
                                  ? "Retry Preparation"
                                  : "Prepare for Sale"
                            }
                          />
                        )}
                      {assetType === "images" && asset.itemKind === "registered_asset" &&
                        asset.classification === "SINGLE_IMAGE" &&
                        asset.standaloneSalePreparation?.destinations?.length === 1 && (
                          <LibraryActionButton
                            icon={ArrowRightLeft}
                            onClick={() => setReassignDestinationAsset(asset)}
                            tooltip="Reassign sales destination"
                          />
                        )}
                      {asset.itemKind === "photoshoot" && (
                        <LibraryActionButton
                          disabled={sellingModeSaving}
                          icon={ArrowRightLeft}
                          onClick={() => openSellingModeReassignment(asset)}
                          tooltip="Reassign Photoshoot commerce"
                        />
                      )}
                      <LibraryActionButton
                        disabled={Boolean(archivingId)}
                        icon={Trash2}
                        onClick={() => void archiveAsset(asset)}
                        tooltip="Archive"
                      />
                      {asset.mediaType === "image" && asset.assetId && (
                        <LibraryActionButton
                          icon={Video}
                          onClick={() => {
                            window.location.href = videoStudioLink({
                              type: "asset",
                              id: String(asset.assetId),
                              previewUrl: asset.imageUrl,
                              label: asset.fileName || `Asset ${asset.assetId}`,
                            });
                          }}
                          tooltip="Create Video"
                        />
                      )}
                      {asset.mediaType === "video" && asset.assetId && (
                        <LibraryActionButton
                          icon={Video}
                          onClick={() => {
                            window.location.href = videoStudioLink({
                              type: "asset",
                              id: String(asset.assetId),
                              previewUrl: asset.imageUrl,
                              label: asset.fileName || `Video ${asset.assetId}`,
                            });
                          }}
                          tooltip="Extend Video"
                        />
                      )}
                    </LibraryActionGroup>
                  </article>
                ))}
              </div>
              {selected && (
                assetType !== "teasers" && selected.classification === "SINGLE_IMAGE" ? <SingleImageDetailPanel
                  asset={selected}
                  onClose={() => setSelected(null)}
                  onEdit={() => setSalePreparationAsset(selected)}
                  onReassign={() => setReassignDestinationAsset(selected)}
                  onPreview={(imageUrl, label) => { setPreviewNavigable(false); setPreview({ ...selected, imageUrl, fileName: label }); }}
                  onPreparationRefresh={(result) => selected.assetId != null && standalonePreparationRefreshed(selected.assetId, result)}
                /> :
                <aside
                  className="asset-details"
                  aria-label="Selected asset details"
                >
                  <header>
                    <div>
                      <small>Asset #{selected.assetId}</small>
                      <h2>
                        {selected.displayName || `Asset #${selected.assetId}`}
                      </h2>
                    </div>
                    <button
                      aria-label="Close asset details"
                      onClick={() => setSelected(null)}
                      type="button"
                    >
                      <X size={17} />
                    </button>
                  </header>
                  <dl>
                    <div>
                      <dt>Filename</dt>
                      <dd>{selected.fileName || "Not recorded"}</dd>
                    </div>
                    <div>
                      <dt>Media type</dt>
                      <dd>{selected.mediaType}</dd>
                    </div>
                    <div>
                      <dt>Classification</dt>
                      <dd>
                        {assetClassificationLabel(selected.classification)}
                      </dd>
                    </div>
                    <div>
                      <dt>Created</dt>
                      <dd>{dateLabel(selected.createdAt)}</dd>
                    </div>
                    <div>
                      <dt>Registration source</dt>
                      <dd>
                        {selected.registrationSource ||
                          "Existing Creator Asset"}
                      </dd>
                    </div>
                    <div>
                      <dt>Status</dt>
                      <dd>{selected.status || "Not recorded"}</dd>
                    </div>
                    <div>
                      <dt>Intelligence</dt>
                      <dd>{intelligenceStatusLabel(selected.intelligenceStatus)}</dd>
                    </div>
                    {selected.intelligenceError && (
                      <div>
                        <dt>Intelligence error</dt>
                        <dd>{selected.intelligenceError}</dd>
                      </div>
                    )}
                    <div>
                      <dt>Canonical reference</dt>
                      <dd>
                        {selected.isCanonicalReference
                          ? "Yes - Protected"
                          : "No"}
                      </dd>
                    </div>
                    <div>
                      <dt>Tags</dt>
                      <dd>
                        {selected.tags.length
                          ? selected.tags.join(", ")
                          : "None"}
                      </dd>
                    </div>
                    <div>
                      <dt>Themes</dt>
                      <dd>
                        {selected.themes.length
                          ? selected.themes.join(", ")
                          : "None"}
                      </dd>
                    </div>
                  </dl>
                  {selected.itemKind === "registered_asset" &&
                    selected.mediaType === "image" &&
                    selected.standaloneSalePreparation?.destinations?.length ? (
                      <section className="asset-detail-destinations" aria-labelledby="asset-destinations-title">
                        <h3 id="asset-destinations-title">Selling / Publishing</h3>
                        <StandaloneDestinationBadges destinations={selected.standaloneSalePreparation.destinations} />
                      </section>
                    ) : null}
                  {selected.commercialAssets &&
                    selected.commercialAssets.length > 0 && (
                      <section
                        className="commercial-assets"
                        aria-labelledby="image-commercial-assets-title"
                      >
                        <header>
                          <small>Supporting Media</small>
                          <h3 id="image-commercial-assets-title">
                            Commercial Assets
                          </h3>
                        </header>
                        <div>
                          {selected.commercialAssets.map((asset) => (
                            <figure key={asset.kind}>
                              <ContainedMediaImage
                                src={asset.previewUrl}
                                alt={asset.label}
                              />
                              <figcaption>
                                <strong>{asset.label}</strong>
                                <span>{asset.status}</span>
                              </figcaption>
                            </figure>
                          ))}
                        </div>
                      </section>
                    )}
                </aside>
              )}
            </div>
          )}

          {!loading && data.totalPages > 1 && (
            <nav
              className="asset-pagination"
              aria-label="Asset Library pagination"
            >
              <button
                disabled={data.page <= 1}
                onClick={() => setPage((current) => current - 1)}
                type="button"
              >
                <ChevronLeft size={16} />
                Previous
              </button>
              <span>
                Page {data.page} of {data.totalPages}
              </span>
              <button
                disabled={data.page >= data.totalPages}
                onClick={() => setPage((current) => current + 1)}
                type="button"
              >
                Next
                <ChevronRight size={16} />
              </button>
            </nav>
          )}
          {preview && (
            <div
              className={`asset-preview${previewNavigable ? " asset-preview--navigable" : ""}`}
              role="dialog"
              aria-modal="true"
              aria-label={previewNavigable ? `${preview.displayName || `Asset #${preview.assetId}`} full-size preview` : `Asset ${preview.assetId} preview`}
              onMouseDown={(event) => {
                if (event.target === event.currentTarget) closePreview();
              }}
            >
              <button
                className="asset-preview__close"
                aria-label="Close preview"
                onClick={closePreview}
                type="button"
              >
                <X />
              </button>
              {previewNavigable && <button className="asset-preview__previous" aria-label="Previous image" disabled={displayedSingleImages.findIndex((item) => item.libraryItemId === preview.libraryItemId) <= 0} onClick={() => movePreview(-1)} type="button"><ArrowLeft /></button>}
              <div>
                {preview.imageUrl ? (
                  <ContainedMediaImage
                    alt={`${preview.displayName || `Asset #${preview.assetId}`} preview`}
                    src={previewImageUrl(preview.imageUrl) || preview.imageUrl}
                  />
                ) : (
                  <span>Media unavailable</span>
                )}
                {!previewNavigable && <p>Asset #{preview.assetId}</p>}
                {originalImageUrl(preview.imageUrl) && <a href={originalImageUrl(preview.imageUrl)!} target="_blank" rel="noreferrer">View Full Resolution</a>}
              </div>
              {previewNavigable && <button className="asset-preview__next" aria-label="Next image" disabled={displayedSingleImages.findIndex((item) => item.libraryItemId === preview.libraryItemId) >= displayedSingleImages.length - 1} onClick={() => movePreview(1)} type="button"><ArrowRight /></button>}
            </div>
          )}
          {salePreparationAsset?.assetId && (
            <StandaloneSalePreparationDialog
              asset={salePreparationAsset}
              retry={
                salePreparationAsset.standaloneSalePreparation?.status ===
                "NEEDS_ATTENTION"
              }
              onClose={() => setSalePreparationAsset(null)}
              onStarted={(result) => {
                standalonePreparationStarted(
                  salePreparationAsset.assetId!,
                  result,
                );
                setSalePreparationAsset(null);
              }}
            />
          )}
          {reassignDestinationAsset?.assetId && (
            <StandaloneSalePreparationDialog
              asset={reassignDestinationAsset}
              reassign
              onClose={() => setReassignDestinationAsset(null)}
              onStarted={(result) => {
                standalonePreparationStarted(reassignDestinationAsset.assetId!, result);
                setActionMessage(`Destination changed to ${result.destinations[0] === "CHAT" ? "Chat" : "TG Wall"}.`);
                setReassignDestinationAsset(null);
                setVersion((current) => current + 1);
              }}
            />
          )}
          {sellingModeAsset && (
            <div className="sale-preparation-dialog photoshoot-selling-mode-dialog" role="dialog" aria-modal="true" aria-labelledby="reassign-selling-mode-title">
              <div>
                <header>
                  <div><small>Photoshoot Commerce</small><h2 id="reassign-selling-mode-title">Reassign Photoshoot</h2></div>
                  <button aria-label="Close selling mode dialog" onClick={() => setSellingModeAsset(null)} type="button"><X size={18} /></button>
                </header>
                <p><strong>{sellingModeAsset.fileName}</strong></p>
                <p>Current selling mode: <strong>{sellingModeAsset.sellingMode || "SESSION"}</strong></p>
                <div className="photoshoot-selling-mode-dialog__options">
                  <label className={sellingModeSelection === "SESSION" ? "is-selected" : ""}>
                    <input checked={sellingModeSelection === "SESSION"} name="photoshoot-selling-mode" onChange={() => setSellingModeSelection("SESSION")} type="radio" />
                    <span><strong>Session</strong><small>Sell the Photoshoot sequentially through the existing Photoshoot Session commerce flow.</small></span>
                  </label>
                  <label className={sellingModeSelection === "BUNDLE" ? "is-selected" : ""}>
                    <input checked={sellingModeSelection === "BUNDLE"} name="photoshoot-selling-mode" onChange={() => setSellingModeSelection("BUNDLE")} type="radio" />
                    <span><strong>Bundle</strong><small>Sell the complete Photoshoot as one multi-image set through the existing Bundle commerce flow.</small></span>
                  </label>
                </div>
                <p><strong>Sales channel</strong></p>
                {sellingModeSelection === "BUNDLE" ? <div className="photoshoot-selling-mode-dialog__options">
                  <label className={sellingChannelSelection === "CHAT" ? "is-selected" : ""}>
                    <input checked={sellingChannelSelection === "CHAT"} name="photoshoot-sales-channel" onChange={() => setSellingChannelSelection("CHAT")} type="radio" />
                    <span><strong>Chat</strong><small>Sell this Bundle directly in customer conversations.</small></span>
                  </label>
                  <label className={sellingChannelSelection === "CONTENT_WALL" ? "is-selected" : ""}>
                    <input checked={sellingChannelSelection === "CONTENT_WALL"} name="photoshoot-sales-channel" onChange={() => setSellingChannelSelection("CONTENT_WALL")} type="radio" />
                    <span><strong>Wall</strong><small>Prepare and publish this Bundle through Ava&apos;s Content Wall.</small></span>
                  </label>
                </div> : <p className="photoshoot-selling-mode__guidance">Session selling uses the existing Chat workflow.</p>}
                <footer>
                  <button disabled={sellingModeSaving} onClick={() => setSellingModeAsset(null)} type="button">Cancel</button>
                  <button className="asset-primary-action" disabled={sellingModeSaving || (sellingModeSelection === (sellingModeAsset.sellingMode || "SESSION") && (sellingModeSelection !== "BUNDLE" || sellingChannelSelection === (sellingModeAsset.bundleSalesChannel || "CHAT")))} onClick={() => void reassignSellingMode()} type="button">
                    {sellingModeSaving ? "Reassigning..." : "Reassign"}
                  </button>
                </footer>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
