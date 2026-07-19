import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, ImageOff, Search, X } from "lucide-react";

import { PageHeader } from "../../shared/ui/PageHeader";
import type { ProductListResponse, ProductWorkspaceItem } from "./types";
import "./business-products.css";

const emptySummary = { total: 0, drafts: 0, needsReview: 0, readyToPublish: 0, active: 0, available: 0, waitingForMediaLink: 0, needsAttention: 0, recommendationEligible: 0 };
const emptyData: ProductListResponse = { items: [], summary: emptySummary, total: 0, page: 1, pageSize: 24, totalPages: 1 };
const title = (value: unknown) => String(value || "Not available").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const money = (cents: number | null, currency = "USD") => cents === null ? "Not priced" : new Intl.NumberFormat("en-US", { style: "currency", currency }).format(cents / 100);

function Badge({ value, ready = false }: { value: string | null; ready?: boolean }) {
  return <span className={`product-badge${ready ? " product-badge--ready" : ""}`}>{title(value)}</span>;
}

function ReadModel({ title: heading, data }: { title: string; data: Record<string, unknown> | null }) {
  const entries = Object.entries(data || {}).filter(([, value]) => value !== null && value !== "" && typeof value !== "object").slice(0, 10);
  return <section className="product-detail__section"><h3>{heading}</h3>{entries.length ? <dl>{entries.map(([key, value]) => <div key={key}><dt>{title(key)}</dt><dd>{typeof value === "boolean" ? (value ? "Yes" : "No") : String(value)}</dd></div>)}</dl> : <p>No additional information recorded.</p>}</section>;
}

export function BusinessProductsPage() {
  const [data, setData] = useState(emptyData);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [approval, setApproval] = useState("");
  const [availability, setAvailability] = useState("");
  const [productType, setProductType] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<ProductWorkspaceItem | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ page: String(page), page_size: "24" });
    if (search.trim()) params.set("search", search.trim());
    if (status) params.set("product_status", status);
    if (approval) params.set("approval_status", approval);
    if (availability) params.set("availability", availability);
    if (productType) params.set("product_type", productType);
    setLoading(true); setError("");
    fetch(`/api/v1/products?${params}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => { const body = await response.json() as ProductListResponse & { detail?: string }; if (!response.ok) throw new Error(body.detail || "Unable to load Products."); return body; })
      .then(setData)
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Unable to load Products."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [search, status, approval, availability, productType, page]);

  const metrics = useMemo(() => [
    ["Total Products", data.summary.total], ["Active", data.summary.active], ["Available", data.summary.available],
    ["Recommendation Ready", data.summary.recommendationEligible], ["Needs Review", data.summary.needsReview],
    ["Ready To Publish", data.summary.readyToPublish], ["Waiting For Link", data.summary.waitingForMediaLink], ["Needs Attention", data.summary.needsAttention],
  ] as const, [data.summary]);

  const openDetails = async (product: ProductWorkspaceItem) => {
    setDetailLoading(true); setError("");
    try {
      const response = await fetch(`/api/v1/products/${product.productId}`, { cache: "no-store" });
      const body = await response.json() as ProductWorkspaceItem & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Unable to load Product details.");
      setSelected(body);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load Product details."); }
    finally { setDetailLoading(false); }
  };

  return <section className="business-products-page">
    <PageHeader title="Products" description="Monitor the offers available to the Sales Agent from draft through customer availability." />
    <div className="product-metrics">{metrics.map(([name, value]) => <article key={name}><span>{name}</span><strong>{value}</strong></article>)}</div>
    <div className="product-toolbar">
      <label className="product-search"><Search size={16} /><span className="sr-only">Search Products</span><input aria-label="Search Products" placeholder="Search name or Product ID" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} /></label>
      <label><span>Status</span><select aria-label="Product status" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}><option value="">All statuses</option><option value="DRAFT">Draft</option><option value="ACTIVE">Active</option><option value="DISABLED">Disabled</option><option value="ARCHIVED">Archived</option></select></label>
      <label><span>Approval</span><select aria-label="Approval status" value={approval} onChange={(event) => { setApproval(event.target.value); setPage(1); }}><option value="">All approvals</option><option value="NEEDS_REVIEW">Needs review</option><option value="APPROVED">Approved</option><option value="REJECTED">Rejected</option><option value="READY_TO_PUBLISH">Ready to publish</option></select></label>
      <label><span>Availability</span><select aria-label="Availability" value={availability} onChange={(event) => { setAvailability(event.target.value); setPage(1); }}><option value="">All availability</option><option value="AVAILABLE">Available</option><option value="DRAFT">Draft</option><option value="PUBLISHING">Publishing</option><option value="WAITING_FOR_MEDIA_LINK">Waiting for media link</option><option value="NEEDS_ATTENTION">Needs attention</option><option value="UNAVAILABLE">Unavailable</option><option value="ARCHIVED">Archived</option></select></label>
      <label><span>Type</span><select aria-label="Product type" value={productType} onChange={(event) => { setProductType(event.target.value); setPage(1); }}><option value="">All types</option><option value="SINGLE_IMAGE">Single image</option><option value="SINGLE_VIDEO">Single video</option><option value="PHOTO_SET">Photo set</option><option value="VIDEO_SET">Video set</option><option value="SESSION">Session</option><option value="STORY">Story</option><option value="BUNDLE">Bundle</option><option value="CUSTOM">Custom</option></select></label>
    </div>
    {error && <div className="product-state product-state--error" role="alert"><AlertTriangle size={18} />{error}</div>}
    {loading && <div className="product-state">Loading Products…</div>}
    {!loading && !error && !data.items.length && <div className="product-state"><strong>No Products found.</strong><span>Products will appear here when they enter the catalog.</span></div>}
    {!loading && data.items.length > 0 && <div className="product-inventory">{data.items.map((product) => <article className="product-row" key={product.productId}>
      <div className="product-row__media">{product.imageUrl ? <img src={product.imageUrl} alt={product.displayName} /> : <ImageOff />}</div>
      <div className="product-row__identity"><small>{title(product.productType)} · {product.productOrigin}</small><h2>{product.displayName}</h2><span>{money(product.priceCents, product.currency)}</span></div>
      <div><small>Product</small><Badge value={product.productStatus} ready={product.productStatus === "ACTIVE"} /></div>
      <div><small>Approval</small><Badge value={product.approvalStatus} ready={["APPROVED", "READY_TO_PUBLISH"].includes(product.approvalStatus)} /></div>
      <div><small>Lifecycle</small><strong>{title(product.lifecycleStage)}</strong><span>{title(product.publishingStatus)}</span></div>
      <div className="product-row__readiness"><span className={product.availabilityStatus === "AVAILABLE" ? "is-ready" : ""}>Availability · {title(product.availabilityStatus)}</span><span className={product.fulfillmentStatus === "READY" ? "is-ready" : ""}>Fulfillment · {title(product.fulfillmentStatus)}</span><span className={product.recommendationEligibility.eligible ? "is-ready" : ""}>Recommendation · {product.recommendationEligibility.eligible ? "Eligible" : "Not eligible"}</span></div>
      <div><small>Composition</small><strong>{product.assetCount} asset{product.assetCount === 1 ? "" : "s"}</strong><span>{title(product.deliveryType)}</span></div>
      <button className="product-detail-button" disabled={detailLoading} onClick={() => void openDetails(product)} type="button">View details</button>
    </article>)}</div>}
    {data.totalPages > 1 && <nav className="product-pagination" aria-label="Products pagination"><button disabled={page <= 1} onClick={() => setPage((value) => value - 1)}><ChevronLeft size={16} />Previous</button><span>Page {data.page} of {data.totalPages}</span><button disabled={page >= data.totalPages} onClick={() => setPage((value) => value + 1)}>Next<ChevronRight size={16} /></button></nav>}
    {selected && <aside className="product-detail" aria-label="Product details"><header><div><small>Product</small><h2>{selected.displayName}</h2></div><button aria-label="Close Product details" onClick={() => setSelected(null)}><X /></button></header><div className="product-detail__body">
      {selected.imageUrl && <img className="product-detail__cover" src={selected.imageUrl} alt={selected.displayName} />}
      <section className="product-detail__section"><h3>Identity</h3><dl><div><dt>Product ID</dt><dd>{selected.productId}</dd></div><div><dt>Internal name</dt><dd>{selected.internalName}</dd></div><div><dt>Type</dt><dd>{title(selected.productType)}</dd></div><div><dt>Origin</dt><dd>{selected.productOrigin}</dd></div><div><dt>Delivery</dt><dd>{title(selected.deliveryType)}</dd></div></dl><p>{selected.description || "No description recorded."}</p><p>Tags: {selected.tags.length ? selected.tags.join(", ") : "None"}</p><p>Themes: {selected.themes.length ? selected.themes.join(", ") : "None"}</p></section>
      <section className="product-detail__section"><h3>Pricing</h3><dl><div><dt>Current price</dt><dd>{money(selected.priceCents, selected.currency)}</dd></div><div><dt>Base price</dt><dd>{money(selected.basePriceCents, selected.currency)}</dd></div><div><dt>Price band</dt><dd>{money(selected.minPriceCents, selected.currency)} – {money(selected.maxPriceCents, selected.currency)}</dd></div></dl></section>
      <ReadModel title="AI Pricing Recommendation" data={selected.aiPricingRecommendation} />
      <section className="product-detail__section"><h3>Approval & Lifecycle</h3><dl><div><dt>Product status</dt><dd>{title(selected.productStatus)}</dd></div><div><dt>Approval</dt><dd>{title(selected.approvalStatus)}</dd></div><div><dt>Review</dt><dd>{selected.reviewStatus}</dd></div><div><dt>Lifecycle</dt><dd>{title(selected.lifecycleStage)}</dd></div></dl></section>
      <ReadModel title="Availability" data={selected.availability} />
      <section className="product-detail__section"><h3>Composition</h3><div className="product-composition">{selected.composition.length ? selected.composition.map((asset) => <article key={asset.assetId}>{asset.imageUrl ? <img src={asset.imageUrl} alt={asset.fileName || `Asset ${asset.assetId}`} /> : <ImageOff />}<span>Asset #{asset.assetId}</span><small>{asset.fileName || title(asset.mediaType)}</small>{asset.assetId === selected.coverAssetId && <em>Cover</em>}{asset.assetId === selected.previewAssetId && <em>Preview</em>}</article>) : <p>No assets associated.</p>}</div></section>
      <section className="product-detail__section"><h3>Publishing State</h3><dl><div><dt>Status</dt><dd>{title(selected.publishingStatus)}</dd></div><div><dt>Fulfillment</dt><dd>{title(selected.fulfillmentStatus)}</dd></div><div><dt>Strategy</dt><dd>{title(selected.fulfillmentStrategy)}</dd></div></dl><p>{selected.publishingDetail}</p></section>
      <section className="product-detail__section"><h3>Recommendation Eligibility</h3><Badge value={selected.recommendationEligibility.eligible ? "Eligible" : "Not eligible"} ready={selected.recommendationEligibility.eligible} /><p>{selected.recommendationEligibility.reason ? title(selected.recommendationEligibility.reason) : "The Product passes the catalog recommendation gate."}</p></section>
      <ReadModel title="Performance" data={selected.performance} />
      <ReadModel title="Business Health" data={selected.business} />
      <section className={`product-detail__section${selected.warnings.length ? " product-detail__attention" : ""}`}><h3>Warnings</h3>{selected.warnings.length ? selected.warnings.map((warning) => <p key={warning}>{warning}</p>) : <p>No warnings.</p>}</section>
    </div></aside>}
  </section>;
}
