import { Check, Pencil, X } from "lucide-react";
import { useState } from "react";
import { ContainedMediaImage } from "../../shared/ui/ContainedMediaImage";
import { BundleTeaserEditor, type SelectiveBlurSavePayload } from "./BundleTeaserEditor";
import type { AssetLibraryItem, BundleTeaserReadiness, StandaloneSalePreparation } from "./types";

type StandaloneSaleDestination = "CHAT" | "CONTENT_VAULT";
type TeaserStyle = "FULL_BLUR" | "SELECTIVE_BLUR";
const DEFAULT_SINGLE_IMAGE_PRICE_MINOR = 999;

const initialDestination = (preparation?: StandaloneSalePreparation | null): StandaloneSaleDestination => {
  if (preparation?.destinations?.includes("CHAT")) return "CHAT";
  if (preparation?.destinations?.includes("CONTENT_VAULT")) return "CONTENT_VAULT";
  return "CHAT";
};

const minorUnits = (value: string) => {
  if (!/^\d+(?:\.\d{1,2})?$/.test(value.trim())) return null;
  const minor = Math.round(Number(value) * 100);
  return Number.isSafeInteger(minor) && minor >= 300 && minor <= 50000 ? minor : null;
};

export function StandaloneSalePreparationDialog({ asset, retry = false, reassign = false, onClose, onStarted }: {
  asset: AssetLibraryItem; retry?: boolean; reassign?: boolean; onClose: () => void;
  onStarted: (value: StandaloneSalePreparation) => void;
}) {
  const initial = asset.standaloneSalePreparation;
  const initialChatTeaser = (initial?.teasers || []).find((item) => item.distributionUse === "CHAT") || null;
  const initialVaultTeaser = (initial?.teasers || []).find((item) => item.distributionUse === "CONTENT_VAULT") || null;
  const [price, setPrice] = useState(((initial?.priceMinor ?? DEFAULT_SINGLE_IMAGE_PRICE_MINOR) / 100).toFixed(2));
  const currentDestination = initialDestination(initial);
  const [destination, setDestination] = useState<StandaloneSaleDestination>(() => reassign
    ? currentDestination === "CHAT" ? "CONTENT_VAULT" : "CHAT"
    : currentDestination);
  const [preparation, setPreparation] = useState<StandaloneSalePreparation | null>(initial || null);
  const [chatTeaserDraft, setChatTeaserDraft] = useState(initialChatTeaser);
  const [vaultTeaserDraft, setVaultTeaserDraft] = useState(initialVaultTeaser);
  const [vaultStyle, setVaultStyle] = useState<TeaserStyle>(() =>
    initial?.destinations?.includes("CONTENT_VAULT")
      ? initial.teaserStyle || initialVaultTeaser?.teaserStyle || "FULL_BLUR"
      : initialVaultTeaser?.teaserStyle || "FULL_BLUR");
  const [editing, setEditing] = useState<StandaloneSaleDestination | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const priceMinor = minorUnits(price);
  const chatSelected = destination === "CHAT", vaultSelected = destination === "CONTENT_VAULT";
  const chatTeaserReady = chatTeaserDraft?.status === "READY";
  const vaultSelectiveTeaserReady = vaultTeaserDraft?.status === "READY"
    && vaultTeaserDraft.teaserStyle === "SELECTIVE_BLUR";
  const saveSelectiveTeaser = async (use: StandaloneSaleDestination, payload: SelectiveBlurSavePayload) => {
    const path = use === "CHAT" ? "chat" : "content_vault";
    const response = await fetch(`/api/v1/assets/${asset.assetId}/commercial-teasers/${path}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    const result = await response.json().catch(() => null) as (StandaloneSalePreparation & { detail?: string }) | null;
    if (!response.ok || !result) throw new Error(result?.detail || "Unable to save selective teaser.");
    setPreparation(result);
    const saved = (result.teasers || []).find((item) => item.distributionUse === use) || null;
    if (use === "CHAT") setChatTeaserDraft(saved);
    else setVaultTeaserDraft(saved);
  };
  const submit = async () => {
    if (!asset.assetId || priceMinor == null || saving) { setError("Select a destination and enter a price between $3.00 and $500.00."); return; }
    setSaving(true); setError("");
    try {
      const response = await fetch(reassign
        ? `/api/v1/assets/${asset.assetId}/sale-destination`
        : `/api/v1/assets/${asset.assetId}/sale-preparation${retry ? "/retry" : ""}`, {
        method: reassign ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
          priceMinor, ...(reassign ? { destination } : { destinations: [destination] }),
          teaserStyle: destination === "CHAT" ? "SELECTIVE_BLUR" : vaultStyle,
        }),
      });
      const result = await response.json().catch(() => null) as (StandaloneSalePreparation & { detail?: string }) | null;
      if (!response.ok || !result) throw new Error(result?.detail || "Unable to prepare Asset for sale.");
      onClose(); onStarted(result);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to prepare Asset for sale."); }
    finally { setSaving(false); }
  };
  const activeTeaser = editing === "CONTENT_VAULT" ? vaultTeaserDraft : chatTeaserDraft;
  const editorState: BundleTeaserReadiness = {
    status: activeTeaser?.status || "NOT_CONFIGURED", statusLabel: editing === "CONTENT_VAULT" ? "Content Vault Teaser" : "Chat Teaser", commercialRole: "BUNDLE_PROMOTIONAL_TEASER",
    sourceAssetId: asset.assetId, teaserAssetId: activeTeaser?.derivedAssetId || null, blurStrength: activeTeaser?.blurStrength || 24,
    maskWidth: activeTeaser?.maskWidth || null, maskHeight: activeTeaser?.maskHeight || null,
    maskVersion: activeTeaser?.maskVersion || "selective_blur_mask_v1", maskUrl: activeTeaser?.maskUrl || null,
    previewUrl: activeTeaser?.previewUrl || null, error: null,
    candidates: asset.assetId ? [{ assetId: asset.assetId, shotOrder: 1, imageUrl: asset.imageUrl || `/api/v1/assets/${asset.assetId}/media` }] : [],
  };
  return <div className="sale-preparation-dialog" role="dialog" aria-modal="true" aria-labelledby="prepare-single-image-title"><div>
    <header className="single-image-sale-header"><div><small>Single Image</small><h2 id="prepare-single-image-title">{reassign ? "Reassign Sales Destination" : retry ? "Retry Preparation" : preparation?.foundationReady ? "Edit Sale Preparation" : "Prepare for Sale"}</h2></div><button className="sale-preparation-close" aria-label="Close Prepare for Sale" onClick={onClose} type="button"><X /></button></header>
    <div className="single-image-sale-preparation">{asset.imageUrl && <ContainedMediaImage alt={`${asset.displayName} preview`} src={asset.imageUrl} />}<div><strong>{asset.displayName || `Asset #${asset.assetId}`}</strong><p>Configure where this image can be sold.</p></div></div>
    {reassign && <p>Current Destination: <strong>{currentDestination === "CHAT" ? "Chat" : "TG Wall"}</strong></p>}
    <fieldset className="single-image-sale-destinations"><legend>Selling / Publishing</legend>
      <label className={chatSelected ? "is-selected" : ""}><input aria-label="Chat Selling" disabled={reassign && currentDestination === "CHAT"} type="radio" name="standalone-sale-destination" checked={chatSelected} onChange={() => setDestination("CHAT")} /><span className="destination-check" aria-hidden="true">{chatSelected && <Check />}</span><span><strong>Chat Selling</strong><small>Selective teaser for 1:1 sales</small></span></label>
      <label className={vaultSelected ? "is-selected" : ""}><input aria-label="Ava's Content Vault" disabled={reassign && currentDestination === "CONTENT_VAULT"} type="radio" name="standalone-sale-destination" checked={vaultSelected} onChange={() => setDestination("CONTENT_VAULT")} /><span className="destination-check" aria-hidden="true">{vaultSelected && <Check />}</span><span><strong>Ava&apos;s Content Vault</strong><small>Full-blur teaser for Vault posts</small></span></label>
    </fieldset>
    {chatSelected && <section className="single-image-teaser-choice"><div className="single-image-teaser-heading"><strong>Chat Teaser</strong><span>Selective Blur</span></div><p>Protect the reveal while keeping enough visible to sell.</p>{chatTeaserDraft?.previewUrl && <ContainedMediaImage alt="Chat selective blur teaser" src={`${chatTeaserDraft.previewUrl}?v=${Date.now()}`} />}{chatTeaserReady && <em><Check /> Teaser Ready</em>}<button className="sale-preparation-secondary" type="button" onClick={() => setEditing("CHAT")}><Pencil />{chatTeaserReady ? "Replace Selective Teaser" : "Create Selective Teaser"}</button>{!chatTeaserReady && <small className="single-image-teaser-requirement">Create, save, and accept a Chat teaser before reassigning.</small>}</section>}
    {vaultSelected && <><fieldset className="single-image-vault-teaser-styles"><legend>Teaser Style</legend><label><input type="radio" name="vault-teaser-style" checked={vaultStyle === "FULL_BLUR"} onChange={() => setVaultStyle("FULL_BLUR")} />Full Blur</label><label><input type="radio" name="vault-teaser-style" checked={vaultStyle === "SELECTIVE_BLUR"} onChange={() => setVaultStyle("SELECTIVE_BLUR")} />Selective Blur</label></fieldset>
      <section className="single-image-teaser-choice"><div className="single-image-teaser-heading"><strong>Content Vault Teaser</strong><span>{vaultStyle === "FULL_BLUR" ? "Full Blur" : "Selective Blur"}</span></div>{vaultStyle === "FULL_BLUR" ? <><p>A full blur will be used for the Wall preview.</p>{vaultTeaserDraft?.teaserStyle === "FULL_BLUR" && vaultTeaserDraft.previewUrl ? <ContainedMediaImage alt="Content Vault full blur teaser" src={vaultTeaserDraft.previewUrl} /> : <small>The preview will be created or reused during preparation.</small>}</> : <><p>Protect the reveal while keeping enough visible to encourage an unlock.</p>{vaultTeaserDraft?.teaserStyle === "SELECTIVE_BLUR" && vaultTeaserDraft.previewUrl && <ContainedMediaImage alt="Content Vault selective blur teaser" src={`${vaultTeaserDraft.previewUrl}?v=${Date.now()}`} />}{vaultTeaserDraft?.teaserStyle === "SELECTIVE_BLUR" && <em><Check /> Teaser Ready</em>}<button className="sale-preparation-secondary" type="button" onClick={() => setEditing("CONTENT_VAULT")}><Pencil />{vaultTeaserDraft?.teaserStyle === "SELECTIVE_BLUR" ? "Replace Selective Teaser" : "Edit Selective Teaser"}</button>{vaultTeaserDraft?.teaserStyle !== "SELECTIVE_BLUR" && <small>Save and accept a selective teaser before preparation.</small>}</>}</section></>}
    <label className="single-image-sale-price" htmlFor="single-image-sale-price"><span>Price</span><span className="single-image-sale-price__control"><small>USD</small><input aria-label="Price" id="single-image-sale-price" inputMode="decimal" min="3" max="500" step=".01" type="number" value={price} onChange={(event) => setPrice(event.target.value)} /></span><small>$3.00 – $500.00</small></label>
    {error && <p className="sale-preparation-error" role="alert">{error}</p>}
    <footer className="single-image-sale-footer"><button className="sale-preparation-secondary" onClick={onClose} type="button">Cancel</button><button className="sale-preparation-primary" disabled={priceMinor == null || saving || (chatSelected && !chatTeaserReady) || (vaultSelected && vaultStyle === "SELECTIVE_BLUR" && !vaultSelectiveTeaserReady)} onClick={() => void submit()} type="button">{saving ? (reassign ? "Reassigning..." : "Starting...") : reassign ? "Reassign" : preparation?.foundationReady ? "Save Changes" : retry ? "Retry Preparation" : "Prepare for Sale"}</button></footer>
    {editing && asset.assetId && <BundleTeaserEditor deliverableId="standalone" state={editorState} sourceAssetId={asset.assetId} onClose={() => setEditing(null)} onSaved={() => undefined} saveRequest={(payload) => saveSelectiveTeaser(editing, payload)} />}
  </div></div>;
}
