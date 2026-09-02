import { Check, Copy, ExternalLink, RefreshCw, ShoppingBag, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { BundleSellingReadiness, ContentVaultCaptionOption, SessionSellingReadiness } from "./types";
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

export function SessionSellingPanel({ deliverableId, initialDialog = null, onReadinessChange, deferStrategyGeneration = false }: {
  deliverableId: string; initialDialog?: "prepare" | "retry" | null;
  onReadinessChange?: (value: SessionSellingReadiness) => void;
  deferStrategyGeneration?: boolean;
}) {
  const [readiness, setReadiness] = useState<SessionSellingReadiness | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [strategyActionError, setStrategyActionError] = useState("");
  const [dialog, setDialog] = useState<"prepare" | "retry" | null>(initialDialog);
  const [published, setPublished] = useState(false);
  const readinessRef = useRef<SessionSellingReadiness | null>(null);
  const ensuringStrategy = useRef(false);
  const pollingReadiness = useRef(false);
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
  const ensureStrategy = useCallback(async () => {
    if (ensuringStrategy.current) return;
    ensuringStrategy.current = true; setStrategyActionError("");
    try {
      const value = await request<SessionSellingReadiness>(`/api/v1/assets/photoshoots/${encodeURIComponent(deliverableId)}/session-sales-strategy`, { method: "POST" });
      updateReadiness(value);
    } catch (reason) {
      setStrategyActionError(reason instanceof Error ? reason.message : "Unable to start Session strategy preparation.");
    } finally { ensuringStrategy.current = false; }
  }, [deliverableId, updateReadiness]);
  useEffect(() => {
    if (deferStrategyGeneration || readiness?.status !== "STRATEGY_REQUIRED" || readiness.strategyOperation) return;
    void ensureStrategy();
  }, [deferStrategyGeneration, ensureStrategy, readiness?.status, readiness?.strategyOperation]);
  const strategyOperationStatus = readiness?.strategyOperation?.status;
  useEffect(() => {
    const strategyActive = Boolean(strategyOperationStatus && ["QUEUED", "RUNNING", "WAITING_EXTERNAL", "CANCEL_REQUESTED"].includes(strategyOperationStatus));
    if (readiness?.status !== "PREPARING" && !strategyActive) return;
    const poll = async () => {
      if (pollingReadiness.current) return;
      pollingReadiness.current = true;
      try { await load(); } finally { pollingReadiness.current = false; }
    };
    const timer = window.setInterval(() => void poll(), strategyActive ? 1500 : 2500);
    return () => { window.clearInterval(timer); pollingReadiness.current = false; };
  }, [readiness?.status, strategyOperationStatus, load]);
  useEffect(() => {
    const refreshOnFocus = () => {
      if (readiness?.status === "NEEDS_ATTENTION") void load();
    };
    window.addEventListener("focus", refreshOnFocus);
    return () => window.removeEventListener("focus", refreshOnFocus);
  }, [readiness?.status, load]);
  const completedSteps = readiness?.steps.filter((step) => step.ready).length || 0;
  const progress = readiness?.steps.length ? Math.round((completedSteps / readiness.steps.length) * 100) : 0;
  const retryStrategy = async () => {
    const operationId = readiness?.strategyOperation?.operationId;
    if (!operationId) { await ensureStrategy(); return; }
    setStrategyActionError("");
    try {
      await request(`/api/v1/background-operations/${encodeURIComponent(operationId)}/retry`, { method: "POST" });
      await load();
    } catch (reason) {
      setStrategyActionError(reason instanceof Error ? reason.message : "Unable to retry Session strategy preparation.");
    }
  };
  const strategyFailed = strategyOperationStatus === "FAILED" || strategyOperationStatus === "CANCELLED" || Boolean(strategyActionError);
  const teaserAuthoringRequired = deferStrategyGeneration && readiness?.status === "STRATEGY_REQUIRED";
  const strategyPreparing = readiness?.status === "STRATEGY_REQUIRED" && !strategyFailed && !teaserAuthoringRequired;
  const pricingRequired = readiness?.status === "NOT_PREPARED";
  const paidImageNoun = readiness?.paidStepCount === 1 ? "paid image" : "paid images";
  const priceNoun = readiness?.paidStepCount === 1 ? "a price" : "prices";
  const heading = loading && !readiness ? "Loading…" : teaserAuthoringRequired ? "Create Teaser First" : strategyFailed ? "Strategy Needs Attention" : strategyPreparing ? "Preparing Strategy..." : error && !readiness ? "Session Selling Unavailable" : pricingRequired ? "Pricing Required" : readiness?.status === "PREPARING" ? "Preparing..." : readiness?.status === "READY" ? "READY" : readiness?.statusLabel || "Session Selling";
  return <section className="session-selling-panel"><header><div><small>Session Selling</small><h2>{heading}</h2></div>{readiness && readiness.status !== "STRATEGY_REQUIRED" && <span className={`session-selling-badge session-selling-badge--${readiness.status.toLowerCase()}`}>{pricingRequired ? "Pricing Required" : readinessBadge(readiness)}</span>}</header>
    {error && <p role="alert">{error}</p>}
    {strategyActionError && <p className="sale-preparation-error" role="alert">{strategyActionError}</p>}
    {!loading && teaserAuthoringRequired && <div className="session-selling-strategy-required" role="status"><p>Create the Session teaser before preparing the sales strategy.</p></div>}
    {!loading && strategyPreparing && <div className="session-selling-strategy-required" role="status"><p>Analyzing the completed Photoshoot for sequential selling.</p></div>}
    {!loading && strategyFailed && <div className="session-selling-strategy-required">
      <p>We couldn&apos;t prepare the Session sales strategy.</p>
      {readiness?.strategyOperation?.errorMessage && <p className="sale-preparation-error">{readiness.strategyOperation.errorMessage}</p>}
      <button onClick={() => void retryStrategy()} type="button"><RefreshCw size={16} />Retry</button>
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
    {pricingRequired
      ? <p>{readiness.paidStepCount} {paidImageNoun} need{readiness.paidStepCount === 1 ? "s" : ""} {priceNoun} before this Session can be prepared.</p>
      : readiness.status === "PREPARING"
        ? <p>Preparing paid images: {readiness.readyPaidStepCount} of {readiness.paidStepCount}</p>
        : readiness.status === "READY"
          ? <p>{readiness.readyPaidStepCount} of {readiness.paidStepCount} paid images ready</p>
          : <p>Paid images ready: {readiness.readyPaidStepCount} of {readiness.paidStepCount}</p>}
    <div className="session-selling-actions">
      {pricingRequired && <button onClick={() => setDialog("prepare")} type="button"><ShoppingBag size={16} />Set Session Prices</button>}
      {readiness.status === "NEEDS_ATTENTION" && <button onClick={() => setDialog("retry")} type="button"><RefreshCw size={16} />Retry Failed Preparation</button>}
      {readiness.status !== "NOT_PREPARED" && <button onClick={() => setPublished((value) => !value)} type="button">View Published Assets</button>}
    </div>{published && <div className="published-assets">{readiness.steps.map((step) => <article key={step.assetId}><div><strong>Shot {step.shotOrder} · {step.role.replaceAll("_", " ")}</strong><span>{step.access === "FREE" ? "Direct Telegram delivery" : `${step.publicationStatus || "Not published"} · ${step.ready ? "Link ready" : "Link unavailable"}`}</span>{step.publishedAt && <span>Published {new Date(step.publishedAt).toLocaleString()}</span>}</div>{step.access === "PAID" && <><span>{step.priceMinor ? `${step.currency} ${(step.priceMinor / 100).toFixed(2)}` : "Price required"}</span>{step.deliveryUrl && <div className="published-assets__link"><code>{step.deliveryUrl}</code><button aria-label={`Copy Shot ${step.shotOrder} link`} onClick={() => void navigator.clipboard.writeText(step.deliveryUrl!)} type="button"><Copy size={14} /></button><a aria-label={`Open Shot ${step.shotOrder} link`} href={step.deliveryUrl} rel="noreferrer" target="_blank"><ExternalLink size={14} /></a></div>}</>}{step.error && <em>{operatorStepError(step)}</em>}</article>)}</div>}</>}
    {dialog && <PrepareForSaleDialog deliverableId={deliverableId} retry={dialog === "retry"} onClose={() => setDialog(null)} onStarted={(value) => { updateReadiness(value); setPublished(false); }} />}
  </section>;
}

const bundlePrice = (minor: number | null | undefined) => minor == null ? "" : (minor / 100).toFixed(2);

function BundleContentVaultPublishing({ deliverableId, readiness, refresh }: {
  deliverableId: string; readiness: BundleSellingReadiness; refresh: () => Promise<void> | void;
}) {
  const publication = readiness.contentVaultPublication;
  const [options, setOptions] = useState<ContentVaultCaptionOption[]>([]);
  const [selected, setSelected] = useState<number | "custom" | null>(null);
  const [customCaption, setCustomCaption] = useState("");
  const [customError, setCustomError] = useState("");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [editingCaption, setEditingCaption] = useState(false);
  const [captionDraft, setCaptionDraft] = useState("");
  const endpoint = `/api/v1/assets/photoshoots/${encodeURIComponent(deliverableId)}/content-vault`;
  useEffect(() => {
    const persisted = readiness.contentVaultCaptionCandidates?.captions || [];
    if (options.length === 0 && persisted.length === 5) {
      setOptions(persisted);
      setOpen(true);
    }
  }, [options.length, readiness.contentVaultCaptionCandidates]);
  const generate = async () => {
    setBusy(true); setError(""); setCustomError(""); setOpen(false); setOptions([]); setSelected(null);
    try {
      const result = await request<{ captions: ContentVaultCaptionOption[] }>(`${endpoint}/captions/generate`, {
        method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ tone: "CLASSY" }),
        signal: AbortSignal.timeout(120_000),
      });
      const candidates = Array.isArray(result.captions)
        ? result.captions.filter((item) => Boolean(item?.text?.trim())) : [];
      if (candidates.length !== 5) throw new Error("Caption generation did not return five usable options. Please retry.");
      setOptions(candidates); setOpen(true);
    } catch (reason) {
      setOpen(false); setOptions([]);
      setError(reason instanceof DOMException && reason.name === "TimeoutError"
        ? "Bundle caption generation timed out. Please retry."
        : reason instanceof Error ? reason.message : "Unable to generate Bundle captions.");
    }
    finally { setBusy(false); }
  };
  const persistCaption = async (text: string, source: "MANUAL" | "GROK") => {
    setBusy(true); setError("");
    try {
      await request(`${endpoint}/caption`, { method: "PUT", headers: { "content-type": "application/json" },
        body: JSON.stringify({ text, source }) });
      setOpen(false); setEditingCaption(false); setCaptionDraft(""); await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to save Bundle caption."); }
    finally { setBusy(false); }
  };
  const save = async () => {
    const custom = customCaption.trim();
    if (selected === "custom" && !custom) {
      setCustomError("Enter a caption before saving.");
      return;
    }
    const option = typeof selected === "number" ? options[selected] : null;
    if (selected == null || (selected !== "custom" && !option)) return;
    const text = selected === "custom" ? custom : option!.text;
    const source = selected === "custom" ? "MANUAL" : "GROK";
    await persistCaption(text, source);
  };
  const publish = async () => {
    if (!readiness.offeringId || !publication?.canPublish) return;
    setBusy(true); setError("");
    try {
      await request(`/api/v1/commerce-authoring/${readiness.offeringId}/telegram-content-vault`, {
        method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({}),
      });
      await refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to publish Bundle."); }
    finally { setBusy(false); }
  };
  return <section className="content-vault-publishing" aria-labelledby="bundle-vault-publishing-title">
    <h3 id="bundle-vault-publishing-title">Content Vault Publishing</h3>
    <p><strong>{readiness.imageCount} Photos</strong> · ${bundlePrice(readiness.priceMinor)}</p>
    {publication?.previewUrl && <img className="bundle-content-vault-teaser" src={publication.previewUrl} alt="Bundle Content Vault publication preview" />}
    <dl className="content-vault-publishing__preview"><div><dt>Teaser</dt><dd>{readiness.promotionalTeaser?.status || "NOT CONFIGURED"}</dd></div><div><dt>Fanvue Media Link</dt><dd>{readiness.deliveryUrl ? "READY" : "NEEDS ATTENTION"}</dd></div></dl>
    {editingCaption ? <div className="bundle-caption-editor"><label><span>Content Wall caption</span><textarea aria-label="Content Wall caption" maxLength={1024} rows={4} value={captionDraft} onChange={(event) => setCaptionDraft(event.target.value)} /></label><div className="content-vault-publishing__actions"><button disabled={busy || !captionDraft.trim()} onClick={() => void persistCaption(captionDraft.trim(), "MANUAL")} type="button">Save Caption</button><button disabled={busy} onClick={() => { setEditingCaption(false); setCaptionDraft(""); setError(""); }} type="button">Cancel</button></div></div> : <>
      {readiness.contentVaultCaption ? <blockquote>{readiness.contentVaultCaption.text}</blockquote> : <p className="content-vault-publishing__empty">No caption selected.</p>}
      <div className="content-vault-publishing__actions"><button disabled={busy} onClick={() => { setCaptionDraft(readiness.contentVaultCaption?.text || ""); setEditingCaption(true); setError(""); }} type="button">{readiness.contentVaultCaption ? "Edit Caption" : "Write Your Own Caption"}</button><button disabled={busy} onClick={() => void generate()} type="button">{busy ? "Generating Captions…" : "Generate Captions with AI"}</button></div>
    </>}
    {publication?.status === "PUBLISHED" && <div className="content-vault-publishing__published"><strong>Published</strong>{publication.publishedAt && <span>{new Date(publication.publishedAt).toLocaleDateString()}</span>}{publication.providerMessageId && <small>Telegram message {publication.providerMessageId}</small>}</div>}
    {publication?.readinessError && publication.status !== "PUBLISHED" && <small>{publication.readinessError}</small>}
    {error && <p className="sale-preparation-error" role="alert">{error}</p>}
    <button className="sale-preparation-primary" disabled={busy || !publication?.canPublish} onClick={() => void publish()} type="button">{publication?.status === "PUBLISHED" ? "Published to Content Vault" : publication?.status === "PUBLISHING" ? "Publishing…" : "Publish to Content Vault"}</button>
    {open && options.length > 0 && <div className="caption-chooser-backdrop" role="presentation"><div className="caption-chooser" role="dialog" aria-modal="true" aria-label="Choose Bundle Content Vault Caption"><header><div><div><small>Photoshoot Bundle</small><h2>Choose Content Vault Caption</h2></div></div><button aria-label="Close caption chooser" disabled={busy} onClick={() => setOpen(false)} type="button"><X size={18} /></button></header><div className="caption-options">{options.map((option, index) => <button className={selected === index ? "is-selected" : ""} key={option.text} onClick={() => { setSelected(index); setCustomError(""); }} type="button">{option.text}</button>)}</div><div className="bundle-caption-custom"><button className={selected === "custom" ? "is-selected" : ""} onClick={() => { setSelected("custom"); setCustomError(""); }} type="button">Write My Own</button>{selected === "custom" && <label className="caption-chooser__field"><span>Custom Bundle caption</span><textarea aria-label="Custom Bundle caption" autoFocus maxLength={1024} rows={4} value={customCaption} onChange={(event) => { setCustomCaption(event.target.value); setSelected("custom"); setCustomError(""); }} />{customError && <small className="caption-chooser__validation" role="alert">{customError}</small>}<small>{customCaption.length} / 1024</small></label>}</div><footer><button disabled={busy} onClick={() => setOpen(false)} type="button">Cancel</button><button disabled={busy || selected == null || (selected === "custom" && !customCaption.trim())} onClick={() => void save()} type="button">Use Caption</button></footer></div></div>}
  </section>;
}

export function BundleSellingPanel({ deliverableId, salesChannel = "CHAT", onReadinessChange }: {
  deliverableId: string; salesChannel?: "CHAT" | "CONTENT_WALL";
  onReadinessChange?: (value: BundleSellingReadiness) => void;
}) {
  const [readiness, setReadiness] = useState<BundleSellingReadiness | null>(null);
  const [price, setPrice] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [editingPrice, setEditingPrice] = useState(false);
  const [priceUpdated, setPriceUpdated] = useState(false);
  const replacementTarget = useRef<number | null>(null);
  const editingPriceRef = useRef(false);
  const pollingReadiness = useRef(false);
  const load = useCallback(() => request<BundleSellingReadiness>(`/api/v1/assets/photoshoots/${encodeURIComponent(deliverableId)}/sale-preparation`).then((value) => {
    if (value.sellingMode !== "BUNDLE") throw new Error("Bundle readiness is unavailable.");
    setReadiness(value); onReadinessChange?.(value);
    if (!editingPriceRef.current) setPrice(bundlePrice(value.priceMinor));
    setError("");
  }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to load Bundle readiness.")), [deliverableId, onReadinessChange]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const target = replacementTarget.current;
    if (target == null) return;
    const replacementFailed = readiness?.status === "NEEDS_ATTENTION"
      || readiness?.priceReplacement?.state === "PREFLIGHT_FAILED"
      || readiness?.priceReplacement?.state === "REPLACEMENT_FAILED";
    if (replacementFailed) {
      replacementTarget.current = null; setSaving(false);
      setError(readiness?.error || "Unable to replace the Fanvue Media Link. Retry the price update.");
      return;
    }
    if (readiness?.status !== "READY" || readiness.priceMinor !== target) return;
    replacementTarget.current = null;
    editingPriceRef.current = false;
    setEditingPrice(false); setSaving(false); setPrice(bundlePrice(readiness.priceMinor));
    setPriceUpdated(true);
    const timer = window.setTimeout(() => setPriceUpdated(false), 4500);
    return () => window.clearTimeout(timer);
  }, [readiness?.priceMinor, readiness?.status]);
  useEffect(() => {
    if (readiness?.status !== "PREPARING") return;
    const poll = async () => {
      if (pollingReadiness.current) return;
      pollingReadiness.current = true;
      try { await load(); } finally { pollingReadiness.current = false; }
    };
    const timer = window.setInterval(() => void poll(), 2500);
    return () => { window.clearInterval(timer); pollingReadiness.current = false; };
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
      setReadiness(value); onReadinessChange?.(value);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to prepare Bundle."); }
    finally {
      if (retry) await load();
      setSaving(false);
    }
  };
  const beginPriceUpdate = () => {
    setPrice(bundlePrice(readiness?.priceMinor)); setError("");
    editingPriceRef.current = true; setEditingPrice(true);
  };
  const cancelPriceUpdate = () => {
    setPrice(bundlePrice(readiness?.priceMinor)); setError("");
    editingPriceRef.current = false; setEditingPrice(false);
  };
  const submitPriceUpdate = async () => {
    if (!readiness || saving || priceMinor == null) {
      setError("Bundle price must be between $3.00 and $500.00."); return;
    }
    if (priceMinor === readiness.priceMinor) { cancelPriceUpdate(); return; }
    setSaving(true); setError(""); replacementTarget.current = priceMinor;
    try {
      const value = await request<BundleSellingReadiness>(`/api/v1/assets/photoshoots/${encodeURIComponent(deliverableId)}/bundle-price`, {
        method: "PUT", headers: { "content-type": "application/json" },
        body: JSON.stringify({ priceMinor }),
      });
      setReadiness(value); onReadinessChange?.(value);
    } catch (reason) {
      replacementTarget.current = null; setSaving(false);
      setError(reason instanceof Error ? reason.message : "Unable to update Bundle price.");
    }
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
          <p><strong>Content Wall Publishing</strong><br />Uses the prepared Bundle package below.</p>
        </div>}
      <div className="bundle-selling-price-row"><label className="bundle-selling-price" htmlFor="bundle-price"><span>Bundle Price</span><span><b>$</b><input id="bundle-price" aria-label="Bundle Price" disabled={(readiness.status === "READY" && !editingPrice) || saving} inputMode="decimal" min="3" max="500" step=".01" type="number" value={price} onChange={(event) => setPrice(event.target.value)} /></span></label>{readiness.status === "READY" && !editingPrice && <button onClick={beginPriceUpdate} type="button">Update</button>}{editingPrice && <div className="bundle-selling-price-actions"><button disabled={saving || priceMinor == null} onClick={() => void submitPriceUpdate()} type="button">{saving ? "Updating..." : "Submit"}</button><button disabled={saving} onClick={cancelPriceUpdate} type="button">Cancel</button></div>}</div>
      {priceUpdated && <div className="asset-library-toast" role="status">Price and Fanvue Media Link updated.</div>}
      {readiness.status === "PREPARING" && <div className="session-selling-progress" role="status"><strong>Preparing Bundle...</strong><progress aria-label="Bundle preparation progress" /></div>}
      {readiness.error && <p className="sale-preparation-error" role="alert">{readiness.error}</p>}
      <div className="session-selling-actions">
        {readiness.status === "NOT_CONFIGURED" && <button disabled={priceMinor == null || saving} onClick={() => void submit()} type="button"><ShoppingBag size={16} />{saving ? "Starting..." : "Prepare Bundle"}</button>}
        {readiness.status === "NEEDS_ATTENTION" && <button disabled={priceMinor == null || saving} onClick={() => void submit(true)} type="button"><RefreshCw size={16} />Retry Bundle Preparation</button>}
        {readiness.status === "READY" && readiness.deliveryUrl && <a href={readiness.deliveryUrl} rel="noreferrer" target="_blank"><ExternalLink size={14} />Open Fanvue Media Link</a>}
      </div>
      {readiness.status === "READY" && <p>Fanvue Media Link ready · {readiness.currency} {bundlePrice(readiness.priceMinor)}</p>}
      {readiness.promotionalTeaser && <BundlePromotionalTeaser deliverableId={deliverableId} initial={readiness.promotionalTeaser} onChanged={(promotionalTeaser) => {
        setReadiness((current) => current ? { ...current, promotionalTeaser } : current);
        void load();
      }} />}
      {salesChannel === "CONTENT_WALL" && readiness.status === "READY" && <BundleContentVaultPublishing deliverableId={deliverableId} readiness={readiness} refresh={load} />}
    </>}
  </section>;
}
