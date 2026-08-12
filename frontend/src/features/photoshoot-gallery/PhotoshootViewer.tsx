import { useEffect, useState } from "react";
import { Video } from "lucide-react";

import { ContainedMediaImage } from "../../shared/ui/ContainedMediaImage";
import { BundleSellingPanel, SessionSellingPanel } from "../asset-library/PhotoshootSalePreparation";
import type { BundleSalesChannel, CommercialAsset, PhotoshootSellingMode, SalePreparationReadiness } from "../asset-library/types";
import "./photoshoot-gallery.css";
import { videoStudioLink } from "../../infrastructure/api/videoStudioApi";

export type RegistrationState = "PHOTOSHOOT_COMPLETE" | "IN_ASSET_LIBRARY" | "REGISTERED" | "ARCHIVED";
export type PhotoshootDetail = {
  deliverableId: string;
  name: string;
  description: string | null;
  completedAt: string;
  shotCount: number;
  imageUrl: string | null;
  registrationState: RegistrationState;
  sellingMode: PhotoshootSellingMode;
  bundleSalesChannel?: BundleSalesChannel | null;
  intelligence: Record<string, unknown>;
  productionIntelligence: Record<string, unknown>;
  members: { assetId: number; shotOrder: number; imageUrl: string; intelligence: Record<string, unknown> }[];
  technical: Record<string, unknown>;
  commercialAssets?: CommercialAsset[];
};

async function readJson<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null) as T | { detail?: string } | null;
  const detail = body && typeof body === "object" && "detail" in body ? String(body.detail || "") : "";
  if (!response.ok || !body) throw new Error(detail || `Request failed (${response.status}).`);
  return body as T;
}

const registrationLabel = (state: RegistrationState) => state === "PHOTOSHOOT_COMPLETE" ? "Not Added" : state === "IN_ASSET_LIBRARY" ? "In Asset Library" : state === "REGISTERED" ? "Registered" : "Archived";
const productionFields = [
  ["theme", "Theme"], ["story", "Story"], ["experience", "Experience"],
  ["emotional_journey", "Emotional Journey"], ["hero_shot", "Hero Shot"],
  ["cover_shot", "Cover Shot"], ["teaser_shot", "Teaser Shot"],
  ["thumbnail_shot", "Thumbnail Shot"],
] as const;
const shotFields = [
  ["sequence_role", "Sequence Role"], ["summary", "Summary"], ["classification", "Classification"],
  ["suggested_content_uses", "Suggested Uses"], ["hero_suitability", "Hero Suitability"],
  ["cover_suitability", "Cover Suitability"], ["thumbnail_suitability", "Thumbnail Suitability"],
  ["teaser_suitability", "Teaser Suitability"],
] as const;

function conciseValue(value: unknown): string | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (["string", "number"].includes(typeof value)) return String(value);
  if (Array.isArray(value)) {
    const items = value.filter((item) => ["string", "number", "boolean"].includes(typeof item)).map(String);
    return items.length ? items.join(", ") : null;
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["rating", "score", "value", "recommended", "suitable"]) {
      const concise = conciseValue(record[key]);
      if (concise) return concise;
    }
  }
  return null;
}

function IntelligenceCard({ title, intelligence, fields }: {
  title: string;
  intelligence: Record<string, unknown>;
  fields: ReadonlyArray<readonly [string, string]>;
}) {
  const values = fields.flatMap(([key, fieldLabel]) => {
    const value = conciseValue(intelligence[key]);
    return value ? [{ key, label: fieldLabel, value }] : [];
  });
  return <article className="photoshoot-intelligence-card">
    <header><h2>{title}</h2></header>
    {values.length > 0 && <dl className="photoshoot-intelligence-fields">{values.map((field) => <div key={field.key}><dt>{field.label}</dt><dd>{field.value}</dd></div>)}</dl>}
  </article>;
}

export function PhotoshootViewer({ deliverableId, onClose, onAddToAssetLibrary, onCreateOffer,
  enableSessionSelling = false, initialSessionSellingDialog = null, onSessionSellingChange,
  onSellingModeChange }: {
  deliverableId: string;
  onClose: () => void;
  onAddToAssetLibrary?: (deliverableId: string) => Promise<RegistrationState>;
  onCreateOffer?: (deliverableId: string, selectedAssetId: number | null) => void;
  enableSessionSelling?: boolean;
  initialSessionSellingDialog?: "prepare" | "retry" | null;
  onSessionSellingChange?: (value: SalePreparationReadiness) => void;
  onSellingModeChange?: (value: PhotoshootSellingMode) => void;
}) {
  const [detail, setDetail] = useState<PhotoshootDetail | null>(null);
  const [selectedAssetId, setSelectedAssetId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [registering, setRegistering] = useState(false);
  const [savingMode, setSavingMode] = useState(false);
  const [savingChannel, setSavingChannel] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setDetail(null); setError(""); setSelectedAssetId(null);
    fetch(`/api/v1/photoshoot-gallery/${encodeURIComponent(deliverableId)}`, { cache: "no-store", signal: controller.signal })
      .then((response) => readJson<PhotoshootDetail>(response))
      .then((result) => { setDetail({ ...result, sellingMode: result.sellingMode || "SESSION", bundleSalesChannel: result.sellingMode === "BUNDLE" ? result.bundleSalesChannel || "CHAT" : null }); setSelectedAssetId(result.members[0]?.assetId ?? null); })
      .catch((reason: unknown) => {
        if ((reason as { name?: string }).name !== "AbortError") setError(reason instanceof Error ? reason.message : "Unable to load Photoshoot.");
      });
    return () => controller.abort();
  }, [deliverableId]);

  const register = async () => {
    if (!onAddToAssetLibrary || registering) return;
    setRegistering(true); setError("");
    try {
      const registrationState = await onAddToAssetLibrary(deliverableId);
      setDetail((current) => current ? { ...current, registrationState } : current);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to register Photoshoot.");
    } finally { setRegistering(false); }
  };

  const changeSellingMode = async (sellingMode: PhotoshootSellingMode) => {
    if (!detail || detail.sellingMode === sellingMode || savingMode) return;
    setSavingMode(true); setError("");
    try {
      const result = await fetch(`/api/v1/assets/photoshoots/${encodeURIComponent(deliverableId)}/selling-mode`, {
        method: "PUT", headers: { "content-type": "application/json" },
        body: JSON.stringify({ sellingMode }),
      }).then((response) => readJson<{ sellingMode: PhotoshootSellingMode }>(response));
      setDetail((current) => current ? { ...current, sellingMode: result.sellingMode, bundleSalesChannel: result.sellingMode === "BUNDLE" ? current.bundleSalesChannel || "CHAT" : current.bundleSalesChannel } : current);
      onSellingModeChange?.(result.sellingMode);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to change selling mode.");
    } finally { setSavingMode(false); }
  };

  const changeBundleSalesChannel = async (bundleSalesChannel: BundleSalesChannel) => {
    if (!detail || detail.sellingMode !== "BUNDLE" || detail.bundleSalesChannel === bundleSalesChannel || savingChannel) return;
    setSavingChannel(true); setError("");
    try {
      const result = await fetch(`/api/v1/assets/photoshoots/${encodeURIComponent(deliverableId)}/bundle-sales-channel`, {
        method: "PUT", headers: { "content-type": "application/json" },
        body: JSON.stringify({ bundleSalesChannel }),
      }).then((response) => readJson<{ bundleSalesChannel: BundleSalesChannel }>(response));
      setDetail((current) => current ? { ...current, bundleSalesChannel: result.bundleSalesChannel } : current);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to change Bundle sales channel.");
    } finally { setSavingChannel(false); }
  };

  const selectedMember = detail?.members.find((member) => member.assetId === selectedAssetId) || null;
  return <section className="photoshoot-detail-page">
    <header className="photoshoot-detail-header">
      <div><p className="photoshoot-gallery-page__eyebrow">Photoshoot</p>{detail && <p>{new Date(detail.completedAt).toLocaleDateString()} <span aria-hidden="true">·</span> {detail.shotCount} images</p>}</div>
      <div className="photoshoot-detail-header__actions">{selectedMember && <button type="button" onClick={() => { window.location.href = videoStudioLink({ type: "photoshoot_shot", id: String(selectedMember.assetId), previewUrl: selectedMember.imageUrl, label: `Shot ${selectedMember.shotOrder}`, context: `Production Photoshoot · Shot ${selectedMember.shotOrder}` }); }}><Video size={16} /> Create Video</button>}{detail && onCreateOffer && <button type="button" onClick={() => onCreateOffer(deliverableId, selectedAssetId)}>Create Offer</button>}<button type="button" className="photoshoot-detail-close" onClick={onClose}>Close</button></div>
    </header>
    {error && <div role="alert">{error}</div>}
    {!detail && !error && <div className="photoshoot-gallery-empty">Loading Photoshoot...</div>}
    {detail && <>
      <div className="photoshoot-detail-filmstrip" aria-label="Photoshoot filmstrip">
        {detail.members.map((member) => <button type="button" className={member.assetId === selectedAssetId ? "photoshoot-detail-shot photoshoot-detail-shot--selected" : "photoshoot-detail-shot"} key={member.assetId} onClick={() => setSelectedAssetId(member.assetId)} aria-label={`Select shot ${member.shotOrder}`} aria-pressed={member.assetId === selectedAssetId}>
          <span>Shot {member.shotOrder}</span>
          <div className="photoshoot-detail-shot__media"><ContainedMediaImage src={member.imageUrl} alt={`Shot ${member.shotOrder}`} /></div>
        </button>)}
      </div>
      <div className="photoshoot-intelligence-cards" aria-label="Intelligence Inspector">
        <IntelligenceCard title="Photoshoot Summary" intelligence={detail.productionIntelligence || {}} fields={productionFields} />
        <IntelligenceCard title={`Selected Shot — Shot ${selectedMember?.shotOrder ?? 1}`} intelligence={selectedMember?.intelligence || {}} fields={shotFields} />
      </div>
      {detail.commercialAssets && detail.commercialAssets.length > 0 && <section className="commercial-assets" aria-labelledby="photoshoot-commercial-assets-title">
        <header><small>Supporting Media</small><h2 id="photoshoot-commercial-assets-title">Commercial Assets</h2></header>
        <div>{detail.commercialAssets.map((asset) => <figure key={`${asset.kind}-${asset.assetId || asset.previewUrl}`}><ContainedMediaImage src={asset.previewUrl} alt={asset.label} /><figcaption><strong>{asset.label}</strong><span>{asset.status}</span></figcaption></figure>)}</div>
      </section>}
      {enableSessionSelling && <section className="photoshoot-selling-mode" aria-labelledby="selling-mode-title">
        <header><div><small>Commercial Configuration</small><h2 id="selling-mode-title">Selling Mode</h2></div></header>
        <div className="photoshoot-selling-mode__options">
          <button type="button" aria-pressed={detail.sellingMode === "SESSION"} disabled={savingMode} onClick={() => void changeSellingMode("SESSION")}><strong>Session</strong><span>Sell this Photoshoot progressively, one asset at a time.</span></button>
          <button type="button" aria-pressed={detail.sellingMode === "BUNDLE"} disabled={savingMode} onClick={() => void changeSellingMode("BUNDLE")}><strong>Bundle</strong><span>Sell the complete Photoshoot together as one bundle.</span></button>
        </div>
        {savingMode && <p role="status">Saving selling mode...</p>}
      </section>}
      {enableSessionSelling && detail.sellingMode === "BUNDLE" && <section className="photoshoot-selling-mode" aria-labelledby="bundle-sales-channel-title">
        <header><div><small>Commercial Configuration</small><h2 id="bundle-sales-channel-title">Sell Bundle Through</h2></div></header>
        <div className="photoshoot-selling-mode__options">
          <button type="button" aria-pressed={(detail.bundleSalesChannel || "CHAT") === "CHAT"} disabled={savingChannel} onClick={() => void changeBundleSalesChannel("CHAT")}><strong>Chats</strong><span>Sell this Bundle directly in customer conversations.</span></button>
          <button type="button" aria-pressed={detail.bundleSalesChannel === "CONTENT_WALL"} disabled={savingChannel} onClick={() => void changeBundleSalesChannel("CONTENT_WALL")}><strong>Ava&apos;s Content Wall</strong><span>Sell this Bundle through Ava&apos;s Content Wall.</span></button>
        </div>
        {savingChannel && <p role="status">Saving Bundle sales channel...</p>}
      </section>}
      {enableSessionSelling && detail.sellingMode === "SESSION" && <SessionSellingPanel deliverableId={deliverableId}
        initialDialog={initialSessionSellingDialog} onReadinessChange={onSessionSellingChange} />}
      {enableSessionSelling && detail.sellingMode === "BUNDLE" && <BundleSellingPanel deliverableId={deliverableId} salesChannel={detail.bundleSalesChannel || "CHAT"} onReadinessChange={onSessionSellingChange} />}
      <div className="photoshoot-detail-sections">
        <details><summary>Commerce</summary><div className="photoshoot-detail-section-content"><p><strong>Asset Library status</strong> {registrationLabel(detail.registrationState)}</p>{detail.registrationState === "PHOTOSHOOT_COMPLETE" && onAddToAssetLibrary && <button type="button" disabled={registering} onClick={() => void register()}>Add to Asset Library</button>}</div></details>
        <details><summary>Technical Details</summary><div className="photoshoot-detail-section-content"><dl>{Object.entries(detail.technical).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value ?? "")}</dd></div>)}</dl></div></details>
      </div>
    </>}
  </section>;
}
