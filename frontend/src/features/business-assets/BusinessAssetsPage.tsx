import { useEffect, useState } from "react";
import { AlertTriangle, ChevronDown, ChevronLeft, ChevronRight, ImageOff, X } from "lucide-react";

import { PageHeader } from "../../shared/ui/PageHeader";
import type { BusinessAssetDetail, BusinessAssetItem, BusinessAssetListResponse, CommerceStatus, PhotoshootBusinessDetail } from "./types";
import "./business-assets.css";

const filters: ("All" | CommerceStatus)[] = ["All", "Analyzing", "Analysis Failed", "Ready", "Needs Upload", "Needs Media Link", "Chat Ready"];
const emptySummary = { total_business_assets: 0, chat_ready: 0, fulfillment_ready: 0, awaiting_destination: 0, waiting_for_media_link: 0, blocked: 0, recommendation_ready: 0 };
const emptyData: BusinessAssetListResponse = { items: [], summary: emptySummary, total: 0, page: 1, pageSize: 24, totalPages: 1 };

const label = (value: unknown) => String(value || "Not available").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const valueOf = (data: Record<string, unknown> | null, ...keys: string[]) => {
  for (const key of keys) if (data?.[key] !== undefined && data[key] !== null && data[key] !== "") return label(data[key]);
  return "Not registered";
};

function Status({ value }: { value: string }) {
  const tone = value === "Chat Ready" || value === "Ready" || value === "Complete" || value === "Verified" ? " business-status--ready" : "";
  return <span className={`business-status${tone}`}>{label(value)}</span>;
}

function ReadOnlyRow({ name, value }: { name: string; value: string }) {
  return <div><dt>{name}</dt><dd><Status value={value} /></dd></div>;
}

const providerFieldLabels: Record<string, string> = {
  classification: "Classification", confidence: "Confidence", detectedCategories: "Detected Categories",
  explicitScores: "Explicit Scores", providerVersion: "Provider Version", shortDescription: "Short Description",
  scene: "Scene", objects: "Objects", people: "People", environment: "Environment", lighting: "Lighting",
  composition: "Composition", tags: "Tags", mood: "Mood", theme: "Theme", visualStyle: "Visual Style",
  lifestyleContext: "Lifestyle Context", suggestedCollections: "Suggested Collections", searchPhrases: "Search Phrases",
  semanticSummary: "Semantic Summary", assetCategory: "Asset Category",
  recommendedProducts: "Recommended Products", suggestedPricingTier: "Suggested Pricing Tier",
  searchKeywords: "Search Keywords", decisionEngineSummary: "Decision Engine Summary",
};

const displayValue = (key: string, value: unknown) => {
  if (key === "confidence" && typeof value === "number") return `${Math.round(value * 100)}%`;
  if (Array.isArray(value)) return value.join(", ");
  if (value && typeof value === "object") return Object.entries(value as Record<string, unknown>).map(([name, score]) => `${label(name)}: ${typeof score === "number" ? `${Math.round(score * 100)}%` : String(score)}`).join(", ");
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
};

function ProviderAnalysis({ name, status, values, expanded, onToggle }: { name: string; status: string; values: Record<string, unknown>; expanded: boolean; onToggle: () => void }) {
  const fields = Object.entries(values).filter(([key, value]) => key !== "status" && value !== null && value !== "" && (!Array.isArray(value) || value.length > 0));
  return <div className={`provider-analysis${expanded ? " provider-analysis--expanded" : ""}`}>
    <button aria-expanded={expanded} className="provider-analysis__toggle" onClick={onToggle} type="button">
      <span><ChevronDown aria-hidden="true" size={15} />{name}</span><Status value={status} />
    </button>
    <div className="provider-analysis__content" aria-hidden={!expanded}><dl>{fields.map(([key, value]) => <div key={key}><dt>{providerFieldLabels[key] || label(key)}</dt><dd>{displayValue(key, value)}</dd></div>)}</dl></div>
  </div>;
}

const visibleProviderValues = (provider: string, values: Record<string, unknown>) => {
  if (provider !== "CONTENT_INTELLIGENCE") return values;
  const currentValues = { ...values };
  delete currentValues.commerceClassification;
  delete currentValues.contentRating;
  return currentValues;
};

export function BusinessAssetsPage() {
  const [data, setData] = useState(emptyData);
  const [filter, setFilter] = useState<"All" | CommerceStatus>("All");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<BusinessAssetDetail | null>(null);
  const [selectedPhotoshoot, setSelectedPhotoshoot] = useState<PhotoshootBusinessDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [archiveTarget, setArchiveTarget] = useState<BusinessAssetItem | null>(null);
  const [archiving, setArchiving] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [expandedProviders, setExpandedProviders] = useState<Set<string>>(new Set());

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ page: String(page), page_size: "24" });
    if (filter !== "All") params.set("commerce_status", filter);
    setLoading(true);
    setError("");
    fetch(`/api/v1/business-assets?${params}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const body = await response.json() as BusinessAssetListResponse & { detail?: string };
        if (!response.ok) throw new Error(body.detail || "Unable to load the Commerce Library.");
        return body;
      })
      .then(setData)
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Unable to load the Commerce Library."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [filter, page, refreshKey]);

  const openDetail = async (item: BusinessAssetItem) => {
    setDetailLoading(true);
    setError("");
    try {
      const response = await fetch(item.itemKind === "photoshoot" ? `/api/v1/business-assets/photoshoots/${item.deliverableId}` : `/api/v1/business-assets/${item.asset_id}`, { cache: "no-store" });
      if (item.itemKind === "photoshoot") {
        const body = await response.json() as PhotoshootBusinessDetail & { detail?: string };
        if (!response.ok) throw new Error(body.detail || "Unable to load Photoshoot details.");
        setSelected(null); setSelectedPhotoshoot(body); return;
      }
      const body = await response.json() as BusinessAssetDetail & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Unable to load Business Asset details.");
      setExpandedProviders(new Set());
      setSelected(body);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load Business Asset details.");
    } finally {
      setDetailLoading(false);
    }
  };

  const confirmArchive = async () => {
    if (!archiveTarget) return;
    setArchiving(true);
    setError("");
    try {
      const response = await fetch(archiveTarget.itemKind === "photoshoot" ? `/api/v1/business-assets/photoshoots/${archiveTarget.deliverableId}/archive` : `/api/v1/business-assets/${archiveTarget.asset_id}/archive`, { method: "POST" });
      const body = await response.json() as { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Unable to archive the Commerce Asset.");
      setArchiveTarget(null);
      setSelected(null);
      setSelectedPhotoshoot(null);
      setRefreshKey((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to archive the Commerce Asset.");
    } finally {
      setArchiving(false);
    }
  };

  return <section className="business-assets-page">
    <PageHeader title="Commerce Library" description="Review every registered Business Asset from analysis through chat readiness." />
    <div className="commerce-filter" role="group" aria-label="Commerce status filter">
      {filters.map((option) => <button key={option} type="button" aria-pressed={filter === option} onClick={() => { setFilter(option); setPage(1); }}>{option}</button>)}
    </div>
    {error && <div className="business-state business-state--error" role="alert"><AlertTriangle size={18} />{error}</div>}
    {loading && <div className="business-state">Loading Commerce Library…</div>}
    {!loading && !error && !data.items.length && <div className="business-state"><strong>No Business Assets found.</strong><span>Registered Business Assets will appear here automatically.</span></div>}
    {!loading && data.items.length > 0 && <div className="commerce-table" role="table" aria-label="Commerce Library">
      <div className="commerce-table__header" role="row"><span>Preview</span><span>Asset Name</span><span>Current Status</span><span>Commerce Status</span><span>Actions</span></div>
      {data.items.map((item) => <div className="commerce-table__row" key={item.deliverableId || item.asset_id} role="row">
        <button aria-label={`View details for ${item.asset_name || `Business Asset ${item.asset_id}`}`} className="commerce-table__row-details" disabled={detailLoading} onClick={() => void openDetail(item)} type="button">
          <span className="business-asset__media" role="cell">{item.imageUrl ? <img src={item.imageUrl} alt="" /> : <ImageOff />}</span>
          <span className="business-asset__identity" role="cell"><strong>{item.asset_name || `Business Asset ${item.asset_id}`}</strong><small>{item.itemKind === "photoshoot" ? `Photoshoot • ${item.shotCount} Images` : `Asset #${item.asset_id}`}</small></span>
          <span role="cell"><Status value={item.analysisStatus?.endsWith("_FAILED") ? item.analysisStatus : item.current_lifecycle || item.analysisStatus || "Analyzing"} /></span>
          <span role="cell"><Status value={item.commerceStatus} /></span>
        </button>
        <span className="commerce-table__action" role="cell"><button aria-label={`Archive ${item.asset_name || `Business Asset ${item.asset_id}`}`} className="commerce-archive-button" onClick={() => setArchiveTarget(item)} type="button">Archive</button></span>
      </div>)}
    </div>}
    {data.totalPages > 1 && <nav className="business-pagination" aria-label="Commerce Library pagination"><button disabled={page <= 1} onClick={() => setPage((value) => value - 1)}><ChevronLeft size={16} />Previous</button><span>Page {data.page} of {data.totalPages}</span><button disabled={page >= data.totalPages} onClick={() => setPage((value) => value + 1)}>Next<ChevronRight size={16} /></button></nav>}
    {selected && <aside className="business-detail" aria-label="Business Asset details"><header><div><small>Commerce Library</small><h2>{selected.item.asset_name || `Asset #${selected.item.asset_id}`}</h2></div><button aria-label="Close Business Asset details" onClick={() => setSelected(null)}><X /></button></header><div className="business-detail__body">
      <img src={selected.item.imageUrl} alt={selected.item.asset_name || `Asset ${selected.item.asset_id}`} />
      <section className="business-detail__section"><h3>Analysis</h3><div className="provider-analysis-list">
        {(["NUDENET", "VISION", "GROK", "CONTENT_INTELLIGENCE"] as const).map((provider) => {
          const name = { NUDENET: "NudeNet", VISION: "Vision", GROK: "Grok", CONTENT_INTELLIGENCE: "Content Intelligence" }[provider];
          const status = provider === "CONTENT_INTELLIGENCE" && selected.contentIntelligence ? valueOf(selected.contentIntelligence, "status") : selected.analysis[provider];
          return <ProviderAnalysis key={provider} name={name} status={status} values={visibleProviderValues(provider, selected.analysisResults?.[provider] || {})} expanded={expandedProviders.has(provider)} onToggle={() => setExpandedProviders((current) => { const next = new Set(current); if (next.has(provider)) next.delete(provider); else next.add(provider); return next; })} />;
        })}
        {selected.item.analysisStatus?.endsWith("_FAILED") && <ReadOnlyRow name="Analysis Error" value={valueOf(selected.commerceRegistration, "error_message", "error_code")} />}
      </div></section>
      <section className="business-detail__section"><h3>Commerce</h3><dl>
        <ReadOnlyRow name="Fanvue" value={valueOf(selected.fulfillment, "provider_processing_status", "lifecycle_state")} />
        <ReadOnlyRow name="Media Link" value={valueOf(selected.fulfillment, "media_link_verification_state")} />
        <ReadOnlyRow name="Chat Status" value={valueOf(selected.chatCommerce, "availability_state", "chat_ready")} />
      </dl><div className="commerce-actions"><button className="commerce-archive-button" onClick={() => setArchiveTarget(selected.item)} type="button">Archive</button></div></section>
    </div></aside>}
    {selectedPhotoshoot && <aside className="business-detail" aria-label="Photoshoot details"><header><div><small>Photoshoot • {selectedPhotoshoot.item.shotCount} Images</small><h2>{selectedPhotoshoot.item.asset_name}</h2></div><button aria-label="Close Photoshoot details" onClick={() => setSelectedPhotoshoot(null)}><X /></button></header><div className="business-detail__body">
      {selectedPhotoshoot.item.description && <p className="photoshoot-commerce-description">{selectedPhotoshoot.item.description}</p>}<img src={selectedPhotoshoot.item.imageUrl} alt={selectedPhotoshoot.item.asset_name || "Photoshoot cover"} />
      <section className="business-detail__section"><h3>Photoshoot Intelligence</h3><dl>{Object.entries(selectedPhotoshoot.photoshootIntelligence).filter(([, value]) => value).map(([key, value]) => <div key={key}><dt>{label(key)}</dt><dd>{displayValue(key, value)}</dd></div>)}</dl></section>
      <section className="business-detail__section"><h3>Ordered Shots</h3><div className="photoshoot-commerce-shots">{selectedPhotoshoot.members.map((member) => <figure key={member.assetId}><img src={member.imageUrl} alt={`Shot ${member.shotOrder}`} /><figcaption>Shot {member.shotOrder}</figcaption></figure>)}</div></section>
      <section className="business-detail__section"><h3>Commerce</h3><ReadOnlyRow name="Status" value={selectedPhotoshoot.commerceStatus} /><div className="commerce-actions"><button className="commerce-archive-button" onClick={() => setArchiveTarget(selectedPhotoshoot.item)} type="button">Archive</button></div></section>
      <details className="business-detail__section"><summary>Advanced / Technical</summary><dl>{Object.entries(selectedPhotoshoot.technical).map(([key, value]) => <div key={key}><dt>{label(key)}</dt><dd>{String(value ?? "")}</dd></div>)}</dl></details>
    </div></aside>}
    {archiveTarget && <div className="commerce-archive-dialog" role="dialog" aria-modal="true" aria-labelledby="archive-commerce-title"><div>
      <h2 id="archive-commerce-title">Archive Commerce Asset?</h2>
      <p>This will remove the asset from active commerce, sales rotation, Decision Engine inventory, and future product eligibility.</p>
      <p>The asset will be preserved in the Commerce Archive and may be restored later.</p>
      <footer><button disabled={archiving} onClick={() => setArchiveTarget(null)} type="button">Cancel</button><button className="commerce-archive-dialog__confirm" disabled={archiving} onClick={() => void confirmArchive()} type="button">{archiving ? "Archiving…" : "Archive"}</button></footer>
    </div></div>}
  </section>;
}
