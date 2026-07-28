import { useEffect, useMemo, useState, type FormEvent } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, ImageOff, Search, X } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { PageHeader } from "../../shared/ui/PageHeader";
import type { AvailableInventoryItem, AvailableInventoryResponse } from "./types";
import "./available-inventory.css";

const emptyData: AvailableInventoryResponse = {
  items: [], total: 0, ready: 0, pending: 0, page: 1, pageSize: 20, totalPages: 1,
};
const label = (value: string) => value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
const dateLabel = (value: string | null) => value ? new Date(value).toLocaleDateString() : "Not recorded";

export function AvailableInventoryPage() {
  const navigate = useNavigate();
  const [data, setData] = useState(emptyData);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [readiness, setReadiness] = useState("");
  const [source, setSource] = useState("");
  const [mediaType, setMediaType] = useState("");
  const [sort, setSort] = useState("newest");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [preview, setPreview] = useState<AvailableInventoryItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ page: String(page), page_size: "20", sort });
    if (search) params.set("search", search);
    if (readiness) params.set("readiness", readiness);
    if (source) params.set("source", source);
    if (mediaType) params.set("media_type", mediaType);
    setLoading(true);
    setError("");
    fetch(`/api/v1/available-inventory?${params}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const body = await response.json() as AvailableInventoryResponse & { detail?: string };
        if (!response.ok) throw new Error(body.detail || "Unable to load Available Inventory.");
        return body;
      })
      .then((body) => setData({ ...body, items: body.items.filter((item) => item.contentDestination === "AVAILABLE_INVENTORY") }))
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Unable to load Available Inventory.");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [mediaType, page, readiness, retry, search, sort, source]);

  const selectedCount = selected.size;
  const hasFilters = Boolean(search || readiness || source || mediaType);
  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    setPage(1);
    setSearch(query.trim());
  };
  const toggle = (assetId: number) => setSelected((current) => {
    const next = new Set(current);
    if (next.has(assetId)) next.delete(assetId); else next.add(assetId);
    return next;
  });
  const summary = useMemo(() => [
    ["Total Available", data.total],
    ["Ready", data.ready],
    ["Analysis Pending", data.pending],
    ["Selected", selectedCount],
  ] as const, [data.pending, data.ready, data.total, selectedCount]);

  return <section className="available-inventory-page">
    <PageHeader title="Available Inventory" description="Canonical assets that are analyzed and not yet committed to a permanent content destination." />
    <div className="available-inventory-summary" aria-label="Available Inventory summary">
      {summary.map(([name, value]) => <article key={name}><span>{name}</span><strong>{value}</strong></article>)}
    </div>
    <form className="available-inventory-filters" onSubmit={submitSearch}>
      <label className="available-inventory-search"><span className="sr-only">Search Available Inventory</span><Search size={16} /><input aria-label="Search Available Inventory" onChange={(event) => setQuery(event.target.value)} placeholder="Search names, descriptions, or sources" value={query} /><button type="submit">Search</button></label>
      <label><span>Readiness</span><select aria-label="Readiness filter" value={readiness} onChange={(event) => { setReadiness(event.target.value); setPage(1); }}><option value="">All readiness</option><option value="READY">Ready</option><option value="PENDING">Pending</option><option value="ANALYZING">Analyzing</option><option value="PARTIAL">Partial</option><option value="FAILED">Failed</option></select></label>
      <label><span>Source</span><select aria-label="Source filter" value={source} onChange={(event) => { setSource(event.target.value); setPage(1); }}><option value="">All sources</option><option value="photoshoot">Photoshoot Studio</option><option value="standalone">Standalone</option></select></label>
      <label><span>Media</span><select aria-label="Media type filter" value={mediaType} onChange={(event) => { setMediaType(event.target.value); setPage(1); }}><option value="">All media</option><option value="image">Images</option><option value="video">Videos</option><option value="story">Stories</option></select></label>
      <label><span>Sort</span><select aria-label="Sort Available Inventory" value={sort} onChange={(event) => { setSort(event.target.value); setPage(1); }}><option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="name">Name</option><option value="readiness">Readiness</option></select></label>
    </form>

    {selectedCount > 0 && <aside className="available-inventory-actions" aria-label="Future inventory actions">
      <strong>{selectedCount} selected</strong>
      <button className="available-inventory-actions__create" onClick={() => navigate(`/commerce/offerings?asset_ids=${Array.from(selected).join(",")}`)} type="button">Create Commercial Offering</button>
      {["Create Teaser", "Create Single PPV", "Create Bundle", "Send to Telegram Wall"].map((action) => <button disabled key={action} title="Coming soon" type="button">{action}</button>)}
      <button className="available-inventory-actions__clear" onClick={() => setSelected(new Set())} type="button">Clear selection</button>
      <span>Destination actions are coming soon.</span>
    </aside>}

    {loading && <div className="available-inventory-grid" aria-label="Loading Available Inventory">{Array.from({ length: 8 }, (_, index) => <div className="available-inventory-skeleton" key={index} />)}</div>}
    {error && <div className="available-inventory-state available-inventory-state--error" role="alert"><AlertTriangle /><div><strong>Available Inventory could not be loaded.</strong><span>{error}</span></div><button onClick={() => setRetry((value) => value + 1)} type="button">Retry</button></div>}
    {!loading && !error && data.items.length === 0 && <div className="available-inventory-state"><strong>{hasFilters ? "No inventory matches your search." : "No available inventory yet."}</strong><span>{hasFilters ? "Try adjusting your search or filters." : "Approved but unselected Photoshoot images will appear here."}</span></div>}
    {!loading && !error && data.items.length > 0 && <div className="available-inventory-grid" aria-label="Available Inventory assets">
      {data.items.map((item) => <article className={selected.has(item.assetId) ? "available-inventory-card available-inventory-card--selected" : "available-inventory-card"} key={item.assetId}>
        <button className="available-inventory-card__preview" aria-label={`Preview ${item.displayName}`} onClick={() => setPreview(item)} type="button">
          {item.thumbnailUrl ? <img alt="" decoding="async" loading="lazy" src={item.thumbnailUrl} /> : <ImageOff />}
        </button>
        <div className="available-inventory-card__body"><div><strong>{item.displayName}</strong><span>{item.sourceName}</span></div><dl><div><dt>Readiness</dt><dd>{label(item.readiness)}</dd></div><div><dt>Media</dt><dd>{label(item.mediaType)}</dd></div><div><dt>Status</dt><dd>{label(item.registrationState)}</dd></div><div><dt>Destination</dt><dd>Available Inventory</dd></div></dl></div>
        <label className="available-inventory-card__select"><input aria-label={`Select ${item.displayName}`} checked={selected.has(item.assetId)} onChange={() => toggle(item.assetId)} type="checkbox" /><span>Select asset</span></label>
      </article>)}
    </div>}

    {!loading && !error && data.totalPages > 1 && <nav className="available-inventory-pagination" aria-label="Available Inventory pagination"><button disabled={page <= 1} onClick={() => setPage((value) => value - 1)} type="button"><ChevronLeft size={16} />Previous</button><span>Page {data.page} of {data.totalPages}</span><button disabled={page >= data.totalPages} onClick={() => setPage((value) => value + 1)} type="button">Next<ChevronRight size={16} /></button></nav>}

    {preview && <div className="available-inventory-preview" role="dialog" aria-modal="true" aria-label={`${preview.displayName} preview`} onMouseDown={(event) => { if (event.target === event.currentTarget) setPreview(null); }}><div><header><div><small>Available Inventory</small><h2>{preview.displayName}</h2></div><button aria-label="Close preview" onClick={() => setPreview(null)} type="button"><X /></button></header><img alt={preview.displayName} src={preview.previewUrl} /><dl><div><dt>Destination</dt><dd>Available Inventory</dd></div><div><dt>Source</dt><dd>{preview.sourceName}</dd></div><div><dt>Readiness</dt><dd>{label(preview.readiness)}</dd></div><div><dt>Registration state</dt><dd>{label(preview.registrationState)}</dd></div><div><dt>Media type</dt><dd>{label(preview.mediaType)}</dd></div><div><dt>Created</dt><dd>{dateLabel(preview.createdAt)}</dd></div><div><dt>Asset ID</dt><dd>{preview.assetId}</dd></div></dl>{preview.shortDescription && <p>{preview.shortDescription}</p>}</div></div>}
  </section>;
}
