import { useEffect, useState, type FormEvent } from "react";
import { AlertTriangle, Search } from "lucide-react";
import { developerFetch } from "../../infrastructure/api/developerFetch";

import { PageHeader } from "../../shared/ui/PageHeader";
import type {
  CustomerSalesDecision,
  CustomerSalesDecisionList,
  CustomerSalesStatistics,
} from "./types";
import "./customer-sales-brain.css";

const emptyList: CustomerSalesDecisionList = {
  items: [], total: 0, page: 1, pageSize: 20, totalPages: 1,
};
const emptyStats: CustomerSalesStatistics = {
  total: 0, decisionDistribution: {}, buyerStageDistribution: {},
  currentActiveOffers: 0, pendingPayments: 0, unknownAttributions: 0,
};
const label = (value: string | null) => value
  ? value.replaceAll("_", " ").toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase()) : "—";
const date = (value: string | null) =>
  value ? new Date(value).toLocaleString() : "—";
const money = (minor: unknown) => new Intl.NumberFormat(undefined, {
  style: "currency", currency: "USD",
}).format((typeof minor === "number" ? minor : 0) / 100);

export function CustomerSalesBrainPage() {
  const [data, setData] = useState(emptyList);
  const [statistics, setStatistics] = useState(emptyStats);
  const [selected, setSelected] = useState<CustomerSalesDecision | null>(null);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({
      page: String(page), page_size: "20",
    });
    if (search) params.set("search", search);
    setLoading(true);
    Promise.all([
      developerFetch(`/api/v1/developer/customer-sales-brain?${params}`, {
        cache: "no-store", signal: controller.signal,
      }),
      developerFetch("/api/v1/developer/customer-sales-brain/statistics", {
        cache: "no-store", signal: controller.signal,
      }),
    ]).then(async ([listResponse, statisticsResponse]) => {
      const listBody = await listResponse.json();
      const statsBody = await statisticsResponse.json();
      if (!listResponse.ok) {
        throw new Error(listBody.detail || "Unable to load Sales Brain decisions.");
      }
      if (!statisticsResponse.ok) {
        throw new Error(statsBody.detail || "Unable to load Sales Brain statistics.");
      }
      return [listBody, statsBody] as const;
    }).then(([listBody, statsBody]) => {
      setData(listBody); setStatistics(statsBody); setError("");
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted) {
        setError(reason instanceof Error ? reason.message : "Unable to load Customer Sales Brain.");
      }
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [page, search]);

  const submit = (event: FormEvent) => {
    event.preventDefault(); setPage(1); setSearch(query.trim());
  };
  return <section className="sales-brain">
    <PageHeader title="Customer Sales Brain"
      description="Developer Tool — Read-only deterministic commercial decisions." />
    <div className="sales-brain__summary" aria-label="Sales Brain summary">
      <article><span>Customers</span><strong>{statistics.total}</strong></article>
      <article><span>Active Offers</span><strong>{statistics.currentActiveOffers}</strong></article>
      <article><span>Pending Payments</span><strong>{statistics.pendingPayments}</strong></article>
      <article><span>Unknown Attribution</span><strong>{statistics.unknownAttributions}</strong></article>
    </div>
    <div className="sales-brain__distributions">
      <Distribution title="Decision distribution" values={statistics.decisionDistribution} />
      <Distribution title="Buyer stage distribution" values={statistics.buyerStageDistribution} />
    </div>
    <form className="sales-brain__search" onSubmit={submit}>
      <Search size={16} /><input aria-label="Search Customer Sales Brain"
        value={query} onChange={(event) => setQuery(event.target.value)}
        placeholder="Search buyer UUID, handle, or display name" />
      <button type="submit">Search</button>
    </form>
    {loading && <div className="sales-brain__state">Evaluating customers…</div>}
    {error && <div className="sales-brain__state sales-brain__state--error" role="alert"><AlertTriangle />{error}</div>}
    {!loading && !error && data.items.length === 0 && <div className="sales-brain__state">No customer decisions found.</div>}
    {!loading && !error && data.items.length > 0 && <div className="sales-brain__workspace">
      <div className="sales-brain__table"><table><thead><tr>
        <th>Buyer</th><th>Stage</th><th>Decision</th><th>Reason</th>
        <th>Lifetime Spend</th><th>Purchases</th><th>Current Offer</th><th>Offer Status</th>
      </tr></thead><tbody>{data.items.map((item) => <tr
        key={`${item.fanvueAccountId}:${item.externalFanvueBuyerUuid}`}
        aria-selected={selected === item} onClick={() => setSelected(item)}>
        <td><button type="button" aria-label={`View ${item.externalFanvueBuyerUuid}`}
          onClick={() => setSelected(item)}>{item.externalFanvueBuyerUuid || `Telegram ${item.telegramUserId}`}</button></td>
        <td>{label(item.buyerStage)}</td>
        <td><span className="sales-brain__decision">{label(item.decision)}</span></td>
        <td>{label(item.reasonCode)}</td>
        <td>{money(item.commerceSignal.lifetimeSpendMinor)}</td>
        <td>{String(item.commerceSignal.purchaseCount ?? 0)}</td>
        <td>{item.activeOfferingId || "—"}</td><td>{label(item.activeOfferStatus)}</td>
      </tr>)}</tbody></table></div>
      <aside aria-label="Complete CustomerSalesDecision" className="sales-brain__detail">
        {selected ? <DecisionDetail item={selected} /> : <div className="sales-brain__empty">No decision selected.</div>}
      </aside>
    </div>}
    <nav className="sales-brain__pagination" aria-label="Customer Sales Brain pagination">
      <button disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</button>
      <span>Page {data.page} of {data.totalPages}</span>
      <button disabled={page >= data.totalPages} onClick={() => setPage((value) => value + 1)}>Next</button>
    </nav>
  </section>;
}

function Distribution({ title, values }: {
  title: string; values: Record<string, number>;
}) {
  return <section><h2>{title}</h2><div>{Object.entries(values).map(([name, count]) =>
    <span key={name}>{label(name)} <strong>{count}</strong></span>
  )}</div></section>;
}

function DecisionDetail({ item }: { item: CustomerSalesDecision }) {
  const fields: Array<[string, string | number]> = [
    ["Decision", label(item.decision)], ["Reason code", item.reasonCode],
    ["Reason", item.reasonSummary], ["Buyer stage", label(item.buyerStage)],
    ["Identity resolved", item.identityResolved ? "Yes" : "No"],
    ["Telegram user", item.telegramUserId ?? "—"],
    ["Active Purchase Intent", item.activePurchaseIntentId || "—"],
    ["Active Offering", item.activeOfferingId || "—"],
    ["Offer status", label(item.activeOfferStatus)],
    ["Conversion state", label(item.activeOfferConversionState)],
    ["Recommended Offering", item.recommendedOfferingId || "—"],
    ["Recommended Publication", item.recommendedPublicationId || "—"],
    ["Delivery URL", item.recommendedDeliveryUrl || "—"],
    ["Sell allowed", item.sellAllowed ? "Yes" : "No"],
    ["Nudge allowed", item.nudgeAllowed ? "Yes" : "No"],
    ["Congratulate allowed", item.congratulateAllowed ? "Yes" : "No"],
    ["Cooldown until", date(item.cooldownUntil)],
    ["Evaluated", date(item.evaluatedAt)],
  ];
  return <><header><small>Complete CustomerSalesDecision</small>
    <h2>{label(item.decision)}</h2><p>{item.reasonSummary}</p></header>
    <dl>{fields.map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>
    <h3>Commerce Signal</h3><pre>{JSON.stringify(item.commerceSignal, null, 2)}</pre>
    <h3>Timeline & Decision Metadata</h3><pre>{JSON.stringify(item.decisionMetadata, null, 2)}</pre>
  </>;
}
