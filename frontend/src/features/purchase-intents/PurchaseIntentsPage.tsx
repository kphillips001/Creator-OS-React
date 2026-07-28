import { useEffect, useState } from "react";
import { AlertTriangle, Search } from "lucide-react";
import { developerFetch } from "../../infrastructure/api/developerFetch";

import type {
  PurchaseIntent,
  PurchaseIntentList,
  PurchaseIntentStatistics,
  PurchaseIntentStatus,
} from "./types";
import "./purchase-intents.css";

const emptyList: PurchaseIntentList = {
  items: [], total: 0, page: 1, pageSize: 20, totalPages: 1,
};
const emptyStats: PurchaseIntentStatistics = {
  total: 0, active: 0, purchased: 0, expired: 0,
  abandoned: 0, unknown: 0, superseded: 0,
};
const statuses: Array<PurchaseIntentStatus | ""> = [
  "", "CREATED", "PRESENTED", "CLICKED", "PURCHASED", "EXPIRED",
  "ABANDONED", "UNKNOWN", "SUPERSEDED",
];

function formatDate(value: string | null) {
  return value ? new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium", timeStyle: "short",
  }).format(new Date(value)) : "—";
}

function money(value: number, currency: string) {
  return new Intl.NumberFormat(undefined, {
    style: "currency", currency,
  }).format(value / 100);
}

function label(value: string) {
  return value.toLowerCase().replaceAll("_", " ").replace(
    /(^|\s)\S/g, (letter) => letter.toUpperCase(),
  );
}

function Detail({ intent }: { intent: PurchaseIntent }) {
  const timeline = [
    ["Created", intent.createdAt], ["Presented", intent.presentedAt],
    ["Clicked", intent.clickedAt], ["Purchased", intent.purchasedAt],
    ["Abandoned", intent.abandonedAt], ["Expires", intent.expiresAt],
  ] as const;
  return <div className="purchase-intents__detail-content">
    <h2>Complete Purchase Intent</h2>
    <dl>
      <dt>Status</dt><dd>{label(intent.status)}</dd>
      <dt>Buyer</dt><dd>{intent.externalFanvueUserUuid ?? `Telegram ${intent.telegramUserId}`}</dd>
      <dt>Offering</dt><dd>{intent.commercialOfferingId}</dd>
      <dt>Publication</dt><dd>{intent.commercialPublicationId}</dd>
      <dt>Expected price</dt><dd>{money(intent.expectedPriceMinor, intent.expectedCurrency)}</dd>
      <dt>Provider resource</dt><dd>{intent.providerResourceId}</dd>
      <dt>Transaction</dt><dd>{intent.providerTransactionOrderId ?? "Not associated"}</dd>
      <dt>Payment</dt><dd>{intent.providerPaymentId ?? "Not associated"}</dd>
      <dt>Event</dt><dd>{intent.providerEventId ?? "Not associated"}</dd>
      <dt>Attribution</dt><dd>{label(intent.attributionResult)}</dd>
      <dt>Reason</dt><dd>{intent.attributionReason ?? "—"}</dd>
      <dt>Conversation</dt><dd>{intent.conversationId ?? "—"}</dd>
      <dt>Correlation</dt><dd>{intent.correlationId}</dd>
    </dl>
    <h3>Timeline</h3>
    <ol className="purchase-intents__timeline">
      {timeline.map(([name, value]) =>
        value && <li key={name}><strong>{name}</strong><span>{formatDate(value)}</span></li>
      )}
    </ol>
    <h3>Metadata</h3>
    <pre>{JSON.stringify(intent.createdMetadata, null, 2)}</pre>
  </div>;
}

export function PurchaseIntentsPage() {
  const [data, setData] = useState(emptyList);
  const [statistics, setStatistics] = useState(emptyStats);
  const [selected, setSelected] = useState<PurchaseIntent | null>(null);
  const [search, setSearch] = useState("");
  const [submittedSearch, setSubmittedSearch] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ page: String(page), page_size: "20" });
    if (submittedSearch) params.set("search", submittedSearch);
    if (status) params.set("status", status);
    setLoading(true);
    Promise.all([
      developerFetch(`/api/v1/developer/purchase-intents?${params}`, {
        signal: controller.signal,
      }),
      developerFetch("/api/v1/developer/purchase-intents/statistics", {
        signal: controller.signal,
      }),
    ]).then(async ([listResponse, statsResponse]) => {
      if (!listResponse.ok || !statsResponse.ok) {
        const failed = !listResponse.ok ? listResponse : statsResponse;
        const body = await failed.json().catch(() => ({}));
        throw new Error(body.detail ?? "Purchase Intents are unavailable.");
      }
      return Promise.all([listResponse.json(), statsResponse.json()]);
    }).then(([items, stats]) => {
      setData(items);
      setStatistics(stats);
      setError("");
    }).catch((reason: Error) => {
      if (reason.name !== "AbortError") setError(reason.message);
    }).finally(() => setLoading(false));
    return () => controller.abort();
  }, [page, status, submittedSearch]);

  return <section className="purchase-intents">
    <header>
      <div><span className="purchase-intents__eyebrow">Developer Tool — Read Only</span>
        <h1>Purchase Intents</h1>
        <p>Inspect deterministic offer presentation and payment-reference lifecycle state.</p>
      </div>
    </header>
    <div className="purchase-intents__statistics" aria-label="Purchase Intent statistics">
      {Object.entries(statistics).map(([name, value]) =>
        <div key={name}><strong>{value}</strong><span>{label(name)}</span></div>
      )}
    </div>
    <form className="purchase-intents__filters" onSubmit={(event) => {
      event.preventDefault(); setPage(1); setSubmittedSearch(search.trim());
    }}>
      <label><span>Search Purchase Intents</span>
        <input value={search} onChange={(event) => setSearch(event.target.value)}
          placeholder="Buyer, offering, transaction, resource" />
      </label>
      <label><span>Status</span>
        <select value={status} onChange={(event) => {
          setStatus(event.target.value); setPage(1);
        }}>
          {statuses.map((value) =>
            <option key={value || "all"} value={value}>{value ? label(value) : "All statuses"}</option>
          )}
        </select>
      </label>
      <button type="submit"><Search size={16} />Search</button>
    </form>
    {loading && <div className="purchase-intents__state">Loading Purchase Intents…</div>}
    {error && <div className="purchase-intents__state purchase-intents__state--error" role="alert"><AlertTriangle />{error}</div>}
    {!loading && !error && data.items.length === 0 && <div className="purchase-intents__state">No Purchase Intents found.</div>}
    {!loading && !error && data.items.length > 0 && <div className="purchase-intents__workspace">
      <div className="purchase-intents__table-wrap"><table>
        <thead><tr><th>Buyer</th><th>Offering</th><th>Status</th><th>Presented</th><th>Expires</th><th>Transaction</th><th>Attribution</th></tr></thead>
        <tbody>{data.items.map((item) => <tr key={item.purchaseIntentId}
          className={selected?.purchaseIntentId === item.purchaseIntentId ? "is-selected" : undefined}
          onClick={() => setSelected(item)}>
          <td><button aria-label={`View Purchase Intent ${item.purchaseIntentId}`}>{item.externalFanvueUserUuid ?? item.telegramUserId}</button></td>
          <td>{item.commercialOfferingId}</td><td><span className="purchase-intents__status">{label(item.status)}</span></td>
          <td>{formatDate(item.presentedAt)}</td><td>{formatDate(item.expiresAt)}</td>
          <td>{item.providerTransactionOrderId ?? "—"}</td><td>{label(item.attributionResult)}</td>
        </tr>)}</tbody>
      </table></div>
      <aside aria-label="Complete Purchase Intent" className="purchase-intents__detail">
        {selected ? <Detail intent={selected} /> : <div className="purchase-intents__no-selection">No Purchase Intent selected.</div>}
      </aside>
    </div>}
    <div className="purchase-intents__pagination">
      <button disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</button>
      <span>Page {data.page} of {data.totalPages}</span>
      <button disabled={page >= data.totalPages} onClick={() => setPage((value) => value + 1)}>Next</button>
    </div>
  </section>;
}
