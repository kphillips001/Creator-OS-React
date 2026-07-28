import { AlertTriangle, CheckCircle2, ExternalLink, RefreshCw, Unplug } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "../../shared/ui/PageHeader";
import "./administration.css";

type FanvueStatus = {
  provider: string;
  connected: boolean;
  connectionStatus: "CONNECTED" | "NOT_CONNECTED" | "REAUTHORIZATION_REQUIRED";
  account: { id: number; displayName: string; username: string | null; fanvueUserUuid: string | null };
  grantedScopes: string[];
  requiredScopes: string[];
  missingScopes: string[];
  accessTokenExpiresAt: string | null;
  refreshTokenAvailable: boolean;
  lastSuccessfulRefresh: string | null;
  connectedAt: string | null;
  apiVersion: string;
  workerReady: boolean;
  publicationReady: boolean;
  mediaLinkCapability: { ready: boolean; reason: string | null };
};

const futureProviders = ["Telegram", "X", "OpenAI", "Anthropic", "Grok", "Google"];
const when = (value: string | null) => value ? new Date(value).toLocaleString() : "Unavailable";

export function ProviderConnectionsPage() {
  const [status, setStatus] = useState<FanvueStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [authorizing, setAuthorizing] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const response = await fetch("/api/v1/administration/providers/fanvue", { cache: "no-store" });
      const body = await response.json() as FanvueStatus & { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Unable to load Fanvue status.");
      setStatus(body);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load Fanvue status.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const authorize = async () => {
    setAuthorizing(true); setError("");
    try {
      const response = await fetch("/api/v1/administration/providers/fanvue/authorize", { method: "POST" });
      const body = await response.json() as { authorizationUrl?: string; detail?: string };
      if (!response.ok || !body.authorizationUrl) throw new Error(body.detail || "Unable to start Fanvue authorization.");
      window.location.assign(body.authorizationUrl);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to start Fanvue authorization.");
      setAuthorizing(false);
    }
  };

  return <section className="administration-page provider-connections-page">
    <PageHeader title="Provider Connections" description="Authorize external providers and verify account-scoped capabilities." />
    {error && <div className="administration-alert administration-alert--error" role="alert"><AlertTriangle size={17} />{error}</div>}
    {loading && <div className="administration-state">Refreshing provider status…</div>}
    {!loading && status && <article className="provider-card provider-card--fanvue">
      <header><div><span className="provider-card__mark">F</span><div><p>Provider</p><h2>Fanvue</h2></div></div><span className={status.connected && !status.missingScopes.length ? "provider-status is-ready" : "provider-status needs-attention"}>{status.connected ? status.missingScopes.length ? "Reauthorization Required" : "Connected" : "Not Connected"}</span></header>
      {status.missingScopes.length > 0 && <div className="administration-alert"><AlertTriangle size={17} /><span><strong>Reauthorization Required</strong><br />Reconnect Fanvue to grant {status.missingScopes.join(", ")}. Media Link publication remains unavailable until authorization succeeds.</span></div>}
      <dl className="provider-details">
        <div><dt>Connected account</dt><dd>{status.account.displayName}{status.account.username ? ` · @${status.account.username}` : ""}</dd></div>
        <div><dt>Connection status</dt><dd>{status.connectionStatus.replaceAll("_", " ")}</dd></div>
        <div><dt>Access token expiration</dt><dd>{when(status.accessTokenExpiresAt)}</dd></div>
        <div><dt>Last successful refresh</dt><dd>{when(status.lastSuccessfulRefresh)}</dd></div>
        <div><dt>Refresh token</dt><dd>{status.refreshTokenAvailable ? "Available" : "Unavailable"}</dd></div>
        <div><dt>Current API version</dt><dd>{status.apiVersion}</dd></div>
        <div><dt>Worker readiness</dt><dd>{status.workerReady ? "Ready" : "Disabled"}</dd></div>
        <div><dt>Publication readiness</dt><dd>{status.publicationReady ? "Ready" : "Not ready"}</dd></div>
        <div><dt>Media Link capability</dt><dd className={status.mediaLinkCapability.ready ? "is-ready" : "needs-attention"}>{status.mediaLinkCapability.ready ? <><CheckCircle2 size={15} />Ready</> : status.mediaLinkCapability.reason}</dd></div>
      </dl>
      <section className="provider-scopes"><h3>Granted scopes</h3>{status.grantedScopes.length ? <div>{status.grantedScopes.map((scope) => <code className={status.missingScopes.includes(scope) ? "is-missing" : ""} key={scope}>{scope}</code>)}</div> : <p>No OAuth scopes are currently stored.</p>}</section>
      <footer><button disabled={authorizing} onClick={() => void authorize()} type="button"><ExternalLink size={16} />{authorizing ? "Opening Fanvue…" : status.connected ? "Reconnect Fanvue" : "Authorize Fanvue"}</button><button disabled={loading} onClick={() => void refresh()} type="button"><RefreshCw size={16} />Refresh Status</button></footer>
    </article>}
    <section className="future-providers"><h2>Additional providers</h2><div>{futureProviders.map((provider) => <article key={provider}><Unplug size={18} /><strong>{provider}</strong><span>Coming later</span></article>)}</div></section>
  </section>;
}
