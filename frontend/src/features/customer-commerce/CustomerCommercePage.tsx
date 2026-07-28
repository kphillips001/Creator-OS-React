import { useEffect, useState, type FormEvent } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, Search } from "lucide-react";
import { developerFetch } from "../../infrastructure/api/developerFetch";

import { PageHeader } from "../../shared/ui/PageHeader";
import type {
  CustomerCommerceListResponse,
  CustomerCommerceProfile,
  CustomerCommerceStatistics,
  CommerceSignal,
} from "./types";
import "./customer-commerce.css";

const emptyList: CustomerCommerceListResponse = {
  items: [], total: 0, page: 1, pageSize: 20, totalPages: 1,
};
const emptyStatistics: CustomerCommerceStatistics = {
  profileCount: 0, buyerCount: 0, lifetimeGrossMinor: 0,
  lifetimeNetMinor: 0, purchaseCount: 0,
  averageOrderValueMinor: 0, largestPurchaseMinor: 0,
};
const money = (minor: number) => new Intl.NumberFormat(undefined, {
  style: "currency", currency: "USD",
}).format(minor / 100);
const date = (value: string | null) =>
  value ? new Date(value).toLocaleString() : "—";
const label = (value: string | null) =>
  value ? value.replaceAll("_", " ").toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase()) : "—";

export function CustomerCommercePage() {
  const [data, setData] = useState(emptyList);
  const [statistics, setStatistics] = useState(emptyStatistics);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [signal, setSignal] = useState<CommerceSignal | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({
      page: String(page), page_size: "20",
    });
    if (search) params.set("search", search);
    setLoading(true);
    setError("");
    Promise.all([
      developerFetch(`/api/v1/developer/customer-commerce?${params}`, {
        cache: "no-store", signal: controller.signal,
      }),
      developerFetch("/api/v1/developer/customer-commerce/statistics", {
        cache: "no-store", signal: controller.signal,
      }),
    ]).then(async ([listResponse, statisticsResponse]) => {
      const listBody = await listResponse.json() as
        CustomerCommerceListResponse & { detail?: string };
      const statisticsBody = await statisticsResponse.json() as
        CustomerCommerceStatistics & { detail?: string };
      if (!listResponse.ok) {
        throw new Error(listBody.detail || "Unable to load commerce profiles.");
      }
      if (!statisticsResponse.ok) {
        throw new Error(
          statisticsBody.detail || "Unable to load commerce statistics.",
        );
      }
      return [listBody, statisticsBody] as const;
    }).then(([listBody, statisticsBody]) => {
      setData(listBody);
      setStatistics(statisticsBody);
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) {
        setError(
          reason instanceof Error
            ? reason.message : "Unable to load Customer Commerce.",
        );
      }
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [page, search]);

  const selected = data.items.find((item) => item.profileId === selectedId)
    ?? null;
  useEffect(() => {
    if (!selected) {
      setSignal(null);
      return;
    }
    const controller = new AbortController();
    developerFetch(`/api/v1/developer/commerce-signals?buyer_uuid=${selected.externalFanvueUserUuid}`, {
      cache: "no-store", signal: controller.signal,
    }).then((response) => response.ok ? response.json() : null)
      .then((body) => setSignal(body))
      .catch(() => {
        if (!controller.signal.aborted) setSignal(null);
      });
    return () => controller.abort();
  }, [selected]);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setPage(1);
    setSearch(query.trim());
  };

  return <section className="customer-commerce">
    <PageHeader
      title="Customer Commerce"
      description="Developer Tool — Read-only customer purchase aggregates and identity state."
    />
    <div className="customer-commerce__statistics" aria-label="Commerce statistics">
      <article><span>Profiles</span><strong>{statistics.profileCount}</strong></article>
      <article><span>Buyers</span><strong>{statistics.buyerCount}</strong></article>
      <article><span>Lifetime Gross</span><strong>{money(statistics.lifetimeGrossMinor)}</strong></article>
      <article><span>Purchases</span><strong>{statistics.purchaseCount}</strong></article>
      <article><span>Average Order</span><strong>{money(statistics.averageOrderValueMinor)}</strong></article>
      <article><span>Largest Purchase</span><strong>{money(statistics.largestPurchaseMinor)}</strong></article>
    </div>
    <form className="customer-commerce__search" onSubmit={submit}>
      <Search size={17} />
      <input
        aria-label="Search Customer Commerce"
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search buyer UUID, handle, or display name"
        value={query}
      />
      <button type="submit">Search</button>
    </form>
    {loading && <div className="customer-commerce__state">Loading customer commerce profiles…</div>}
    {error && <div className="customer-commerce__state customer-commerce__state--error" role="alert"><AlertTriangle />{error}</div>}
    {!loading && !error && data.items.length === 0 && <div className="customer-commerce__state"><strong>No customer commerce profiles found.</strong></div>}
    {!loading && !error && data.items.length > 0 && <div className="customer-commerce__workspace">
      <div className="customer-commerce__table-wrap">
        <table>
          <thead><tr>
            <th>Buyer</th><th>Handle</th><th>Lifetime Spend</th>
            <th>Purchases</th><th>Last Purchase</th><th>Average Order</th>
            <th>Last Source</th><th>Last Status</th><th>Stage</th>
          </tr></thead>
          <tbody>{data.items.map((item) => <tr
            aria-selected={selectedId === item.profileId}
            key={item.profileId}
            onClick={() => setSelectedId(item.profileId)}
          >
            <td><button
              aria-label={`View ${item.displayName || item.externalFanvueUserUuid}`}
              onClick={() => setSelectedId(item.profileId)}
              type="button"
            >{item.displayName || item.externalFanvueUserUuid}</button></td>
            <td>{item.handle ? `@${item.handle}` : "—"}</td>
            <td>{money(item.lifetimeGrossMinor)}</td>
            <td>{item.purchaseCount}</td>
            <td>{date(item.lastPurchaseAt)}</td>
            <td>{money(item.averageOrderValueMinor)}</td>
            <td>{label(item.lastPurchaseSource)}</td>
            <td>{label(item.lastPaymentStatus)}</td>
            <td><span className="customer-commerce__stage">{label(item.profileState)}</span></td>
          </tr>)}</tbody>
        </table>
      </div>
      <aside aria-label="Complete Commerce Profile" className="customer-commerce__detail">
        {!selected && <div className="customer-commerce__no-selection">No commerce profile selected.</div>}
        {selected && <ProfileDetail profile={selected} signal={signal} />}
      </aside>
    </div>}
    {!loading && !error && data.totalPages > 1 && <nav
      aria-label="Customer Commerce pagination"
      className="customer-commerce__pagination"
    >
      <button disabled={page <= 1} onClick={() => setPage((value) => value - 1)} type="button"><ChevronLeft size={16} />Previous</button>
      <span>Page {data.page} of {data.totalPages}</span>
      <button disabled={page >= data.totalPages} onClick={() => setPage((value) => value + 1)} type="button">Next<ChevronRight size={16} /></button>
    </nav>}
  </section>;
}

function ProfileDetail({ profile, signal }: {
  profile: CustomerCommerceProfile; signal: CommerceSignal | null;
}) {
  const fields: Array<[string, string | number]> = [
    ["Buyer UUID", profile.externalFanvueUserUuid],
    ["Creator Profile", profile.creatorProfileId],
    ["Fanvue Account", profile.fanvueAccountId],
    ["Telegram Mapping", profile.telegramIdentityMappingId ?? "Not linked"],
    ["Telegram User", profile.telegramUserId ?? "Not linked"],
    ["Display Name", profile.displayName || "—"],
    ["Handle", profile.handle ? `@${profile.handle}` : "—"],
    ["Stage", label(profile.profileState)],
    ["First Seen", date(profile.firstSeenAt)],
    ["Last Seen", date(profile.lastSeenAt)],
    ["First Purchase", date(profile.firstPurchaseAt)],
    ["Last Purchase", date(profile.lastPurchaseAt)],
    ["Lifetime Gross", money(profile.lifetimeGrossMinor)],
    ["Lifetime Net", money(profile.lifetimeNetMinor)],
    ["Purchase Count", profile.purchaseCount],
    ["Average Order", money(profile.averageOrderValueMinor)],
    ["Largest Purchase", money(profile.largestPurchaseMinor)],
    ["Last Transaction", profile.lastTransactionOrderId || "—"],
    ["Last Payment Status", label(profile.lastPaymentStatus)],
    ["Last Purchase Source", label(profile.lastPurchaseSource)],
    ["Last Synced", date(profile.lastSyncedAt)],
    ["Created", date(profile.createdAt)],
    ["Updated", date(profile.updatedAt)],
    ["Identity Resolved", signal ? (signal.identityResolved ? "Yes" : "No") : "—"],
    ["Active Offer", signal?.currentActiveOfferId || "—"],
    ["Offer Status", label(signal?.currentOfferStatus || null)],
    ["Conversion State", label(signal?.conversionState || null)],
    ["Attribution", label(signal?.attributionState || null)],
    ["Reconciliation", label(signal?.reconciliationState || null)],
  ];
  return <>
    <header><small>Complete Commerce Profile</small><h2>{profile.displayName || profile.handle || "Fanvue Buyer"}</h2></header>
    <dl>{fields.map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>
  </>;
}
