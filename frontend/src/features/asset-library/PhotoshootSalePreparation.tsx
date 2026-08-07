import { Check, Copy, ExternalLink, RefreshCw, ShoppingBag, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { BundleSellingReadiness, SessionSellingReadiness } from "./types";
import { readinessBadge } from "./photoshootSalePreparationStatus";
import { BundlePromotionalTeaser } from "./BundleTeaserEditor";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, { cache: "no-store", ...options });
  const body = await response.json().catch(() => null) as T | { detail?: string } | null;
  if (!response.ok || !body) throw new Error((body as { detail?: string } | null)?.detail || "Unable to prepare Photoshoot.");
  return body as T;
}

export function PrepareForSaleDialog({ deliverableId, retry = false, onClose, onStarted }: {
  deliverableId: string; retry?: boolean; onClose: () => void;
  onStarted?: (value: SessionSellingReadiness) => void;
}) {
  const [readiness, setReadiness] = useState<SessionSellingReadiness | null>(null);
  const [prices, setPrices] = useState<Record<number, string>>({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    request<SessionSellingReadiness>(`/api/v1/assets/photoshoots/${encodeURIComponent(deliverableId)}/sale-preparation`)
      .then((value) => {
        setReadiness({ ...value, steps: [...value.steps].sort((left, right) => left.position - right.position) });
        setPrices(Object.fromEntries(value.steps.filter((step) => step.access === "PAID").map((step) => [step.assetId, step.priceMinor != null ? (step.priceMinor / 100).toFixed(2) : ""])));
      }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to load Session Selling strategy."));
  }, [deliverableId]);
  const minorUnits = (assetId: number) => {
    const value = prices[assetId]?.trim() || "";
    if (!/^\d+(?:\.\d{1,2})?$/.test(value)) return null;
    const minor = Math.round(Number(value) * 100);
    return Number.isSafeInteger(minor) && minor >= 300 && minor <= 50000 ? minor : null;
  };
  const invalid = !readiness || readiness.steps.some((step) => Boolean(step.priceConflict) || (step.access === "PAID" && minorUnits(step.assetId) == null));
  const submit = async () => {
    if (!readiness || saving || invalid) {
      setError("Every paid step requires a USD price between $3.00 and $500.00.");
      return;
    }
    setSaving(true); setError("");
    try {
      const result = await request<SessionSellingReadiness>(`/api/v1/assets/photoshoots/${encodeURIComponent(deliverableId)}/sale-preparation${retry ? "/retry" : ""}`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({
          strategyVersion: readiness.strategyVersion,
          steps: readiness.steps.map((step) => ({
            assetId: step.assetId, shotOrder: step.shotOrder,
            salesPosition: step.position, role: step.role, access: step.access,
            currency: "USD",
            ...(step.access === "PAID" ? { priceMinor: minorUnits(step.assetId) } : {}),
          })),
        }),
      });
      // Close before propagating readiness so a parent rerender cannot retain the modal.
      onClose(); onStarted?.(result);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to start preparation."); }
    finally { setSaving(false); }
  };
  return <div className="sale-preparation-dialog" role="dialog" aria-modal="true" aria-labelledby="prepare-sale-title">
    <div><header><div><small>Session Selling</small><h2 id="prepare-sale-title">{retry ? "Retry Failed Preparation" : "Prepare Session"}</h2></div><button aria-label="Close Prepare Session" onClick={onClose} type="button"><X /></button></header>
      <p>Review and confirm every strategy step before any Fanvue upload or Media Link creation begins.</p>
      {error && <p className="sale-preparation-error" role="alert">{error}</p>}
      {!readiness && !error && <p>Loading Session Sales Strategy…</p>}
      {readiness && <div className="sale-preparation-prices">{readiness.steps.map((step) => <div className="sale-preparation-step" key={step.assetId}>
        <img alt={`Shot ${step.shotOrder}`} src={step.imageUrl || `/api/v1/assets/${step.assetId}/thumbnail`} />
        <span><strong>Shot {step.shotOrder}</strong><small>{step.role.replaceAll("_", " ")}</small><small>{step.access === "FREE" ? "Free" : "Paid"}</small></span>
        {step.access === "FREE"
          ? <em><Check size={14} />Direct Telegram delivery</em>
          : <span className="sale-preparation-step__price"><label htmlFor={`shot-price-${step.assetId}`}>USD</label><input aria-label={`Shot ${step.shotOrder} price`} disabled={step.priceLocked} id={`shot-price-${step.assetId}`} inputMode="decimal" min="3" max="500" required step=".01" type="number" value={prices[step.assetId] || ""} onChange={(event) => setPrices((current) => ({ ...current, [step.assetId]: event.target.value }))} />{step.priceLocked && <small>Live price locked</small>}</span>}
        {step.priceLocked && <p>Fanvue does not currently support editing the live Media Link price. Keep this price or cancel.</p>}
        {step.priceConflict && <p className="sale-preparation-error">{step.priceConflict}</p>}
      </div>)}</div>}
      <footer><button onClick={onClose} type="button">Cancel</button><button disabled={invalid || saving} onClick={() => void submit()} type="button">{saving ? "Starting…" : "Prepare Session"}</button></footer>
    </div>
  </div>;
}

const progressLabel = (step: SessionSellingReadiness["steps"][number]) => {
  const role = step.role.replaceAll("_", " ");
  if (step.access === "FREE") return "Direct Telegram teaser ready";
  if (step.ready) return `Published ${role}`;
  if (step.error || step.publicationStatus === "FAILED") return `Failed ${role}`;
  if (step.publicationStatus === "PUBLISHING") return `Uploading ${role}`;
  if (step.offeringId) return `Creating publication for ${role}`;
  return `Waiting to prepare ${role}`;
};

const operatorStepError = (step: SessionSellingReadiness["steps"][number]) => {
  const detail = String(step.error || "");
  if (/timed?\s*out|timeout|HTTPSConnectionPool/i.test(detail)) {
    return `Fanvue timed out while preparing ${step.role.replaceAll("_", " ")}.`;
  }
  return detail || "Publication failed.";
};

export function SessionSellingPanel({ deliverableId, initialDialog = null, onReadinessChange }: {
  deliverableId: string; initialDialog?: "prepare" | "retry" | null;
  onReadinessChange?: (value: SessionSellingReadiness) => void;
}) {
  const [readiness, setReadiness] = useState<SessionSellingReadiness | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [strategyError, setStrategyError] = useState("");
  const [generating, setGenerating] = useState(false);
  const [dialog, setDialog] = useState<"prepare" | "retry" | null>(initialDialog);
  const [published, setPublished] = useState(false);
  const readinessRef = useRef<SessionSellingReadiness | null>(null);
  const updateReadiness = useCallback((value: SessionSellingReadiness) => {
    readinessRef.current = value;
    setReadiness(value);
    onReadinessChange?.(value);
  }, [onReadinessChange]);
  const load = useCallback(async () => {
    const isInitialLoad = readinessRef.current === null;
    if (isInitialLoad) setLoading(true);
    setError("");
    try {
      const value = await request<SessionSellingReadiness>(`/api/v1/assets/photoshoots/${encodeURIComponent(deliverableId)}/sale-preparation`);
      if (!value.status || !Array.isArray(value.steps)) throw new Error("Session Selling readiness is unavailable.");
      updateReadiness(value);
    } catch (reason) {
      if (isInitialLoad) setReadiness(null);
      setError(reason instanceof Error ? reason.message : "Unable to load Session Selling.");
    } finally { if (isInitialLoad) setLoading(false); }
  }, [deliverableId, updateReadiness]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (readiness?.status !== "PREPARING") return;
    const timer = window.setInterval(() => void load(), 2500);
    return () => window.clearInterval(timer);
  }, [readiness?.status, load]);
  const completedSteps = readiness?.steps.filter((step) => step.ready).length || 0;
  const progress = readiness?.steps.length ? Math.round((completedSteps / readiness.steps.length) * 100) : 0;
  const generateStrategy = async () => {
    if (generating) return;
    setGenerating(true); setStrategyError("");
    try {
      await request<SessionSellingReadiness>(`/api/v1/assets/photoshoots/${encodeURIComponent(deliverableId)}/session-sales-strategy`, { method: "POST" });
      await load();
      setDialog("prepare");
    } catch (reason) {
      setStrategyError(reason instanceof Error ? reason.message : "Unable to generate Session Sales Strategy.");
    } finally { setGenerating(false); }
  };
  const heading = loading && !readiness ? "Loading…" : strategyError ? "Session Strategy Needs Attention" : error && !readiness ? "Session Selling Unavailable" : readiness?.statusLabel || "Session Selling";
  return <section className="session-selling-panel"><header><div><small>Session Selling</small><h2>{heading}</h2></div>{readiness && <span className={`session-selling-badge session-selling-badge--${readiness.status.toLowerCase()}`}>{readinessBadge(readiness)}</span>}</header>
    {error && <p role="alert">{error}</p>}
    {strategyError && <p className="sale-preparation-error" role="alert">{strategyError}</p>}
    {!loading && readiness?.status === "STRATEGY_REQUIRED" && <div className="session-selling-strategy-required">
      <p>No Session Sales Strategy has been created yet.</p>
      <button disabled={generating} onClick={() => void generateStrategy()} type="button"><ShoppingBag size={16} />{generating ? "Generating Session Strategy…" : strategyError ? "Retry Session Strategy" : "Generate Session Strategy"}</button>
    </div>}
    {!loading && readiness && readiness.status !== "STRATEGY_REQUIRED" && <>{readiness.status === "PREPARING" && <div className="session-selling-progress" role="status" aria-live="polite">
      <div><strong>Preparing Photoshoot...</strong><span>{progress}%</span></div>
      <progress aria-label="Photoshoot preparation progress" max="100" value={progress}>{progress}%</progress>
      <ul>{readiness.steps.map((step) => <li className={step.ready ? "is-complete" : step.error || step.publicationStatus === "FAILED" ? "is-failed" : "is-pending"} key={step.assetId}>
        <span aria-hidden="true">{step.ready ? "✓" : step.error || step.publicationStatus === "FAILED" ? "!" : "⏳"}</span>{progressLabel(step)}
      </li>)}</ul>
    </div>}
    {readiness.status === "NEEDS_ATTENTION" && <div className="session-selling-failures" role="alert">
      {readiness.steps.filter((step) => step.error || step.publicationStatus === "FAILED").map((step) => <p key={step.assetId}>
        <strong>Shot {step.shotOrder} · {step.role.replaceAll("_", " ")}</strong><span>{operatorStepError(step)}</span>
      </p>)}
    </div>}
    <p>Paid steps: {readiness.readyPaidStepCount} of {readiness.paidStepCount} ready</p><div className="session-selling-actions">
      {readiness.status === "NOT_PREPARED" && <button onClick={() => setDialog("prepare")} type="button"><ShoppingBag size={16} />Prepare Session</button>}
      {readiness.status === "NEEDS_ATTENTION" && <button onClick={() => setDialog("retry")} type="button"><RefreshCw size={16} />Retry Failed Preparation</button>}
      {readiness.status !== "NOT_PREPARED" && <button onClick={() => setPublished((value) => !value)} type="button">View Published Assets</button>}
    </div>{published && <div className="published-assets">{readiness.steps.map((step) => <article key={step.assetId}><div><strong>Shot {step.shotOrder} · {step.role.replaceAll("_", " ")}</strong><span>{step.access === "FREE" ? "Direct Telegram delivery" : `${step.publicationStatus || "Not published"} · ${step.ready ? "Link ready" : "Link unavailable"}`}</span>{step.publishedAt && <span>Published {new Date(step.publishedAt).toLocaleString()}</span>}</div>{step.access === "PAID" && <><span>{step.priceMinor ? `${step.currency} ${(step.priceMinor / 100).toFixed(2)}` : "Price required"}</span>{step.deliveryUrl && <div className="published-assets__link"><code>{step.deliveryUrl}</code><button aria-label={`Copy Shot ${step.shotOrder} link`} onClick={() => void navigator.clipboard.writeText(step.deliveryUrl!)} type="button"><Copy size={14} /></button><a aria-label={`Open Shot ${step.shotOrder} link`} href={step.deliveryUrl} rel="noreferrer" target="_blank"><ExternalLink size={14} /></a></div>}</>}{step.error && <em>{operatorStepError(step)}</em>}</article>)}</div>}</>}
    {dialog && <PrepareForSaleDialog deliverableId={deliverableId} retry={dialog === "retry"} onClose={() => setDialog(null)} onStarted={(value) => { updateReadiness(value); setPublished(false); }} />}
  </section>;
}

const bundlePrice = (minor: number | null | undefined) => minor == null ? "" : (minor / 100).toFixed(2);

export function BundleSellingPanel({ deliverableId, salesChannel = "CHAT" }: {
  deliverableId: string; salesChannel?: "CHAT" | "CONTENT_WALL";
}) {
  const [readiness, setReadiness] = useState<BundleSellingReadiness | null>(null);
  const [price, setPrice] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const load = useCallback(() => request<BundleSellingReadiness>(`/api/v1/assets/photoshoots/${encodeURIComponent(deliverableId)}/sale-preparation`).then((value) => {
    if (value.sellingMode !== "BUNDLE") throw new Error("Bundle readiness is unavailable.");
    setReadiness(value); setPrice((current) => current || bundlePrice(value.priceMinor)); setError("");
  }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to load Bundle readiness.")), [deliverableId]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (readiness?.status !== "PREPARING") return;
    const timer = window.setInterval(() => void load(), 2500);
    return () => window.clearInterval(timer);
  }, [readiness?.status, load]);
  const priceMinor = (() => {
    if (!/^\d+(?:\.\d{1,2})?$/.test(price.trim())) return null;
    const value = Math.round(Number(price) * 100);
    return Number.isSafeInteger(value) && value >= 300 && value <= 50000 ? value : null;
  })();
  const submit = async (retry = false) => {
    if (priceMinor == null || saving) { setError("Bundle price must be between $3.00 and $500.00."); return; }
    setSaving(true); setError("");
    try {
      const value = await request<BundleSellingReadiness>(`/api/v1/assets/photoshoots/${encodeURIComponent(deliverableId)}/sale-preparation${retry ? "/retry" : ""}`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ priceMinor }),
      });
      setReadiness(value);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to prepare Bundle."); }
    finally { setSaving(false); }
  };
  return <section className="session-selling-panel bundle-selling-panel"><header><div><small>Bundle Selling · Paid Bundle</small><h2>{readiness?.statusLabel || "Loading..."}</h2></div>{readiness && <span className={`session-selling-badge session-selling-badge--${readiness.status.toLowerCase()}`}>{readiness.status === "READY" ? "Ready" : readinessBadge(readiness)}</span>}</header>
    {error && <p className="sale-preparation-error" role="alert">{error}</p>}
    {readiness && <>
      <p><strong>{readiness.imageCount} images</strong><br />All approved Photoshoot images will be included.</p>
      {salesChannel === "CHAT" ?
        <p role="status"><strong>Autonomous Sales: {readiness.autonomousSales?.statusLabel || "Needs Setup"}</strong>{readiness.autonomousSales?.reason && <><br /><span>{readiness.autonomousSales.reason}</span></>}</p> :
        <div className="bundle-content-wall-status" role="status">
          <h3>Ava&apos;s Content Wall</h3>
          <p>This Bundle is designated for Ava&apos;s Content Wall.</p>
          <p><strong>Chat Sales</strong><br />Disabled — designated for Ava&apos;s Content Wall</p>
          <p><strong>Content Wall Publishing</strong><br />Not configured yet</p>
          <small>Publishing support will be configured next.</small>
        </div>}
      <label className="bundle-selling-price" htmlFor="bundle-price"><span>Bundle Price</span><span><b>$</b><input id="bundle-price" aria-label="Bundle Price" disabled={readiness.status === "READY" || saving} inputMode="decimal" min="3" max="500" step=".01" type="number" value={price} onChange={(event) => setPrice(event.target.value)} /></span></label>
      {readiness.status === "PREPARING" && <div className="session-selling-progress" role="status"><strong>Preparing Bundle...</strong><progress aria-label="Bundle preparation progress" /></div>}
      {readiness.error && <p className="sale-preparation-error" role="alert">{readiness.error}</p>}
      <div className="session-selling-actions">
        {readiness.status === "NOT_CONFIGURED" && <button disabled={priceMinor == null || saving} onClick={() => void submit()} type="button"><ShoppingBag size={16} />{saving ? "Starting..." : "Prepare Bundle"}</button>}
        {readiness.status === "NEEDS_ATTENTION" && <button disabled={priceMinor == null || saving} onClick={() => void submit(true)} type="button"><RefreshCw size={16} />Retry Bundle Preparation</button>}
        {readiness.status === "READY" && readiness.deliveryUrl && <a href={readiness.deliveryUrl} rel="noreferrer" target="_blank"><ExternalLink size={14} />Open Fanvue Media Link</a>}
      </div>
      {readiness.status === "READY" && <p>Fanvue Media Link ready · {readiness.currency} {bundlePrice(readiness.priceMinor)}</p>}
      {readiness.promotionalTeaser && <BundlePromotionalTeaser deliverableId={deliverableId} initial={readiness.promotionalTeaser} onChanged={() => void load()} />}
    </>}
  </section>;
}
