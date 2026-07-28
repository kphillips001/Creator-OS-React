import { useEffect, useMemo, useState, type FormEvent } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, ImageOff, Search, X } from "lucide-react";

import { PageHeader } from "../../shared/ui/PageHeader";
import type { CommerceSale, CommerceSalesResponse } from "./types";
import "./commerce-sales-explorer.css";
import { developerFetch } from "../../infrastructure/api/developerFetch";

const empty: CommerceSalesResponse = {
  items: [], total: 0, page: 1, pageSize: 20, totalPages: 1,
};
const label = (value: string) => value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());

export function CommerceSalesExplorerPage() {
  const [data, setData] = useState(empty);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [offeringType, setOfferingType] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<CommerceSale | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({
      channel: "AI_CHAT", page: String(page), page_size: "20",
    });
    if (offeringType) params.set("offering_type", offeringType);
    setLoading(true); setError("");
    developerFetch(`/api/v1/commerce/sales?${params}`, {
      cache: "no-store", signal: controller.signal,
    }).then(async (response) => {
      const body = await response.json() as CommerceSalesResponse & { detail?: string | { message?: string } };
      if (!response.ok) {
        const detail = typeof body.detail === "string" ? body.detail : body.detail?.message;
        throw new Error(detail || "Unable to load Commerce Sales.");
      }
      return body;
    }).then(setData).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Unable to load Commerce Sales.");
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [offeringType, page]);

  const visible = useMemo(() => {
    const normalized = search.trim().toLowerCase();
    if (!normalized) return data.items;
    return data.items.filter((item) =>
      `${item.title} ${item.description || ""} ${item.provider}`.toLowerCase().includes(normalized)
    );
  }, [data.items, search]);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSearch(query);
  };

  return <section className="commerce-sales-explorer">
    <PageHeader title="Commerce Sales Explorer" description="Developer-only view of the fulfillable offerings AI Chat is currently allowed to sell." />
    <form className="commerce-sales-explorer__filters" onSubmit={submit}>
      <label><span className="sr-only">Search Commerce Sales</span><Search size={16} /><input aria-label="Search Commerce Sales" onChange={(event) => setQuery(event.target.value)} placeholder="Search current results" value={query} /><button type="submit">Search</button></label>
      <select aria-label="Offering type" onChange={(event) => { setOfferingType(event.target.value); setPage(1); }} value={offeringType}><option value="">All supported types</option><option value="SINGLE_IMAGE">Single Image</option><option value="PHOTOSET">Photoset</option><option value="VIDEO">Video</option></select>
    </form>
    {loading && <div className="commerce-sales-explorer__state">Loading eligible offerings…</div>}
    {error && <div className="commerce-sales-explorer__state commerce-sales-explorer__state--error" role="alert"><AlertTriangle />{error}</div>}
    {!loading && !error && visible.length === 0 && <div className="commerce-sales-explorer__state"><strong>{search ? "No eligible offerings match this search." : "No offerings are currently eligible for AI Chat."}</strong><span>Only provider-confirmed, fulfillable offerings appear here.</span></div>}
    {!loading && !error && visible.length > 0 && <div className="commerce-sales-explorer__grid" aria-label="AI Chat sellable offerings">
      {visible.map((item) => <article key={item.offeringId}>
        <button aria-label={`Open ${item.title}`} className="commerce-sales-explorer__hero" onClick={() => setSelected(item)} type="button">{item.heroUrl ? <img alt="" loading="lazy" src={item.heroUrl} /> : <ImageOff />}</button>
        <div><small>{label(item.offeringType)}</small><h2>{item.title}</h2>{item.description && <p>{item.description}</p>}<dl><div><dt>Price</dt><dd>{new Intl.NumberFormat(undefined, { style: "currency", currency: item.currency }).format(item.priceMinor / 100)}</dd></div><div><dt>Provider</dt><dd>{label(item.provider)}</dd></div><div><dt>Status</dt><dd>{label(item.status)}</dd></div><div><dt>Published</dt><dd>{new Date(item.publishedAt).toLocaleDateString()}</dd></div></dl><a href={item.deliveryUrl} rel="noreferrer" target="_blank">Open Media Link</a></div>
      </article>)}
    </div>}
    {!loading && !error && data.totalPages > 1 && <nav className="commerce-sales-explorer__pagination" aria-label="Commerce Sales pagination"><button disabled={page <= 1} onClick={() => setPage((value) => value - 1)} type="button"><ChevronLeft size={16} />Previous</button><span>Page {data.page} of {data.totalPages}</span><button disabled={page >= data.totalPages} onClick={() => setPage((value) => value + 1)} type="button">Next<ChevronRight size={16} /></button></nav>}
    {selected && <div className="commerce-sales-explorer__dialog" role="dialog" aria-modal="true" aria-label={`${selected.title} details`} onMouseDown={(event) => { if (event.target === event.currentTarget) setSelected(null); }}><article><header><div><small>{label(selected.offeringType)}</small><h2>{selected.title}</h2></div><button aria-label="Close details" onClick={() => setSelected(null)} type="button"><X /></button></header><img alt={selected.title} src={selected.heroUrl} />{selected.description && <p>{selected.description}</p>}<dl><div><dt>Price</dt><dd>{new Intl.NumberFormat(undefined, { style: "currency", currency: selected.currency }).format(selected.priceMinor / 100)}</dd></div><div><dt>Channel</dt><dd>AI Chat</dd></div><div><dt>Provider</dt><dd>{label(selected.provider)}</dd></div><div><dt>Provider resource</dt><dd>{selected.providerResourceId}</dd></div><div><dt>Status</dt><dd>Fulfillable</dd></div><div><dt>Published</dt><dd>{new Date(selected.publishedAt).toLocaleString()}</dd></div></dl><a href={selected.deliveryUrl} rel="noreferrer" target="_blank">Open Media Link</a></article></div>}
  </section>;
}
