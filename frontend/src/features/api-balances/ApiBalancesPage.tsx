import { AlertTriangle, CircleDollarSign, ExternalLink, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "../../shared/ui/PageHeader";
import "./api-balances.css";

export type BalanceStatus = "AVAILABLE" | "STALE" | "UNAVAILABLE" | "CREDENTIAL_REQUIRED" | "NOT_SUPPORTED";
export type ProviderBalance = {
  provider: string; displayName: string; status: BalanceStatus; balance: string | null;
  currency: string | null; unit: string | null; authoritative: boolean;
  checkedAt: string | null; lastSuccessfulAt: string | null; errorCategory: string | null;
};
type Payload = { providers: ProviderBalance[]; checkedAt: string; cacheTtlSeconds: number };

const statusCopy: Record<BalanceStatus, string> = {
  AVAILABLE: "Available", STALE: "Stale", UNAVAILABLE: "Unavailable",
  CREDENTIAL_REQUIRED: "Credential required", NOT_SUPPORTED: "Not available",
};
export function formatBalance(item: ProviderBalance) {
  if (!item.authoritative || item.balance === null) return "Balance unavailable";
  const amount = Number(item.balance);
  if (item.unit === "currency" && item.currency === "USD")
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount);
  return `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(amount)} ${item.unit ?? ""}`.trim();
}
const when = (value: string | null) => value ? new Date(value).toLocaleString() : "No successful check";
const OPENAI_BILLING_URL = "https://platform.openai.com/settings/organization/billing/overview";
const providerUses: Record<string, string[]> = {
  WAVESPEED: ["Image and video generation", "Creative media processing"],
  TWITTERAPI_IO: ["X profile and post intelligence", "Competitor and audience analysis"],
  XAI: ["Grok creative analysis", "Caption and content direction"],
  OPENAI: ["Ava language generation", "Structured analysis and supported vision workflows"],
};

export function ApiBalancesPage() {
  const [data, setData] = useState<Payload | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [usesProvider, setUsesProvider] = useState<ProviderBalance | null>(null);
  const load = useCallback(async (force = false) => {
    force ? setRefreshing(true) : setLoading(true); setError("");
    try {
      const response = await fetch(`/api/v1/business/api-balances${force ? "?refresh=true" : ""}`, {
        cache: "no-store", headers: { "X-Creator-OS-Developer": "true" },
      });
      const body = await response.json() as Payload & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Unable to load API balances.");
      setData(body);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load API balances.");
    } finally { setLoading(false); setRefreshing(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  return <section className="api-balances-page">
    <div className="api-balances-page__heading">
      <PageHeader title="API Balances" description="Authoritative provider balances, credits, and availability in one place." />
      <button disabled={loading || refreshing} onClick={() => void load(true)} type="button">
        <RefreshCw className={refreshing ? "is-spinning" : ""} size={16} />{refreshing ? "Refreshing…" : "Refresh"}
      </button>
    </div>
    {error && <div className="api-balances-alert" role="alert"><AlertTriangle size={18} />{error}</div>}
    {loading && <div className="api-balances-state">Checking provider balances…</div>}
    {!loading && data && <>
      <div className="api-balances-grid">
        {data.providers.map((item) => {
          const isOpenAi = item.provider === "OPENAI";
          return <article className="api-balance-card" key={item.provider}>
          <header><span className="api-balance-card__icon"><CircleDollarSign size={19} /></span><div><p>Provider</p><h2>{item.displayName}</h2></div>
            {!isOpenAi && <span className={`api-balance-status api-balance-status--${item.status.toLowerCase()}`}>{statusCopy[item.status]}</span>}
          </header>
          <div className={`api-balance-card__amount${isOpenAi ? " api-balance-card__amount--external" : ""}`}>{isOpenAi ? "Click below to view balance" : formatBalance(item)}</div>
          {!isOpenAi && <dl>
            <div><dt>Authority</dt><dd>{item.authoritative ? "Provider reported" : "No authoritative balance"}</dd></div>
            <div><dt>Last checked</dt><dd>{when(item.checkedAt)}</dd></div>
            {item.status === "STALE" && <div><dt>Last successful</dt><dd>{when(item.lastSuccessfulAt)}</dd></div>}
          </dl>}
          {!isOpenAi && item.status === "CREDENTIAL_REQUIRED" && <p className="api-balance-card__note">A provider-specific balance credential is required.</p>}
          <div className="api-balance-card__actions">
            {isOpenAi && <a href={OPENAI_BILLING_URL} rel="noopener noreferrer" target="_blank"><ExternalLink size={15} />View Balance</a>}
            <button onClick={() => setUsesProvider(item)} type="button">Uses</button>
          </div>
        </article>})}
      </div>
      <p className="api-balances-footnote">Balances are cached for {Math.round(data.cacheTtlSeconds / 60)} minutes. Refresh performs a new read-only provider check.</p>
    </>}
    {usesProvider && <div className="api-balance-modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setUsesProvider(null); }}>
      <section aria-labelledby="api-balance-uses-title" aria-modal="true" className="api-balance-modal" role="dialog">
        <header><div><p>Provider usage</p><h2 id="api-balance-uses-title">{usesProvider.displayName} Uses</h2></div><button aria-label="Close uses" onClick={() => setUsesProvider(null)} type="button"><X size={18} /></button></header>
        <ul>{(providerUses[usesProvider.provider] ?? ["Connected Creator-OS provider workflows"]).map((use) => <li key={use}>{use}</li>)}</ul>
      </section>
    </div>}
  </section>;
}
