import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, Search, X } from "lucide-react";

import { PageHeader } from "../../shared/ui/PageHeader";
import type { CustomerListResponse, CustomerWorkspaceItem } from "./types";
import "./business-customers.css";

const emptyData: CustomerListResponse = { items: [], summary: { total: 0, active: 0, purchasers: 0, highValue: 0, atRisk: 0, activeSessions: 0 }, total: 0, page: 1, pageSize: 24, totalPages: 1 };
const title = (value: unknown) => String(value || "Not available").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const money = (cents: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(cents / 100);
const date = (value: string | null) => value ? new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "No activity recorded";

function Badge({ value, positive = false }: { value: unknown; positive?: boolean }) {
  return <span className={`customer-badge${positive ? " customer-badge--positive" : ""}`}>{title(value)}</span>;
}

function DetailValue({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "") return <span>Not recorded</span>;
  if (typeof value === "boolean") return <span>{value ? "Yes" : "No"}</span>;
  if (Array.isArray(value)) return <span>{value.length ? value.map((item) => typeof item === "object" ? Object.values(item as Record<string, unknown>).filter((part) => typeof part !== "object" && part !== null).slice(0, 3).join(" · ") : String(item)).join(", ") : "None"}</span>;
  if (typeof value === "object") return <span>{Object.entries(value as Record<string, unknown>).filter(([, item]) => typeof item !== "object" && item !== null && item !== "").slice(0, 5).map(([key, item]) => `${title(key)}: ${typeof item === "boolean" ? (item ? "Yes" : "No") : String(item)}`).join(" · ") || "See related customer context"}</span>;
  return <span>{String(value)}</span>;
}

function DetailSection({ heading, data }: { heading: string; data: Record<string, unknown> | Record<string, unknown>[] | undefined }) {
  const entries = Object.entries(data || {}).filter(([key]) => !["metadata", "compatibility", "compatibility_metadata"].includes(key)).slice(0, 14);
  return <section className="customer-detail__section"><h3>{heading}</h3>{entries.length ? <dl>{entries.map(([key, value]) => <div key={key}><dt>{title(key)}</dt><dd><DetailValue value={value} /></dd></div>)}</dl> : <p>No information recorded.</p>}</section>;
}

function IntelligenceEvidence({ profile }: { profile: Record<string, unknown> | undefined }) {
  if (!profile) return <DetailSection heading="Customer Intelligence Profile" data={profile} />;
  const groups: [string, unknown][] = [
    ["Authoritative facts", profile.facts],
    ["Derived metrics", { spending: profile.spending_profile, sessions: profile.session_profile, media: profile.video_conversion, bundles: profile.bundle_behavior, engagement: profile.engagement_profile }],
    ["Inferred preferences", { purchase: profile.purchase_preferences, media: profile.media_preferences }],
    ["Classifications", profile.classifications],
    ["Interpreted opportunities and risks", { opportunities: profile.opportunities, risks: profile.risks }],
    ["Historical decisions", profile.recommendation_history],
  ];
  const count = (value: unknown) => Array.isArray(value) ? value.length : value && typeof value === "object" ? Object.keys(value as Record<string, unknown>).length : value == null ? 0 : 1;
  return <section className="customer-detail__section customer-intelligence-evidence"><h3>Customer Intelligence Profile</h3><dl><div><dt>Profile state</dt><dd><DetailValue value={profile.profile_state} /></dd></div><div><dt>Identity confidence</dt><dd>{Math.round(Number(profile.identity_confidence || 0) * 100)}%</dd></div><div><dt>Section states</dt><dd><DetailValue value={profile.section_states} /></dd></div></dl>{groups.map(([heading, value]) => <article key={heading}><h4>{heading}</h4><p>{count(value)} canonical record{count(value) === 1 ? "" : "s"}</p><details><summary>Technical evidence details</summary><pre>{JSON.stringify(value ?? null, null, 2)}</pre></details></article>)}<article><h4>Provenance, conflicts, and insufficiencies</h4><dl><div><dt>Conflicts</dt><dd><DetailValue value={profile.conflicts} /></dd></div><div><dt>Insufficiencies</dt><dd><DetailValue value={profile.insufficiencies} /></dd></div><div><dt>Calculation metadata</dt><dd><DetailValue value={profile.calculation_metadata} /></dd></div></dl><details><summary>Technical provenance details</summary><pre>{JSON.stringify(profile.provenance ?? null, null, 2)}</pre></details></article></section>;
}

export function BusinessCustomersPage() {
  const [data, setData] = useState(emptyData);
  const [search, setSearch] = useState("");
  const [relationship, setRelationship] = useState("");
  const [valueTier, setValueTier] = useState("");
  const [health, setHealth] = useState("");
  const [session, setSession] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<CustomerWorkspaceItem | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [safetyReason, setSafetyReason] = useState("");
  const [safetySaving, setSafetySaving] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ page: String(page), page_size: "24" });
    if (search.trim()) params.set("search", search.trim());
    if (relationship) params.set("relationship_stage", relationship);
    if (valueTier) params.set("value_tier", valueTier);
    if (health) params.set("customer_health", health);
    if (session) params.set("active_session", session);
    setLoading(true); setError("");
    fetch(`/api/v1/customers?${params}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => { const body = await response.json() as CustomerListResponse & { detail?: string }; if (!response.ok) throw new Error(body.detail || "Unable to load Customers."); return body; })
      .then(setData)
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Unable to load Customers."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [search, relationship, valueTier, health, session, page]);

  const metrics = useMemo(() => [
    ["Total Customers", data.summary.total], ["Active", data.summary.active], ["Purchasers", data.summary.purchasers],
    ["High Value", data.summary.highValue], ["At Risk", data.summary.atRisk], ["Active Sessions", data.summary.activeSessions],
  ] as const, [data.summary]);

  const openDetails = async (customer: CustomerWorkspaceItem) => {
    setDetailLoading(true); setError("");
    try {
      const response = await fetch(`/api/v1/customers/${encodeURIComponent(customer.customerId)}`, { cache: "no-store" });
      const body = await response.json() as CustomerWorkspaceItem & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Unable to load Customer details.");
      setSelected(body);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load Customer details."); }
    finally { setDetailLoading(false); }
  };

  const changeSafety = async (safetyStatus: "NORMAL" | "UNDERAGE_BLOCKED") => {
    if (!selected || safetyReason.trim().length < 5) { setError("Enter a reason for this audited safety change."); return; }
    const action = safetyStatus === "UNDERAGE_BLOCKED" ? "block all autonomous interaction for this customer" : "restore autonomous interaction for this customer";
    if (!window.confirm(`Confirm you want to ${action}. Historical records will remain unchanged.`)) return;
    setSafetySaving(true); setError("");
    try {
      const response = await fetch(`/api/v1/customers/${encodeURIComponent(selected.customerId)}/safety`, {
        method: "PUT", headers: { "content-type": "application/json" },
        body: JSON.stringify({ safetyStatus, reason: safetyReason.trim() }),
      });
      const body = await response.json() as CustomerWorkspaceItem & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Unable to update customer safety.");
      setSelected(body); setSafetyReason("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to update customer safety."); }
    finally { setSafetySaving(false); }
  };

  return <section className="business-customers-page">
    <PageHeader title="Customers" description="Understand customer relationships, value, journeys, and Sales Agent readiness in one read-only workspace." />
    <div className="customer-metrics">{metrics.map(([name, value]) => <article key={name}><span>{name}</span><strong>{value}</strong></article>)}</div>
    <div className="customer-toolbar">
      <label className="customer-search"><Search size={16} /><span className="sr-only">Search Customers</span><input aria-label="Search Customers" placeholder="Search name, username, or Customer ID" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} /></label>
      <label><span>Relationship</span><select aria-label="Relationship stage" value={relationship} onChange={(event) => { setRelationship(event.target.value); setPage(1); }}><option value="">All stages</option><option value="new">New</option><option value="returning">Returning</option><option value="active">Active</option><option value="engaged">Engaged</option><option value="purchaser">Purchaser</option><option value="repeat_purchaser">Repeat purchaser</option><option value="vip">VIP</option><option value="dormant">Dormant</option></select></label>
      <label><span>Value</span><select aria-label="Value tier" value={valueTier} onChange={(event) => { setValueTier(event.target.value); setPage(1); }}><option value="">All values</option><option value="NEW">New</option><option value="ENGAGED">Engaged</option><option value="BUYER">Buyer</option><option value="REPEAT_BUYER">Repeat buyer</option><option value="HIGH_VALUE">High value</option><option value="VIP_POTENTIAL">VIP potential</option><option value="VIP">VIP</option><option value="AT_RISK">At risk</option><option value="DORMANT">Dormant</option><option value="UNKNOWN">Unknown</option></select></label>
      <label><span>Health</span><select aria-label="Customer health" value={health} onChange={(event) => { setHealth(event.target.value); setPage(1); }}><option value="">All health</option><option value="HEALTHY">Healthy</option><option value="OPPORTUNITY">Opportunity</option><option value="NEEDS_ATTENTION">Needs attention</option><option value="AT_RISK">At risk</option><option value="DORMANT">Dormant</option><option value="VIP">VIP</option><option value="UNKNOWN">Unknown</option></select></label>
      <label><span>Buyer session</span><select aria-label="Buyer session" value={session} onChange={(event) => { setSession(event.target.value); setPage(1); }}><option value="">All sessions</option><option value="true">Active</option><option value="false">Inactive</option></select></label>
    </div>
    {error && <div className="customer-state customer-state--error" role="alert"><AlertTriangle size={18} />{error}</div>}
    {loading && <div className="customer-state">Loading Customers…</div>}
    {!loading && !error && !data.items.length && <div className="customer-state"><strong>No Customers found.</strong><span>Customers will appear here when provider relationships are synchronized.</span></div>}
    {!loading && data.items.length > 0 && <div className="customer-inventory">{data.items.map((customer) => <article className="customer-row" key={customer.customerId}>
      <div className="customer-avatar" aria-hidden="true">{customer.displayName.slice(0, 1).toUpperCase()}</div>
      <div className="customer-row__identity"><small>{customer.customerId}</small><h2>{customer.displayName}</h2><span>{customer.isSubscriber ? "Subscriber" : customer.isFollower ? "Follower" : title(customer.relationshipStatus)}</span></div>
      <div><small>Relationship</small><Badge value={customer.relationshipStage} positive={["active", "engaged", "vip"].includes(customer.relationshipStage)} /><span>{title(customer.buyerTier || "No buyer tier")}</span></div>
      <div><small>Value</small><strong>{title(customer.valueTier)}</strong><span>{money(customer.totalSpendCents)} · {customer.purchaseCount} purchase{customer.purchaseCount === 1 ? "" : "s"}</span></div>
      <div><small>Business</small><Badge value={customer.customerHealth} positive={customer.customerHealth === "healthy"} /><span>{title(customer.lifecycleStage)}</span></div>
      <div><small>Retention</small><strong>{title(customer.retentionRisk)}</strong><span>{customer.activeBuyerSession ? "Active buyer session" : date(customer.lastActivityAt)}</span></div>
      <div className="customer-row__action"><small>Next action</small><span>{customer.nextRecommendedAction}</span></div>
      <button className="customer-detail-button" disabled={detailLoading} onClick={() => void openDetails(customer)} type="button">View details</button>
    </article>)}</div>}
    {data.totalPages > 1 && <nav className="customer-pagination" aria-label="Customers pagination"><button disabled={page <= 1} onClick={() => setPage((value) => value - 1)}><ChevronLeft size={16} />Previous</button><span>Page {data.page} of {data.totalPages}</span><button disabled={page >= data.totalPages} onClick={() => setPage((value) => value + 1)}>Next<ChevronRight size={16} /></button></nav>}
    {selected && <aside className="customer-detail" aria-label="Customer details"><header><div><small>Customer</small><h2>{selected.displayName}</h2></div><button aria-label="Close Customer details" onClick={() => setSelected(null)}><X /></button></header><div className="customer-detail__body">
      <section className={`customer-detail__section customer-safety${selected.interactionSafety?.safetyStatus === "UNDERAGE_BLOCKED" ? " customer-safety--blocked" : ""}`}><h3>Interaction Safety</h3><strong>{selected.interactionSafety?.safetyStatus === "UNDERAGE_BLOCKED" ? "UNDERAGE — CHAT BLOCKED" : "NORMAL"}</strong><p>{selected.interactionSafety?.safetyStatus === "UNDERAGE_BLOCKED" ? "No autonomous chatbot, sales, Session, link, follow-up, outreach, or reaction interaction is permitted. Historical records remain intact." : "No customer-specific interaction safety block is active."}</p><label>Required reason<input aria-label="Safety change reason" value={safetyReason} onChange={(event) => setSafetyReason(event.target.value)} /></label><button disabled={safetySaving} onClick={() => void changeSafety(selected.interactionSafety?.safetyStatus === "UNDERAGE_BLOCKED" ? "NORMAL" : "UNDERAGE_BLOCKED")} type="button">{selected.interactionSafety?.safetyStatus === "UNDERAGE_BLOCKED" ? "Restore NORMAL" : "Mark UNDERAGE — BLOCKED"}</button>{selected.interactionSafety?.history?.length ? <details><summary>Safety change history</summary><pre>{JSON.stringify(selected.interactionSafety.history, null, 2)}</pre></details> : null}</section>
      <DetailSection heading="Identity" data={selected.identity} />
      <DetailSection heading="Relationship" data={selected.relationship} />
      <DetailSection heading="Customer Value" data={selected.customerValue} />
      <DetailSection heading="Journey" data={selected.journey} />
      <DetailSection heading="Commerce and Ownership" data={selected.commerceAndOwnership} />
      <DetailSection heading="Recommendation History" data={selected.recommendationHistory} />
      <DetailSection heading="Conversation Summary" data={selected.conversationSummary} />
      <DetailSection heading="Buyer Session" data={selected.buyerSession} />
      <DetailSection heading="Sales Session History" data={selected.salesSessions} />
      <DetailSection heading="Retention and Growth" data={selected.retentionAndGrowth} />
      <DetailSection heading="Business Guidance" data={selected.businessGuidance} />
      <IntelligenceEvidence profile={selected.customerIntelligenceProfile} />
    </div></aside>}
  </section>;
}
