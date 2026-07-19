import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, ImageOff, Search, X } from "lucide-react";

import { PageHeader } from "../../shared/ui/PageHeader";
import type { BusinessAssetDetail, BusinessAssetItem, BusinessAssetListResponse } from "./types";
import "./business-assets.css";

const emptySummary = { total_business_assets: 0, chat_ready: 0, fulfillment_ready: 0, awaiting_destination: 0, waiting_for_media_link: 0, blocked: 0, recommendation_ready: 0 };
const emptyData: BusinessAssetListResponse = { items: [], summary: emptySummary, total: 0, page: 1, pageSize: 24, totalPages: 1 };

const label = (value: unknown) => String(value || "Not available").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const boolLabel = (value: unknown) => value === true ? "Ready" : value === false ? "Not ready" : "Not available";

function Status({ value, positive = false }: { value: string; positive?: boolean }) {
  return <span className={`business-status${positive ? " business-status--ready" : ""}`}>{label(value)}</span>;
}

function DetailSection({ title, data }: { title: string; data: Record<string, unknown> | null }) {
  if (!data) return <section className="business-detail__section"><h3>{title}</h3><p>Not registered yet.</p></section>;
  const entries = Object.entries(data).filter(([, value]) => value !== null && value !== "" && !Array.isArray(value) && typeof value !== "object");
  return <section className="business-detail__section"><h3>{title}</h3><dl>{entries.map(([key, value]) => <div key={key}><dt>{label(key)}</dt><dd>{typeof value === "boolean" ? (value ? "Yes" : "No") : String(value)}</dd></div>)}</dl></section>;
}

export function BusinessAssetsPage() {
  const [data, setData] = useState(emptyData);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [destination, setDestination] = useState("");
  const [readiness, setReadiness] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<BusinessAssetDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ page: String(page), page_size: "24" });
    if (search.trim()) params.set("search", search.trim());
    if (status) params.set("status", status);
    if (destination) params.set("destination", destination);
    if (readiness) params.set(readiness, "true");
    setLoading(true); setError("");
    fetch(`/api/v1/business-assets?${params}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => { const body = await response.json() as BusinessAssetListResponse & { detail?: string }; if (!response.ok) throw new Error(body.detail || "Unable to load Business Assets."); return body; })
      .then(setData)
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Unable to load Business Assets."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [search, status, destination, readiness, page]);

  const metrics = useMemo(() => [
    ["Business Assets", data.summary.total_business_assets], ["Chat Ready", data.summary.chat_ready],
    ["Recommendation Ready", data.summary.recommendation_ready], ["Fulfillment Ready", data.summary.fulfillment_ready],
    ["Awaiting Destination", data.summary.awaiting_destination], ["Needs Attention", data.summary.blocked + data.summary.waiting_for_media_link],
  ] as const, [data.summary]);

  const openDetail = async (item: BusinessAssetItem) => {
    setDetailLoading(true); setError("");
    try {
      const response = await fetch(`/api/v1/business-assets/${item.asset_id}`, { cache: "no-store" });
      const body = await response.json() as BusinessAssetDetail & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Unable to load Business Asset details.");
      setSelected(body);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load Business Asset details."); }
    finally { setDetailLoading(false); }
  };

  return <section className="business-assets-page">
    <PageHeader title="Business Assets" description="Monitor approved assets from intelligence through commerce and Sales Agent readiness." />
    <div className="business-metrics">{metrics.map(([name, value]) => <article key={name}><span>{name}</span><strong>{value}</strong></article>)}</div>
    <div className="business-toolbar">
      <label className="business-search"><Search size={16} /><span className="sr-only">Search Business Assets</span><input aria-label="Search Business Assets" placeholder="Search by asset name or ID" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} /></label>
      <label><span>Status</span><select aria-label="Lifecycle status" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}><option value="">All statuses</option><option>Chat Ready</option><option>Pending</option><option>Awaiting Destination</option><option>Waiting For Media Link</option><option>Blocked</option><option>Temporarily Unavailable</option><option>Retired</option></select></label>
      <label><span>Destination</span><select aria-label="Destination" value={destination} onChange={(event) => { setDestination(event.target.value); setPage(1); }}><option value="">All destinations</option><option value="TELEGRAM_WALL">Telegram Wall</option><option value="CUSTOMER_CONVERSATIONS">Customer Conversations</option><option value="BOTH">Both</option><option value="ARCHIVE_ONLY">Archive Only</option></select></label>
      <label><span>Readiness</span><select aria-label="Readiness" value={readiness} onChange={(event) => { setReadiness(event.target.value); setPage(1); }}><option value="">All assets</option><option value="recommendation_ready">Recommendation ready</option><option value="chat_ready">Chat ready</option><option value="fulfillment_ready">Fulfillment ready</option><option value="awaiting_destination">Awaiting destination</option><option value="waiting_for_media_link">Waiting for media link</option><option value="blocked">Blocked</option></select></label>
    </div>
    {error && <div className="business-state business-state--error" role="alert"><AlertTriangle size={18} />{error}</div>}
    {loading && <div className="business-state">Loading Business Assets…</div>}
    {!loading && !error && !data.items.length && <div className="business-state"><strong>No Business Assets found.</strong><span>Approved assets will appear here after commerce registration.</span></div>}
    {!loading && data.items.length > 0 && <div className="business-inventory">{data.items.map((item) => <article className="business-asset" key={item.asset_id}>
      <div className="business-asset__media">{item.imageUrl ? <img src={item.imageUrl} alt={item.asset_name || `Asset ${item.asset_id}`} /> : <ImageOff />}</div>
      <div className="business-asset__identity"><small>Asset #{item.asset_id}</small><h2>{item.asset_name || `Business Asset ${item.asset_id}`}</h2><span>{label(item.source_workflow)}</span></div>
      <div><small>Lifecycle</small><Status value={item.current_lifecycle || item.availability} /></div>
      <div><small>Destination</small><strong>{label(item.commerce_destination)}</strong></div>
      <div className="business-readiness"><span className={item.fulfillment_ready ? "is-ready" : ""}>Fulfillment · {boolLabel(item.fulfillment_ready)}</span><span className={item.chat_ready ? "is-ready" : ""}>Chat · {boolLabel(item.chat_ready)}</span><span className={item.recommendation_ready ? "is-ready" : ""}>Recommendation · {boolLabel(item.recommendation_ready)}</span></div>
      <div className="business-associations"><small>Associations</small><span>{item.product_ids.length} products · {item.experience_ids.length} experiences</span>{item.block_reasons.length > 0 && <em>{item.block_reasons.length} blocking issue{item.block_reasons.length === 1 ? "" : "s"}</em>}</div>
      <button className="business-detail-button" disabled={detailLoading} onClick={() => void openDetail(item)} type="button">View details</button>
    </article>)}</div>}
    {data.totalPages > 1 && <nav className="business-pagination" aria-label="Business Assets pagination"><button disabled={page <= 1} onClick={() => setPage((value) => value - 1)}><ChevronLeft size={16} />Previous</button><span>Page {data.page} of {data.totalPages}</span><button disabled={page >= data.totalPages} onClick={() => setPage((value) => value + 1)}>Next<ChevronRight size={16} /></button></nav>}
    {selected && <aside className="business-detail" aria-label="Business Asset details"><header><div><small>Business Asset</small><h2>Asset #{selected.item.asset_id}</h2></div><button aria-label="Close Business Asset details" onClick={() => setSelected(null)}><X /></button></header><div className="business-detail__body">
      <img src={selected.item.imageUrl} alt={selected.item.asset_name || `Asset ${selected.item.asset_id}`} />
      <section className="business-detail__section"><h3>Lifecycle</h3><div className="business-lifecycle">{selected.item.lifecycle_steps.map(([name, state]) => <div key={name}><span className={state.toLowerCase()} /><strong>{label(name)}</strong><small>{label(state)}</small></div>)}</div></section>
      <DetailSection title="Content Intelligence" data={selected.contentIntelligence} />
      <DetailSection title="Commerce Registration" data={selected.commerceRegistration} />
      <section className="business-detail__section"><h3>Destination Routing</h3><dl><div><dt>Destination</dt><dd>{label(selected.item.commerce_destination)}</dd></div><div><dt>Routing intents</dt><dd>{selected.destination.routingIntents.length}</dd></div><div><dt>History entries</dt><dd>{selected.destination.history.length}</dd></div></dl></section>
      <DetailSection title="Fulfillment" data={selected.fulfillment} />
      <DetailSection title="Chat Commerce" data={selected.chatCommerce} />
      <section className="business-detail__section"><h3>Product & Experience Associations</h3><p>{selected.item.product_ids.length ? `Products: ${selected.item.product_ids.join(", ")}` : "No products associated."}</p><p>{selected.item.experience_ids.length ? `Experiences: ${selected.item.experience_ids.join(", ")}` : "No experiences associated."}</p></section>
      {(selected.item.block_reasons.length > 0 || selected.item.warnings.length > 0) && <section className="business-detail__section business-detail__attention"><h3>Attention</h3>{[...selected.item.block_reasons, ...selected.item.warnings].map((reason) => <p key={reason}>{label(reason)}</p>)}</section>}
    </div></aside>}
  </section>;
}
