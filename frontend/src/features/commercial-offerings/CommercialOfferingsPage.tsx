import { useEffect, useState, type FormEvent } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, ImageOff, Plus, X } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { PageHeader } from "../../shared/ui/PageHeader";
import type { CommercialFulfillment, CommercialOffering, CommercialOfferingList, CommercialPublication } from "./types";
import "./commercial-offerings.css";

const empty: CommercialOfferingList = { items: [], total: 0, page: 1, pageSize: 20, totalPages: 1 };
const label = (value: string) => value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());

export function CommercialOfferingsPage() {
  const [params, setParams] = useSearchParams();
  const initialAssets = (params.get("asset_ids") || "").split(",").filter(Boolean).map(Number).filter(Number.isInteger);
  const [data, setData] = useState(empty);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [creating, setCreating] = useState(initialAssets.length > 0);
  const [saving, setSaving] = useState(false);
  const [assetIds, setAssetIds] = useState(initialAssets);
  const [offeringType, setOfferingType] = useState("SINGLE_IMAGE");
  const [channel, setChannel] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [hero, setHero] = useState(initialAssets[0] || 0);
  const [detail, setDetail] = useState<CommercialOffering | null>(null);
  const [publications, setPublications] = useState<CommercialPublication[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [publicationDialog, setPublicationDialog] = useState(false);
  const [publicationSaving, setPublicationSaving] = useState(false);
  const [price, setPrice] = useState("");
  const [executingId, setExecutingId] = useState("");
  const [reconcilingId, setReconcilingId] = useState("");
  const [fulfillment, setFulfillment] = useState<CommercialFulfillment | null>(null);
  const createdOfferingId = params.get("offering_id");

  useEffect(() => {
    if (!detail || !publications.some((item) => item.status === "PUBLISHING")) return;
    const timer = window.setTimeout(() => {
      fetch(`/api/v1/commercial-publications?commercial_offering_id=${encodeURIComponent(detail.offeringId)}`, { cache: "no-store" })
        .then((response) => response.json())
        .then((body: { items?: CommercialPublication[] }) => setPublications(body.items || []))
        .catch(() => undefined);
    }, 1500);
    return () => window.clearTimeout(timer);
  }, [detail, publications]);

  useEffect(() => {
    const controller = new AbortController();
    const query = new URLSearchParams({ page: String(page), page_size: "20" });
    if (search) query.set("search", search);
    setLoading(true); setError("");
    fetch(`/api/v1/commercial-offerings?${query}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const body = await response.json() as CommercialOfferingList & { detail?: string };
        if (!response.ok) throw new Error(body.detail || "Unable to load Commercial Offerings.");
        return body;
      }).then(setData)
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Unable to load Commercial Offerings."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [page, refresh, search]);

  const openCreate = () => {
    const selected = (params.get("asset_ids") || "").split(",").filter(Boolean).map(Number).filter(Number.isInteger);
    setAssetIds(selected); setHero(selected[0] || 0); setCreating(true); setError("");
  };
  const create = async (event: FormEvent) => {
    event.preventDefault(); setSaving(true); setError("");
    try {
      const response = await fetch("/api/v1/commercial-offerings", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({
          offeringType, title, description: description || null,
          heroAssetId: hero, primarySalesChannel: channel, assetIds,
        }),
      });
      const body = await response.json() as CommercialOffering & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Unable to create Commercial Offering.");
      setCreating(false); setParams({}); setTitle(""); setDescription(""); setChannel("");
      setAssetIds([]); setHero(0); setRefresh((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to create Commercial Offering.");
    } finally { setSaving(false); }
  };
  const openDetail = async (offering: CommercialOffering) => {
    setDetailLoading(true); setError("");
    try {
      const [offeringResponse, publicationsResponse, fulfillmentResponse] = await Promise.all([
        fetch(`/api/v1/commercial-offerings/${offering.offeringId}`, { cache: "no-store" }),
        fetch(`/api/v1/commercial-publications?commercial_offering_id=${encodeURIComponent(offering.offeringId)}`, { cache: "no-store" }),
        fetch(`/api/v1/commercial-fulfillments/${offering.offeringId}`, { cache: "no-store" }),
      ]);
      const offeringBody = await offeringResponse.json() as CommercialOffering & { detail?: string };
      const publicationBody = await publicationsResponse.json() as { items: CommercialPublication[]; detail?: string };
      const fulfillmentBody = await fulfillmentResponse.json() as CommercialFulfillment & { detail?: string };
      if (!offeringResponse.ok) throw new Error(offeringBody.detail || "Unable to load Commercial Offering.");
      if (!publicationsResponse.ok) throw new Error(publicationBody.detail || "Unable to load Commercial Publications.");
      if (!fulfillmentResponse.ok) throw new Error(fulfillmentBody.detail || "Unable to load Commercial Fulfillment.");
      setDetail(offeringBody); setPrice(offeringBody.priceMinor == null ? "" : (offeringBody.priceMinor / 100).toFixed(2)); setPublications(publicationBody.items || []);
      setFulfillment(fulfillmentBody);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load Commercial Offering.");
    } finally { setDetailLoading(false); }
  };
  useEffect(() => {
    if (!createdOfferingId || detail?.offeringId === createdOfferingId) return;
    const created = data.items.find((item) => item.offeringId === createdOfferingId);
    if (created) void openDetail(created);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [createdOfferingId, data.items]);
  const createPublication = async () => {
    if (!detail || publications.some((item) => item.provider === "FANVUE")) return;
    setPublicationSaving(true); setError("");
    try {
      const response = await fetch("/api/v1/commercial-publications", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ commercialOfferingId: detail.offeringId, provider: "FANVUE" }),
      });
      const body = await response.json() as CommercialPublication & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Unable to create Commercial Publication.");
      setPublications((current) => [...current, body]); setPublicationDialog(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to create Commercial Publication.");
    } finally { setPublicationSaving(false); }
  };
  const savePrice = async () => {
    if (!detail) return;
    setSaving(true); setError("");
    try {
      const response = await fetch(`/api/v1/commercial-offerings/${detail.offeringId}/pricing`, {
        method: "PATCH", headers: { "content-type": "application/json" },
        body: JSON.stringify({ priceMinor: Math.round(Number(price) * 100), currency: "USD" }),
      });
      const body = await response.json() as CommercialOffering & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Unable to save price.");
      setDetail(body);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to save price."); }
    finally { setSaving(false); }
  };
  const executePublication = async (publication: CommercialPublication) => {
    setExecutingId(publication.publicationId); setError("");
    try {
      const action = publication.status === "FAILED" ? "retry" : "execute";
      const response = await fetch(`/api/v1/commercial-publications/${publication.publicationId}/${action}`, {
        method: "POST", headers: { "content-type": "application/json" }, body: "{}",
      });
      const body = await response.json() as CommercialPublication & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Unable to start Fanvue publication.");
      setPublications((items) => items.map((item) => item.publicationId === body.publicationId ? { ...body, status: "PUBLISHING" } : item));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to start Fanvue publication."); }
    finally { setExecutingId(""); }
  };
  const reconcilePublication = async (publication: CommercialPublication) => {
    if (!detail) return;
    setReconcilingId(publication.publicationId); setError("");
    try {
      const response = await fetch(`/api/v1/commercial-publications/${publication.publicationId}/reconcile`, { method: "POST" });
      const result = await response.json() as { detail?: string };
      if (!response.ok) throw new Error(result.detail || "Unable to reconcile Fanvue publication.");
      const [publicationResponse, fulfillmentResponse] = await Promise.all([
        fetch(`/api/v1/commercial-publications?commercial_offering_id=${encodeURIComponent(detail.offeringId)}`, { cache: "no-store" }),
        fetch(`/api/v1/commercial-fulfillments/${detail.offeringId}`, { cache: "no-store" }),
      ]);
      const publicationBody = await publicationResponse.json() as { items: CommercialPublication[] };
      const fulfillmentBody = await fulfillmentResponse.json() as CommercialFulfillment;
      setPublications(publicationBody.items || []); setFulfillment(fulfillmentBody);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to reconcile Fanvue publication."); }
    finally { setReconcilingId(""); }
  };

  return <section className="commercial-offerings-page">
    <PageHeader title="Offers" description="Create and prepare content to publish or sell." />
    {params.get("created") === "1" && <div className="commercial-offerings-state" role="status">Draft Offer created. It is ready for the existing publication flow.</div>}
    <div className="commercial-offerings-toolbar"><form onSubmit={(event) => { event.preventDefault(); setPage(1); setSearch(searchInput.trim()); }}><input aria-label="Search Commercial Offerings" onChange={(event) => setSearchInput(event.target.value)} placeholder="Search offerings" value={searchInput} /><button type="submit">Search</button></form><button onClick={openCreate} type="button"><Plus size={16} />Create Offering</button></div>
    {error && <div className="commercial-offerings-state commercial-offerings-state--error" role="alert"><AlertTriangle />{error}</div>}
    {loading && <div className="commercial-offerings-state">Loading Commercial Offerings…</div>}
    {!loading && !error && data.items.length === 0 && <div className="commercial-offerings-state"><strong>No Offers yet.</strong><span>Create an Offer from a Photoshoot in the Asset Library.</span></div>}
    {!loading && data.items.length > 0 && <div className="commercial-offerings-grid" aria-label="Commercial Offerings">
      {data.items.map((item) => <article key={item.offeringId}><button aria-label={`View ${item.title}`} className="commercial-offering-card__hero" disabled={detailLoading} onClick={() => void openDetail(item)} type="button">{item.heroUrl ? <img alt="" loading="lazy" src={item.heroUrl} /> : <ImageOff />}</button><div><small>{label(item.offeringType)}</small><h2>{item.title}</h2>{item.description && <p>{item.description}</p>}<dl><div><dt>Primary channel</dt><dd>{label(item.primarySalesChannel)}</dd></div><div><dt>Assets</dt><dd>{item.assetCount}</dd></div><div><dt>Status</dt><dd>{label(item.status)}</dd></div><div><dt>Created</dt><dd>{new Date(item.createdAt).toLocaleDateString()}</dd></div></dl></div></article>)}
    </div>}
    {data.totalPages > 1 && <nav className="commercial-offerings-pagination" aria-label="Commercial Offerings pagination"><button disabled={page <= 1} onClick={() => setPage((value) => value - 1)}><ChevronLeft />Previous</button><span>Page {data.page} of {data.totalPages}</span><button disabled={page >= data.totalPages} onClick={() => setPage((value) => value + 1)}>Next<ChevronRight /></button></nav>}
    {creating && <div className="commercial-offering-dialog" role="dialog" aria-modal="true" aria-labelledby="create-offering-title"><form onSubmit={create}><header><div><small>Commercial Offering</small><h2 id="create-offering-title">Create Offering</h2></div><button aria-label="Close creation form" onClick={() => setCreating(false)} type="button"><X /></button></header>
      <p>{assetIds.length ? `${assetIds.length} Available Inventory asset${assetIds.length === 1 ? "" : "s"} selected.` : "Select assets in Available Inventory, then return here to create an offering."}</p>
      <label>Offering Type<select aria-label="Offering Type" onChange={(event) => setOfferingType(event.target.value)} value={offeringType}><option value="SINGLE_IMAGE">Single Image</option><option value="PHOTOSET">Photoset</option><option value="VIDEO">Video</option><option value="STORY">Story</option><option value="STORY_SET">Story Set</option></select></label>
      <fieldset><legend>Primary Sales Channel</legend><label><input checked={channel === "AI_CHAT"} name="channel" onChange={() => setChannel("AI_CHAT")} required type="radio" />AI Chat</label><label><input checked={channel === "TELEGRAM_WALL"} name="channel" onChange={() => setChannel("TELEGRAM_WALL")} required type="radio" />Telegram Wall</label></fieldset>
      <label>Title<input aria-label="Offering title" onChange={(event) => setTitle(event.target.value)} required value={title} /></label>
      <label>Description<textarea aria-label="Offering description" onChange={(event) => setDescription(event.target.value)} value={description} /></label>
      {assetIds.length > 1 && <label>Hero<select aria-label="Hero Asset" onChange={(event) => setHero(Number(event.target.value))} value={hero}>{assetIds.map((id) => <option key={id} value={id}>Asset #{id}</option>)}</select></label>}
      <footer><button onClick={() => setCreating(false)} type="button">Cancel</button><button disabled={saving || !assetIds.length || !channel} type="submit">{saving ? "Creating…" : "Create Offering"}</button></footer>
    </form></div>}
    {detail && <aside className="commercial-offering-detail" aria-label={`${detail.title} details`}><header><div><small>{label(detail.offeringType)}</small><h2>{detail.title}</h2></div><button aria-label="Close offering details" onClick={() => setDetail(null)} type="button"><X /></button></header><img alt="" src={detail.heroUrl} /><dl><div><dt>Primary channel</dt><dd>{label(detail.primarySalesChannel)}</dd></div><div><dt>Status</dt><dd>{label(detail.status)}</dd></div><div><dt>Assets</dt><dd>{detail.assetCount}</dd></div><div><dt>Price</dt><dd>{detail.priceMinor == null ? "Not set" : `$${(detail.priceMinor / 100).toFixed(2)}`}</dd></div><div><dt>Currency</dt><dd>{detail.currency}</dd></div></dl>
      <div className="commercial-offering-price"><label>Price (USD)<input aria-label="Price (USD)" min="3" max="500" onChange={(event) => setPrice(event.target.value)} step=".01" type="number" value={price} /></label><button disabled={saving || !price} onClick={() => void savePrice()} type="button">{saving ? "Saving…" : "Save Price"}</button></div>
      {fulfillment && <section className="commercial-fulfillment"><h3>Fulfillment</h3>{!fulfillment.fulfillable && <div className="commercial-provider-warning"><AlertTriangle size={16} />Offering unavailable: {label(fulfillment.ineligibilityReason || "Unknown")}</div>}<dl><div><dt>Fulfillable</dt><dd>{fulfillment.fulfillable ? "Yes" : "No"}</dd></div><div><dt>Channel</dt><dd>{label(fulfillment.primarySalesChannel)}</dd></div><div><dt>Provider</dt><dd>{fulfillment.provider ? label(fulfillment.provider) : "None"}</dd></div><div><dt>Provider resource</dt><dd>{label(fulfillment.providerResourceStatus)}</dd></div><div><dt>Last reconciled</dt><dd>{fulfillment.lastReconciledAt ? new Date(fulfillment.lastReconciledAt).toLocaleString() : "Never"}</dd></div><div><dt>Active delivery URL</dt><dd>{fulfillment.fulfillable && fulfillment.deliveryUrl ? <a href={fulfillment.deliveryUrl} rel="noreferrer" target="_blank">{fulfillment.deliveryUrl}</a> : "Unavailable"}</dd></div></dl></section>}
      <section className="commercial-publications"><header><div><h3>Commercial Publications</h3><p>AI Chat execution uploads offering media and creates one official Fanvue Media Link.</p></div><button disabled={publications.some((item) => item.provider === "FANVUE")} onClick={() => setPublicationDialog(true)} type="button">{publications.some((item) => item.provider === "FANVUE") ? "Fanvue Publication Exists" : "Create Publication"}</button></header>
        {!publications.length && <p>No publication records yet.</p>}
        {publications.map((publication) => {
          const metadata = publication.publicationMetadata as {
            execution?: { current_stage?: string },
            upload_summary?: { total?: number, ready?: number },
            media_link?: { uuid?: string },
          };
          return <article key={publication.publicationId}>
            {publication.providerResourceStatus !== "PRESENT" && publication.status === "LIVE" && <div className="commercial-provider-warning"><AlertTriangle size={16} />This local publication is not currently verified at the provider and cannot be fulfilled.</div>}
            <dl>
              <div><dt>Provider</dt><dd>{label(publication.provider)}</dd></div>
              <div><dt>Status</dt><dd>{label(publication.status)}</dd></div>
              <div><dt>Provider resource</dt><dd>{label(publication.providerResourceStatus)}</dd></div>
              <div><dt>Execution stage</dt><dd>{metadata.execution?.current_stage ? label(metadata.execution.current_stage) : "Not started"}</dd></div>
              <div><dt>Ready assets</dt><dd>{metadata.upload_summary ? `${metadata.upload_summary.ready || 0} / ${metadata.upload_summary.total || detail.assetCount}` : `0 / ${detail.assetCount}`}</dd></div>
              <div><dt>Published</dt><dd>{publication.publishedAt ? new Date(publication.publishedAt).toLocaleDateString() : "Not published"}</dd></div>
              <div><dt>Media Link UUID</dt><dd>{metadata.media_link?.uuid || publication.externalProductId || "Not assigned"}</dd></div>
              <div><dt>Last reconciled</dt><dd>{publication.lastReconciledAt ? new Date(publication.lastReconciledAt).toLocaleString() : "Never"}</dd></div>
              <div><dt>Reconciliation</dt><dd>{publication.reconciliationResult || "Not reconciled"}</dd></div>
              <div><dt>Retry count</dt><dd>{publication.retryCount}</dd></div>
              <div><dt>Last error</dt><dd>{publication.lastError || "None"}</dd></div>
            </dl>
            <div className="commercial-publication-actions">
              <button disabled={reconcilingId === publication.publicationId} onClick={() => void reconcilePublication(publication)} type="button">{reconcilingId === publication.publicationId ? "Reconciling…" : "Reconcile Provider"}</button>
              {detail.primarySalesChannel === "AI_CHAT" && !["LIVE", "ARCHIVED"].includes(publication.status) && <button disabled={executingId === publication.publicationId || detail.priceMinor == null} onClick={() => void executePublication(publication)} type="button">{executingId === publication.publicationId ? "Starting…" : publication.status === "FAILED" || publication.status === "PUBLISHING" ? "Retry / Resume" : "Execute Fanvue Publication"}</button>}
            </div>
            {detail.primarySalesChannel === "TELEGRAM_WALL" && <p>Fanvue Media Link execution is unavailable for Telegram Wall offerings.</p>}
          </article>;
        })}
      </section>
    </aside>}
    {publicationDialog && detail && <div className="commercial-publication-dialog" role="dialog" aria-modal="true" aria-labelledby="create-publication-title"><div><header><div><small>Record only</small><h2 id="create-publication-title">Create Publication</h2></div><button aria-label="Close publication dialog" onClick={() => setPublicationDialog(false)} type="button"><X /></button></header><p>This creates a Fanvue publication record in Ready to Publish status. It does not contact Fanvue or publish anything.</p><label>Provider<select aria-label="Publication Provider" value="FANVUE" disabled><option value="FANVUE">Fanvue</option></select></label><footer><button onClick={() => setPublicationDialog(false)} type="button">Cancel</button><button disabled={publicationSaving} onClick={() => void createPublication()} type="button">{publicationSaving ? "Creating…" : "Create Publication Record"}</button></footer></div></div>}
  </section>;
}
