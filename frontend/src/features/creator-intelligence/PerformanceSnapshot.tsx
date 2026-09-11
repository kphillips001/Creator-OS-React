import { useEffect, useState } from "react";
import { ArrowRight, RefreshCw, X } from "lucide-react";
import { Link } from "react-router-dom";

import { loadCurrentSalesStatus, loadPerformanceSnapshot, loadSnapshotDrillDown } from "./api";
import type { CurrentSalesStatus, PerformanceSnapshot as Snapshot, SnapshotDrillDown, SnapshotMetricValue, SnapshotPeriod } from "./types";

const PERIODS: Array<[SnapshotPeriod, string]> = [
  ["TODAY", "Today"], ["YESTERDAY", "Yesterday"], ["LAST_7_DAYS", "7 Days"],
  ["LAST_30_DAYS", "30 Days"], ["THIS_MONTH", "This Month"], ["ALL_TIME", "All Time"],
];

type Metric = { label: string; key: string; drillKey?: string; value: SnapshotMetricValue; money?: boolean; percent?: boolean; optional?: boolean; description?: string };

const money = (minor: number) => new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(minor / 100);
const format = (metric: Metric) => metric.value.status !== "AVAILABLE" || metric.value.value == null
  ? metric.percent ? "—" : "Unavailable"
  : metric.money ? money(metric.value.value) : metric.percent ? `${metric.value.value.toFixed(1)}%` : new Intl.NumberFormat().format(metric.value.value);

function rangeLabel(snapshot: Snapshot) {
  if (!snapshot.period.start) return `Through ${new Date(snapshot.period.end).toLocaleString()}`;
  const start = new Date(snapshot.period.start).toLocaleDateString();
  const end = new Date(snapshot.period.end).toLocaleDateString();
  return start === end ? start : `${start} – ${end}`;
}

function MetricGroup({ title, metrics, open }: { title: string; metrics: Metric[]; open: (metric: Metric) => void }) {
  const visible = metrics.filter((metric) => !metric.optional || (metric.value.status === "AVAILABLE" && (metric.value.value ?? 0) !== 0));
  return <section className={`snapshot-group snapshot-group--${title.toLowerCase()}`} aria-labelledby={`snapshot-${title.toLowerCase()}`}>
    <h3 id={`snapshot-${title.toLowerCase()}`}>{title}</h3>
    <div className="snapshot-metric-grid">{visible.map((metric) =>
      <button className="snapshot-metric" disabled={!metric.drillKey} key={metric.key} onClick={() => open(metric)} title={metric.description} type="button">
        <span>{metric.label}</span><strong>{format(metric)}</strong>
        {metric.value.status !== "AVAILABLE" && <small>{metric.value.reason ?? "No authoritative data is available for this period."}</small>}
        {metric.drillKey && <ArrowRight aria-hidden="true" size={14} />}
      </button>,
    )}</div>
  </section>;
}

export function PerformanceSnapshot() {
  const [period, setPeriod] = useState<SnapshotPeriod>("TODAY");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [selected, setSelected] = useState<Metric | null>(null);
  const [details, setDetails] = useState<SnapshotDrillDown | null>(null);
  const [detailsError, setDetailsError] = useState("");
  const [salesStatus, setSalesStatus] = useState<CurrentSalesStatus | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError("");
    void loadPerformanceSnapshot(period, controller.signal)
      .then(setSnapshot)
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Unable to load the performance snapshot."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [period, refreshKey]);

  useEffect(() => { const controller = new AbortController(); void loadCurrentSalesStatus(controller.signal).then(setSalesStatus).catch(() => setSalesStatus(null)); return () => controller.abort(); }, [refreshKey]);

  const open = (metric: Metric) => {
    setSelected(metric); setDetails(null); setDetailsError("");
    if (!metric.drillKey) return;
    void loadSnapshotDrillDown(period, metric.drillKey)
      .then(setDetails)
      .catch((reason: unknown) => setDetailsError(reason instanceof Error ? reason.message : "Unable to load metric details."));
  };

  const groups = snapshot ? [
    ["Money", [
      { label: "Total Revenue", key: "total_revenue", drillKey: "TOTAL_REVENUE", value: snapshot.commerce.totalVerifiedRevenueMinor, money: true },
      { label: "Content Revenue", key: "content_revenue", drillKey: "CONTENT_REVENUE", value: snapshot.commerce.contentMediaRevenueMinor, money: true },
      { label: "Tips", key: "tips", drillKey: "TIPS", value: snapshot.commerce.tipsRevenueMinor, money: true },
      { label: "Average Purchase", key: "average_purchase_value_minor", value: snapshot.commerce.averagePurchaseValueMinor, money: true },
      { label: "Subscriptions & Renewals", key: "subscription_renewal_revenue_minor", value: snapshot.commerce.subscriptionRenewalRevenueMinor, money: true, optional: true },
      { label: "Unclassified Revenue", key: "unclassified_revenue_minor", value: snapshot.commerce.unclassifiedRevenueMinor, money: true, optional: true },
    ]],
    ["People", [
      { label: "People Chatted", key: "active_people", drillKey: "ACTIVE_PEOPLE", value: snapshot.peopleActivity.activePeople, description: "Unique people who chatted with Ava during this period." },
      { label: "New", key: "new_people", drillKey: "NEW_PEOPLE", value: snapshot.peopleActivity.newPeople },
      { label: "Returning", key: "returning_people", drillKey: "RETURNING_PEOPLE", value: snapshot.peopleActivity.returningPeople },
      { label: "Unique Buyers", key: "unique_buyers", drillKey: "UNIQUE_BUYERS", value: snapshot.commerce.uniqueBuyers },
    ]],
    ["Sales", [
      { label: "Offers Presented", key: "offers_presented", drillKey: "OFFERS_PRESENTED", value: snapshot.commerce.offersPresented, description: "Offers Ava presented during this period." },
      { label: "Offers Purchased", key: "offers_purchased", drillKey: "OFFERS_PURCHASED", value: snapshot.commerce.offersPurchased, description: "Offers presented during this period that resulted in a verified purchase." },
      { label: "Offer Conversion", key: "offer_conversion", drillKey: "OFFER_CONVERSION", value: snapshot.commerce.offerConversion, percent: true, description: "Percentage of offers presented during this period that resulted in a verified purchase." },
      { label: "Purchases", key: "purchases", drillKey: "PURCHASES", value: snapshot.commerce.qualifyingPurchases, description: "Verified content purchases paid during this period." },
      { label: "New Buyers", key: "new_buyers", drillKey: "NEW_BUYERS", value: snapshot.commerce.newBuyers },
      { label: "Repeat Buyers", key: "repeat_buyers", drillKey: "REPEAT_BUYERS", value: snapshot.commerce.repeatBuyers },
    ]],
    ["Ava", [
      { label: "Customer Messages", key: "customer_messages", value: snapshot.peopleActivity.customerMessages },
      { label: "Ava Messages", key: "ava_messages", value: snapshot.peopleActivity.avaMessages },
    ]],
  ] as Array<[string, Metric[]]> : [];

  return <section className="performance-snapshot" aria-labelledby="performance-snapshot-heading">
    <header><div><span>Business performance</span><h2 id="performance-snapshot-heading">Performance Snapshot</h2>{snapshot && <p>{rangeLabel(snapshot)} · {snapshot.period.timezone}</p>}</div>
      <button aria-label="Refresh performance snapshot" className="snapshot-refresh" onClick={() => setRefreshKey((value) => value + 1)} type="button"><RefreshCw size={15} />Refresh</button>
    </header>
    <div className="snapshot-periods" role="group" aria-label="Performance period">{PERIODS.map(([key, label]) => <button aria-pressed={period === key} className={period === key ? "is-active" : ""} key={key} onClick={() => { if (key !== period) { setSnapshot(null); setLoading(true); setPeriod(key); } }} type="button">{label}</button>)}</div>
    {loading && !snapshot && <div className="snapshot-state" role="status">Loading performance…</div>}
    {error && <div className="snapshot-state snapshot-state--error" role="alert"><span>{error}</span><button onClick={() => setRefreshKey((value) => value + 1)} type="button">Retry</button></div>}
    {snapshot && <div className={loading ? "snapshot-groups is-refreshing" : "snapshot-groups"}>{groups.map(([name, metrics]) => <MetricGroup key={name} metrics={metrics} open={open} title={name} />)}</div>}
    {salesStatus && <section className="snapshot-current-sales" aria-label="Current sales state"><h3>Current Sales State</h3><div><Link to="/business/relationships?filter=active-sessions"><span>Active Sales Sessions</span><strong>{salesStatus.activeSalesSessions}</strong></Link><Link to="/business/relationships?filter=active-intents"><span>Active PurchaseIntents</span><strong>{salesStatus.activePurchaseIntents}</strong></Link><Link to="/business/operations?tab=failures"><span>Commercial Failures</span><strong>{salesStatus.commercialFailures}</strong></Link></div></section>}
    <nav className="snapshot-customer-links" aria-label="Customer directories"><Link to="/business/customers">Customers</Link><Link to="/business/customers?filter=buyers">Buyers</Link><Link to="/business/customers?filter=subscribers">Active Subscribers</Link><Link to="/business/sales?tab=offers">Offer Activity</Link></nav>
    {selected && <DrillDownDrawer close={() => setSelected(null)} details={details} error={detailsError} metric={selected} />}
  </section>;
}

function itemTitle(item: Record<string, unknown>, index: number) {
  return String(item.displayName ?? item.username ?? item.commercial_offering_id ?? item.transaction_order_id ?? item.record_id ?? `Record ${index + 1}`);
}
function DrillDownDrawer({ metric, details, error, close }: { metric: Metric; details: SnapshotDrillDown | null; error: string; close: () => void }) {
  return <div className="snapshot-drawer-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) close(); }}><aside className="snapshot-drawer" role="dialog" aria-modal="true" aria-labelledby="snapshot-detail-title">
    <header><div><span>Performance detail</span><h2 id="snapshot-detail-title">{metric.label}</h2></div><button aria-label="Close metric details" onClick={close} type="button"><X /></button></header>
    {error && <p role="alert">{error}</p>}
    {!error && !details && <p role="status">Loading details…</p>}
    {details && <><div className="snapshot-detail-summary"><span>{details.count} records</span>{details.amountMinor != null && <strong>{money(details.amountMinor)}</strong>}</div>
      {!details.items.length ? <p>No matching records for this period.</p> : <ol>{details.items.map((item, index) => <li key={String(item.record_id ?? item.personKey ?? item.customerCommerceProfileId ?? index)}><strong>{itemTitle(item, index)}</strong><dl>{Object.entries(item).filter(([, value]) => value != null && typeof value !== "object").slice(0, 12).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{typeof value === "boolean" ? (value ? "Yes" : "No") : String(value)}</dd></div>)}</dl></li>)}</ol>}
    </>}
  </aside></div>;
}
