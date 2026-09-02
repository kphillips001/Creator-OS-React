import { Archive, Check, ExternalLink, ImageOff, Library, RotateCw, X } from "lucide-react";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { useBackgroundOperations } from "../background-operations/BackgroundOperationsContext";
import type { RegenerationResult, RegenerationSource, RegenerationWorkspace } from "./types";
import "./regeneration-studio.css";

type SourceResponse = { success: boolean; source: RegenerationSource | null; eligibility: { canRegenerate: boolean; reason?: string | null }; error?: string };
type ResetIntent = { kind: "reset" } | { kind: "switch"; sourceId: string };

function resultEqual(left: RegenerationResult, right: RegenerationResult) {
  return left.resultId === right.resultId && left.variationIndex === right.variationIndex
    && left.status === right.status && left.generatedImageId === right.generatedImageId
    && left.generationRecipeId === right.generationRecipeId && left.disposition === right.disposition
    && left.mediaUrl === right.mediaUrl && left.errorCode === right.errorCode
    && left.errorMessage === right.errorMessage;
}

function reconcileWorkspace(current: RegenerationWorkspace | null, incoming: RegenerationWorkspace) {
  if (!current || current.run.operationId !== incoming.run.operationId) return incoming;
  const prior = new Map(current.results.map((item) => [item.resultId, item]));
  let resultsChanged = current.results.length !== incoming.results.length;
  const results = incoming.results.map((item) => {
    const previous = prior.get(item.resultId);
    if (previous && resultEqual(previous, item)) return previous;
    resultsChanged = true;
    return item;
  });
  if (!resultsChanged && results.some((item, index) => item !== current.results[index])) resultsChanged = true;
  const operationUnchanged = current.operation.status === incoming.operation.status
    && current.operation.progressCurrent === incoming.operation.progressCurrent
    && current.operation.progressTotal === incoming.operation.progressTotal
    && current.operation.progressPercent === incoming.operation.progressPercent
    && current.operation.currentStage === incoming.operation.currentStage
    && current.operation.stageMessage === incoming.operation.stageMessage
    && current.operation.errorMessage === incoming.operation.errorMessage
    && current.run.status === incoming.run.status
    && current.run.requestedCount === incoming.run.requestedCount
    && current.run.sourceGeneratedImageId === incoming.run.sourceGeneratedImageId;
  if (operationUnchanged && !resultsChanged) return current;
  return { ...incoming, results: resultsChanged ? results : current.results };
}

const RegenerationResultCard = memo(function RegenerationResultCard({ item, selected, onPreview, onToggle }: {
  item: RegenerationResult; selected: boolean; onPreview: (url: string) => void; onToggle: (id: string) => void;
}) {
  return <article className={`regeneration-card regeneration-card--${item.status.toLowerCase()}`}>
    {item.mediaUrl ? <button className="regeneration-card__image" type="button" onClick={() => onPreview(item.mediaUrl!)}><img loading="lazy" decoding="async" src={item.mediaUrl} alt={`Regenerated variation ${item.variationIndex}`} /></button> : <div className="regeneration-card__placeholder"><ImageOff /></div>}
    <div><span>Variation {item.variationIndex}</span><strong>{item.disposition === "PROMOTED" ? "Sent to Generation Library" : item.status}</strong>{item.status === "SUCCEEDED" && item.disposition === "PENDING_REVIEW" && <label><input type="checkbox" checked={selected} onChange={() => onToggle(item.resultId)} /> Select</label>}{item.disposition === "PROMOTED" && <Check aria-label="Promoted" />}{item.errorMessage && <small>{item.errorMessage}</small>}</div>
  </article>;
});

export function RegenerationStudioPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const background = useBackgroundOperations();
  const routeSourceId = params.get("source") || "";
  const requestedOperation = params.get("operation") || "";
  const [sourceId, setSourceId] = useState(routeSourceId);
  const sourceIdRef = useRef(sourceId);
  const navigationTargetRef = useRef<string | null>(null);
  const [source, setSource] = useState<RegenerationSource | null>(null);
  const [eligible, setEligible] = useState(false);
  const [draftCount, setDraftCount] = useState(1);
  const hydratedCountForOperation = useRef("");
  const [operationId, setOperationId] = useState(requestedOperation);
  const [workspace, setWorkspace] = useState<RegenerationWorkspace | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [preview, setPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [resetIntent, setResetIntent] = useState<ResetIntent | null>(null);
  const [restoring, setRestoring] = useState(true);

  useEffect(() => { sourceIdRef.current = sourceId; }, [sourceId]);
  const active = Boolean(workspace && ["QUEUED", "RUNNING", "WAITING_EXTERNAL", "CANCEL_REQUESTED"].includes(workspace.operation.status));
  const unresolved = useMemo(() => workspace?.results.filter((item) => item.status === "SUCCEEDED" && item.disposition === "PENDING_REVIEW") ?? [], [workspace]);

  const routeFor = useCallback((nextSourceId: string, nextOperationId = "") => nextSourceId
    ? `/studio/regeneration?source=${encodeURIComponent(nextSourceId)}${nextOperationId ? `&operation=${encodeURIComponent(nextOperationId)}` : ""}`
    : "/studio/regeneration", []);

  const applySource = useCallback((nextSourceId: string) => {
    sourceIdRef.current = nextSourceId;
    navigationTargetRef.current = nextSourceId;
    setSourceId(nextSourceId); setSource(null); setEligible(false); setOperationId(""); setWorkspace(null);
    setSelected(new Set()); setDraftCount(1); hydratedCountForOperation.current = ""; setError(""); setMessage(""); setResetIntent(null);
    navigate(routeFor(nextSourceId), { replace: true });
  }, [navigate, routeFor]);

  useEffect(() => {
    let mounted = true;
    if (requestedOperation) { setOperationId(requestedOperation); setRestoring(false); return; }
    if (routeSourceId) { setRestoring(false); return; }
    Promise.resolve(fetch("/api/v1/regeneration/workspace/current", { cache: "no-store" }))
      .then(async (response) => {
        if (!response) return;
        const body = await response.json() as { success: boolean; workspace: { operationId: string; sourceGeneratedImageId: string } | null };
        if (!response.ok || !body.success) throw new Error("Unable to restore Regeneration Studio.");
        if (mounted && body.workspace) {
          setSourceId(body.workspace.sourceGeneratedImageId); setOperationId(body.workspace.operationId);
          navigate(routeFor(body.workspace.sourceGeneratedImageId, body.workspace.operationId), { replace: true });
        }
      }).catch((reason) => { if (mounted) setError(reason instanceof Error ? reason.message : "Unable to restore Regeneration Studio."); })
      .finally(() => { if (mounted) setRestoring(false); });
    return () => { mounted = false; };
  }, [navigate, requestedOperation, routeFor, routeSourceId]);

  useEffect(() => {
    if (navigationTargetRef.current !== null) {
      if (routeSourceId === navigationTargetRef.current) navigationTargetRef.current = null;
      else return;
    }
    if (routeSourceId === sourceIdRef.current) {
      if (requestedOperation !== operationId) { setOperationId(requestedOperation); setWorkspace(null); setSelected(new Set()); }
      return;
    }
    const current = sourceIdRef.current;
    if (active) {
      setError("Wait for the active regeneration to finish before changing the source.");
      navigate(routeFor(current, operationId), { replace: true });
    } else if (unresolved.length) {
      setResetIntent({ kind: "switch", sourceId: routeSourceId });
      navigate(routeFor(current, operationId), { replace: true });
    } else if (!operationId) {
      applySource(routeSourceId);
    }
  }, [active, applySource, navigate, operationId, requestedOperation, routeFor, routeSourceId, unresolved.length]);

  useEffect(() => {
    if (!sourceId) { setSource(null); setEligible(false); return; }
    const controller = new AbortController();
    fetch(`/api/v1/regeneration/source/${encodeURIComponent(sourceId)}`, { signal: controller.signal })
      .then(async (response) => { const body = await response.json() as SourceResponse; if (!response.ok || !body.success) throw new Error(body.error || "Unable to load regeneration source."); return body; })
      .then((body) => { setSource(body.source); setEligible(body.eligibility.canRegenerate); setError(body.eligibility.canRegenerate ? "" : body.eligibility.reason || "This image cannot be regenerated."); })
      .catch((reason) => { if (!(reason instanceof DOMException && reason.name === "AbortError")) setError(reason instanceof Error ? reason.message : "Unable to load source."); });
    return () => controller.abort();
  }, [sourceId]);

  useEffect(() => {
    if (!sourceId || operationId || !background.initialized) return;
    const found = background.bySubject("generated_image", sourceId).find((item) => item.operationType === "regeneration");
    if (found) { setOperationId(found.operationId); navigate(routeFor(sourceId, found.operationId), { replace: true }); }
  }, [background, navigate, operationId, routeFor, sourceId]);

  const loadWorkspace = useCallback(async (signal?: AbortSignal) => {
    if (!operationId) return;
    const expectedOperationId = operationId;
    const response = await fetch(`/api/v1/regeneration/${encodeURIComponent(expectedOperationId)}`, { signal });
    const body = await response.json() as RegenerationWorkspace;
    if (response.status === 410) { applySource(""); return; }
    if (!response.ok || !body.success) throw new Error(body.error || "Unable to reconnect to regeneration.");
    if (signal?.aborted || body.run.operationId !== expectedOperationId) return;
    setWorkspace((current) => reconcileWorkspace(current, body));
    if (hydratedCountForOperation.current !== expectedOperationId) {
      hydratedCountForOperation.current = expectedOperationId;
      setDraftCount(body.run.requestedCount);
    }
    if (!sourceIdRef.current) {
      sourceIdRef.current = body.run.sourceGeneratedImageId;
      setSourceId(body.run.sourceGeneratedImageId);
      navigate(routeFor(body.run.sourceGeneratedImageId, operationId), { replace: true });
    }
    return body;
  }, [applySource, navigate, operationId, routeFor]);

  useEffect(() => {
    if (!operationId) return;
    let mounted = true;
    const controller = new AbortController();
    let timer = 0;
    const read = async () => {
      try {
        const next = await loadWorkspace(controller.signal);
        if (mounted && next && ["QUEUED", "RUNNING", "WAITING_EXTERNAL", "CANCEL_REQUESTED"].includes(next.operation.status)) {
          timer = window.setTimeout(() => void read(), 1500);
        }
      } catch (reason) {
        if (mounted && !(reason instanceof DOMException && reason.name === "AbortError")) setError(reason instanceof Error ? reason.message : "Unable to load regeneration.");
      }
    };
    void read();
    return () => { mounted = false; controller.abort(); window.clearTimeout(timer); };
  }, [loadWorkspace, operationId]);

  const regenerate = async () => {
    if (!sourceId || !eligible || busy) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const response = await fetch("/api/v1/regeneration", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source_generated_image_id: sourceId, count: draftCount }) });
      const body = await response.json() as { success: boolean; operationId?: string; error?: string };
      if (!response.ok || !body.success || !body.operationId) throw new Error(body.error || "Regeneration could not be started.");
      setOperationId(body.operationId); navigate(routeFor(sourceId, body.operationId), { replace: true }); await background.refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Regeneration could not be started."); } finally { setBusy(false); }
  };

  const selectable = unresolved;
  const visibleResults = useMemo(() => workspace?.results.filter((item) => item.disposition !== "ARCHIVED") ?? [], [workspace]);
  const toggle = useCallback((id: string) => setSelected((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; }), []);
  const openPreview = useCallback((url: string) => setPreview(url), []);
  const transitionSelected = async (action: "promote" | "archive", ids = [...selected]) => {
    if (!operationId || !ids.length || busy) return false;
    setBusy(true); setError("");
    try {
      const response = await fetch(`/api/v1/regeneration/${encodeURIComponent(operationId)}/${action}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ result_ids: ids }) });
      const body = await response.json() as { success: boolean; message?: string; error?: string; workspaceDismissed?: boolean };
      if (!response.ok || !body.success) throw new Error(body.error || `Selected results could not be ${action === "archive" ? "archived" : "added to Generation Library"}.`);
      setMessage(body.message || (action === "archive" ? `${ids.length} results archived` : `${ids.length} images added to Generation Library`));
      setSelected(new Set());
      if (action === "promote" && body.workspaceDismissed) { applySource(""); return true; }
      const refreshed = await loadWorkspace();
      if (action === "promote" && refreshed && !refreshed.results.some((item) => item.status === "SUCCEEDED" && item.disposition === "PENDING_REVIEW")) {
        await fetch(`/api/v1/regeneration/${encodeURIComponent(operationId)}/dismiss`, { method: "POST" });
        applySource("");
      }
      return true;
    } catch (reason) { setError(reason instanceof Error ? reason.message : `${action} failed.`); return false; } finally { setBusy(false); }
  };

  const dismissAndApply = async (nextSourceId = "") => {
    if (operationId) {
      const response = await fetch(`/api/v1/regeneration/${encodeURIComponent(operationId)}/dismiss`, { method: "POST" });
      if (!response.ok) { setError("Regeneration Studio could not be reset."); return; }
    }
    applySource(nextSourceId);
  };
  const requestReset = () => { if (active || busy) return; if (unresolved.length) setResetIntent({ kind: "reset" }); else void dismissAndApply(); };
  const confirmArchiveAndContinue = async () => {
    if (!resetIntent) return;
    const intent = resetIntent;
    if (await transitionSelected("archive", unresolved.map((item) => item.resultId))) await dismissAndApply(intent.kind === "switch" ? intent.sourceId : "");
  };

  if (restoring) return <section className="regeneration-studio"><header><p>Creative workflow</p><h1>Regeneration Studio</h1></header><div className="regeneration-empty"><RotateCw /><h2>Restoring Regeneration Studio…</h2></div></section>;
  if (!sourceId) return <section className="regeneration-studio"><header><p>Creative workflow</p><h1>Regeneration Studio</h1></header><div className="regeneration-empty"><RotateCw /><h2>Choose a Regenerate-eligible image</h2><p>Open Generation Library and choose Regenerate from same recipe to begin.</p><Link to="/library/generations"><Library size={17} /> Open Generation Library</Link></div></section>;

  const completed = Number(workspace?.operation.metadata.completedCount ?? workspace?.results.filter((item) => item.status === "SUCCEEDED").length ?? 0);
  const failed = Number(workspace?.operation.metadata.failedCount ?? workspace?.results.filter((item) => ["FAILED", "SUBMISSION_AMBIGUOUS"].includes(item.status)).length ?? 0);
  return <section className="regeneration-studio">
    <header><div><p>Creative workflow</p><h1>Regeneration Studio</h1><span>Create fresh variations from the source generation's trusted recipe.</span></div><button className="regeneration-reset" type="button" disabled={active || busy} onClick={requestReset}>Reset Studio</button></header>
    {error && <div className="regeneration-notice regeneration-notice--error" role="alert">{error}</div>}
    {message && <div className="regeneration-notice" role="status">{message}</div>}
    {source && <div className="regeneration-source"><button type="button" onClick={() => setPreview(source.mediaUrl)}><img src={source.mediaUrl} alt="Regeneration source" /></button><div><small>Source generation</small><h2>{source.generatedImageId}</h2><dl><div><dt>Provider</dt><dd>{source.providerDisplayName || "Provider unavailable"}</dd></div><div><dt>Model</dt><dd>{source.modelDisplayName || "Model unavailable"}</dd></div><div><dt>Workflow</dt><dd>{source.sourceWorkflow || source.creativeMode || "Generation"}</dd></div><div><dt>Readiness</dt><dd>{eligible ? "Ready to regenerate" : "Not eligible"}</dd></div></dl><p>The source is context only. Backend recipe references remain authoritative.</p></div></div>}
    {source && eligible && !active && <div className="regeneration-controls"><label>Number of variations<select aria-label="Number of variations" value={draftCount} onChange={(event) => setDraftCount(Number(event.target.value))}>{[1,2,3,4,5].map((value) => <option value={value} key={value}>{value}</option>)}</select></label><button type="button" disabled={busy} onClick={regenerate}><RotateCw size={17} /> {busy ? "Starting…" : "Regenerate"}</button></div>}
    {workspace && <div className="regeneration-progress" role="status"><div><strong>{active ? `Regenerating ${Math.min(completed + 1, workspace.run.requestedCount)} of ${workspace.run.requestedCount}…` : workspace.operation.status === "SUCCEEDED" ? "Regeneration complete" : workspace.operation.stageMessage || workspace.operation.status}</strong><span>{completed} completed · {failed} failed · {workspace.run.requestedCount - completed - failed} remaining</span></div><progress max={100} value={workspace.operation.progressPercent} /></div>}
    {workspace && visibleResults.length > 0 && <div className="regeneration-results"><div className="regeneration-results__header"><div><h2>Variations</h2><span>Select successful results to send to Generation Library or Archive.</span></div>{selectable.length > 1 && <button type="button" onClick={() => setSelected(selected.size === selectable.length ? new Set() : new Set(selectable.map((item) => item.resultId)))}>{selected.size === selectable.length ? "Clear selection" : "Select all"}</button>}</div><div className="regeneration-grid">{visibleResults.map((item: RegenerationResult) => <RegenerationResultCard item={item} selected={selected.has(item.resultId)} onPreview={openPreview} onToggle={toggle} key={item.resultId} />)}</div>{selected.size > 0 && <div className="regeneration-promote"><button type="button" disabled={busy} onClick={() => void transitionSelected("archive")}><Archive size={17} /> Archive Selected</button><button type="button" disabled={busy} onClick={() => void transitionSelected("promote")}><ExternalLink size={17} /> Send Selected to Generation Library</button></div>}</div>}
    {preview && <div className="regeneration-lightbox" role="dialog" aria-modal="true" aria-label="Regeneration image preview" onMouseDown={(event) => { if (event.target === event.currentTarget) setPreview(null); }}><button aria-label="Close preview" onClick={() => setPreview(null)} type="button"><X /></button><img src={preview} alt="Expanded regeneration" /></div>}
    {resetIntent && <div className="regeneration-confirm" role="dialog" aria-modal="true" aria-labelledby="regeneration-reset-title"><div><h2 id="regeneration-reset-title">Archive unresolved results?</h2><p>{resetIntent.kind === "switch" ? "Archive the pending variations before changing to the new source." : "Archive the pending variations before resetting Regeneration Studio."}</p><span>Archived media and recipes remain available in System Archive.</span><footer><button type="button" disabled={busy} onClick={() => setResetIntent(null)}>Cancel</button><button type="button" disabled={busy} onClick={() => void confirmArchiveAndContinue()}><Archive size={16} /> {resetIntent.kind === "switch" ? "Archive & Continue" : "Archive & Reset"}</button></footer></div></div>}
  </section>;
}
