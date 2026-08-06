import { Check, Copy, ExternalLink, RefreshCw, ShoppingBag, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type { SessionSellingReadiness } from "./types";
import { readinessBadge } from "./photoshootSalePreparationStatus";

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
      onStarted?.(result); onClose();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to start preparation."); }
    finally { setSaving(false); }
  };
  return <div className="sale-preparation-dialog" role="dialog" aria-modal="true" aria-labelledby="prepare-sale-title">
    <div><header><div><small>Session Selling</small><h2 id="prepare-sale-title">{retry ? "Retry Failed Preparation" : "Prepare for Sale"}</h2></div><button aria-label="Close Prepare for Sale" onClick={onClose} type="button"><X /></button></header>
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
      <footer><button onClick={onClose} type="button">Cancel</button><button disabled={invalid || saving} onClick={() => void submit()} type="button">{saving ? "Starting…" : "Prepare Photoshoot"}</button></footer>
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

export function SessionSellingPanel({ deliverableId, initialDialog = null, onReadinessChange }: {
  deliverableId: string; initialDialog?: "prepare" | "retry" | null;
  onReadinessChange?: (value: SessionSellingReadiness) => void;
}) {
  const [readiness, setReadiness] = useState<SessionSellingReadiness | null>(null);
  const [error, setError] = useState("");
  const [dialog, setDialog] = useState<"prepare" | "retry" | null>(initialDialog);
  const [published, setPublished] = useState(false);
  const updateReadiness = useCallback((value: SessionSellingReadiness) => {
    setReadiness(value);
    onReadinessChange?.(value);
  }, [onReadinessChange]);
  const load = useCallback(() => request<SessionSellingReadiness>(`/api/v1/assets/photoshoots/${encodeURIComponent(deliverableId)}/sale-preparation`).then((value) => {
    if (!value.status || !Array.isArray(value.steps)) throw new Error("Session Selling readiness is unavailable.");
    updateReadiness(value);
  }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to load readiness.")), [deliverableId, updateReadiness]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (readiness?.status !== "PREPARING") return;
    const timer = window.setInterval(() => void load(), 2500);
    return () => window.clearInterval(timer);
  }, [readiness?.status, load]);
  const completedSteps = readiness?.steps.filter((step) => step.ready).length || 0;
  const progress = readiness?.steps.length ? Math.round((completedSteps / readiness.steps.length) * 100) : 0;
  return <section className="session-selling-panel"><header><div><small>Session Selling</small><h2>{readiness?.statusLabel || "Loading…"}</h2></div>{readiness && <span className={`session-selling-badge session-selling-badge--${readiness.status.toLowerCase()}`}>{readinessBadge(readiness)}</span>}</header>
    {error && <p role="alert">{error}</p>}
    {readiness && <>{readiness.status === "PREPARING" && <div className="session-selling-progress" role="status" aria-live="polite">
      <div><strong>Preparing Photoshoot...</strong><span>{progress}%</span></div>
      <progress aria-label="Photoshoot preparation progress" max="100" value={progress}>{progress}%</progress>
      <ul>{readiness.steps.map((step) => <li className={step.ready ? "is-complete" : step.error || step.publicationStatus === "FAILED" ? "is-failed" : "is-pending"} key={step.assetId}>
        <span aria-hidden="true">{step.ready ? "✓" : step.error || step.publicationStatus === "FAILED" ? "!" : "⏳"}</span>{progressLabel(step)}
      </li>)}</ul>
    </div>}
    {readiness.status === "NEEDS_ATTENTION" && <div className="session-selling-failures" role="alert">
      {readiness.steps.filter((step) => step.error || step.publicationStatus === "FAILED").map((step) => <p key={step.assetId}>
        <strong>Shot {step.shotOrder} · {step.role.replaceAll("_", " ")}</strong><span>{step.error || "Publication failed."}</span>
      </p>)}
    </div>}
    <p>Paid steps: {readiness.readyPaidStepCount} of {readiness.paidStepCount} ready</p><div className="session-selling-actions">
      {readiness.status === "NOT_PREPARED" && <button onClick={() => setDialog("prepare")} type="button"><ShoppingBag size={16} />Prepare for Sale</button>}
      {readiness.status === "NEEDS_ATTENTION" && <button onClick={() => setDialog("retry")} type="button"><RefreshCw size={16} />Retry Failed Preparation</button>}
      {readiness.status !== "NOT_PREPARED" && <button onClick={() => setPublished((value) => !value)} type="button">View Published Assets</button>}
    </div>{published && <div className="published-assets">{readiness.steps.map((step) => <article key={step.assetId}><div><strong>Shot {step.shotOrder} · {step.role.replaceAll("_", " ")}</strong><span>{step.access === "FREE" ? "Direct Telegram delivery" : `${step.publicationStatus || "Not published"} · ${step.ready ? "Link ready" : "Link unavailable"}`}</span>{step.publishedAt && <span>Published {new Date(step.publishedAt).toLocaleString()}</span>}</div>{step.access === "PAID" && <><span>{step.priceMinor ? `${step.currency} ${(step.priceMinor / 100).toFixed(2)}` : "Price required"}</span>{step.deliveryUrl && <div className="published-assets__link"><code>{step.deliveryUrl}</code><button aria-label={`Copy Shot ${step.shotOrder} link`} onClick={() => void navigator.clipboard.writeText(step.deliveryUrl!)} type="button"><Copy size={14} /></button><a aria-label={`Open Shot ${step.shotOrder} link`} href={step.deliveryUrl} rel="noreferrer" target="_blank"><ExternalLink size={14} /></a></div>}</>}{step.error && <em>{step.error}</em>}</article>)}</div>}</>}
    {dialog && <PrepareForSaleDialog deliverableId={deliverableId} retry={dialog === "retry"} onClose={() => setDialog(null)} onStarted={(value) => { updateReadiness(value); setPublished(false); }} />}
  </section>;
}
