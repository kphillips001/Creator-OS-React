import { useEffect, useMemo, useRef, useState } from "react";

import {
  createPromptPreview,
  discardExplicitInspiration,
  dismissExplicitInspiration,
  enhanceCreativeTags,
  getExplicitInspirationOperation,
  handoffExplicitInspiration,
  inspireExplicitContent,
  resetExplicitGenerationBatch,
  retryFailedExplicitGenerationBatch,
  type ExplicitInspirationTierMode,
  startExplicitGenerationBatch,
  updateExplicitGenerationBatch,
} from "../../../infrastructure/api/contentStudioApi";
import { useBackgroundOperations } from "../../background-operations/BackgroundOperationsContext";
import type { ContentStudioContext } from "../types/contentStudioContext";
import type { ExplicitGenerationInput } from "../types/generation";
import { type PlannerBatchItem, updatePlannerBatchItems } from "../types/plannerBatch";
import { useContentStudioConfiguration } from "../hooks/useContentStudioConfiguration";
import {
  beginExplicitGenerationBatch,
  ExplicitBatchCancelledError,
  type ExplicitBatchSnapshot,
} from "../services/explicitGenerationBatch";
import {
  GenerationWorkflowSections,
  type GenerationWorkflowHandle,
  type PlannerBatchProgress,
} from "./GenerationWorkflowSections";

const EXPLICIT_RECONNECT_ORIGINS = ["explicit_inspiration", "explicit_tags"];
const EXPLICIT_IDEA_COUNTS = [1, 2, 3, 5, 10, 12];
const dismissedInspirationOperationIds = new Set<string>();

type ExplicitLane = "tags" | "inspire";
type ExplicitTier = "hardcore" | "softcore";

export function sceneFirstConcept(concept: string) {
  return concept.replace(/^\s*Ava(?:\s+Blackthorne)?\s*(?:[:,—-]\s*)?/i, "").trim();
}

type ExplicitConceptItem = {
  id: string;
  tier: ExplicitTier;
  concept: string;
};

function conceptId(tier: ExplicitTier, index: number): string {
  return `${tier}-${index}`;
}

export function ExplicitContentSection({
  context,
  onStartNewGeneration,
}: {
  context: ContentStudioContext;
  onStartNewGeneration?: () => void;
}) {
  const generationRef = useRef<GenerationWorkflowHandle>(null);
  const reconnectedExplicitBatchRef = useRef(false);
  const explicitStartInFlightRef = useRef(false);
  const backgroundOperations = useBackgroundOperations();
  const { configuration, error: configurationError } = useContentStudioConfiguration();
  const [lane, setLane] = useState<ExplicitLane>("tags");
  const [tags, setTags] = useState("");
  const [enhancedTags, setEnhancedTags] = useState("");
  const [provider, setProvider] = useState("");
  const [imageCount, setImageCount] = useState(1);
  const [hardcore, setHardcore] = useState<string[]>([]);
  const [softcore, setSoftcore] = useState<string[]>([]);
  const [inspirationOperationId, setInspirationOperationId] = useState("");
  const [inspirationHandedOff, setInspirationHandedOff] = useState(false);
  const [inspirationTierMode, setInspirationTierMode] = useState<ExplicitInspirationTierMode>("both");
  const [inspirationCount, setInspirationCount] = useState(10);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [prompts, setPrompts] = useState<string[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [activated, setActivated] = useState(false);
  const [accordionOpen, setAccordionOpen] = useState(false);
  const [items, setItems] = useState<PlannerBatchItem[]>([]);
  const [progress, setProgress] = useState<PlannerBatchProgress | null>(null);
  const [stopConfirmation, setStopConfirmation] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [stoppedOperationId, setStoppedOperationId] = useState("");
  const [retryingFailed, setRetryingFailed] = useState(false);

  const activeProvider = provider || configuration?.defaults.provider || "";
  const activeBatch = backgroundOperations.active
    .filter((operation) => operation.operationType === "content_studio_explicit_batch")
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt))[0];
  const partialBatch = backgroundOperations.recent
    .filter((operation) => operation.operationType === "content_studio_explicit_batch"
      && operation.status === "PARTIAL" && !operation.metadata.workspaceDismissed)
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt))[0];
  const explicitWorkspaceBatch = activeBatch ?? partialBatch;
  const cancelledBatch = backgroundOperations.recent
    .filter((operation) => operation.operationType === "content_studio_explicit_batch"
      && operation.status === "CANCELLED" && !operation.metadata.workspaceDismissed)
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt))[0];
  useEffect(() => {
    if (!activeBatch && cancelledBatch && !stoppedOperationId) {
      setStoppedOperationId(cancelledBatch.operationId);
    }
  }, [activeBatch, cancelledBatch, stoppedOperationId]);
  // The explicit enhancer guarantees preservation of all user anchors, so its
  // editable output is the authoritative replacement when one exists.
  const effectiveInput = enhancedTags.trim() || tags.trim();
  const conceptItems = useMemo<ExplicitConceptItem[]>(
    () => [
      ...hardcore.map((concept, index) => ({
        id: conceptId("hardcore", index),
        tier: "hardcore" as const,
        concept,
      })),
      ...softcore.map((concept, index) => ({
        id: conceptId("softcore", index),
        tier: "softcore" as const,
        concept,
      })),
    ],
    [hardcore, softcore],
  );
  const selectedConcepts = useMemo(
    () => conceptItems.filter((item) => selected.has(item.id)),
    [conceptItems, selected],
  );
  const blocked = context.status === "reference_missing" || !activeProvider;
  const hasConcepts = conceptItems.length > 0;
  const allSelected = hasConcepts && selected.size === conceptItems.length;
  const contentStudioOperations = backgroundOperations.byWorkspace("content_studio");
  const successfullyConsumedBatchIds = new Set(contentStudioOperations
    .filter((operation) => operation.operationType === "content_studio_explicit_batch" && operation.status === "SUCCEEDED")
    .map((operation) => operation.operationId));
  const inspirationOperation = contentStudioOperations.find((operation) => (
    operation.operationType === "content_studio_explicit_inspiration"
    && (operation.status === "QUEUED" || operation.status === "RUNNING" || operation.status === "WAITING_EXTERNAL" || operation.status === "FAILED")
    && String(operation.metadata.phase || "") !== "HANDED_OFF"
  ));
  const handedOffInspiration = contentStudioOperations
    .filter((operation) => (
      operation.operationType === "content_studio_explicit_inspiration"
      && operation.status === "SUCCEEDED"
      && String(operation.metadata.phase || "") === "HANDED_OFF"
      && !operation.metadata.workspaceDismissed
      && Boolean(operation.resultReference)
      && !successfullyConsumedBatchIds.has(String(operation.resultReference))
      && !dismissedInspirationOperationIds.has(operation.operationId)
    ))
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt))[0];

  useEffect(() => {
    if (!inspirationOperation) return;
    const metadata = inspirationOperation.metadata;
    const mode = String(metadata.tierMode || "both") as ExplicitInspirationTierMode;
    const requestedCount = Number(metadata.requestedCount || 10);
    setInspirationOperationId(inspirationOperation.operationId);
    setInspirationHandedOff(false);
    setInspirationTierMode(mode);
    setInspirationCount(requestedCount);
    setLane("inspire");
    setAccordionOpen(true);
    if (inspirationOperation.status === "FAILED") {
      setPending(false);
      setError(inspirationOperation.errorMessage || "Explicit inspiration failed. Retry the operation from Jobs.");
      return;
    }
    const waiting = inspirationOperation.currentStage === "WAITING_SELECTION";
    setPending(!waiting);
    const tierErrors = metadata.tierErrors && typeof metadata.tierErrors === "object"
      ? Object.values(metadata.tierErrors as Record<string, unknown>).map(String).filter(Boolean)
      : [];
    setError(waiting && tierErrors.length ? `Some concepts could not be generated: ${tierErrors.join("; ")}` : "");
    if (waiting) {
      setHardcore((Array.isArray(metadata.hardcore) ? metadata.hardcore : []).map((value) => sceneFirstConcept(String(value))));
      setSoftcore((Array.isArray(metadata.softcore) ? metadata.softcore : []).map((value) => sceneFirstConcept(String(value))));
    }
  }, [inspirationOperation]);

  useEffect(() => {
    if (inspirationOperation || !handedOffInspiration || inspirationOperationId) return;
    let cancelled = false;
    void getExplicitInspirationOperation(handedOffInspiration.operationId).then((operation) => {
      if (cancelled || operation.status !== "SUCCEEDED"
        || String(operation.metadata.phase || "") !== "HANDED_OFF"
        || Boolean(operation.metadata.workspaceDismissed) || !operation.resultReference) return;
      const metadata = operation.metadata;
      setInspirationOperationId(operation.operationId);
      setInspirationHandedOff(true);
      setInspirationTierMode(String(metadata.tierMode || "both") as ExplicitInspirationTierMode);
      setInspirationCount(Number(metadata.requestedCount || 10));
      setHardcore((Array.isArray(metadata.hardcore) ? metadata.hardcore : []).map((value) => sceneFirstConcept(String(value))));
      setSoftcore((Array.isArray(metadata.softcore) ? metadata.softcore : []).map((value) => sceneFirstConcept(String(value))));
      setSelected(new Set());
      setLane("inspire");
      setAccordionOpen(true);
    }).catch(() => {
      // A stale recent summary must not prevent normal Content Studio use.
    });
    return () => { cancelled = true; };
  }, [handedOffInspiration, inspirationOperation, inspirationOperationId]);

  useEffect(() => {
    const operation = explicitWorkspaceBatch;
    if (!operation) {
      if (reconnectedExplicitBatchRef.current) {
        reconnectedExplicitBatchRef.current = false;
        setActivated(false);
        setPending(false);
        setItems([]);
        setProgress(null);
      }
      return;
    }
    const metadata = operation.metadata as Partial<ExplicitBatchSnapshot>;
    const totalIdeas = Number(metadata.totalIdeas ?? operation.progressTotal ?? 0);
    if (!totalIdeas) return;
    reconnectedExplicitBatchRef.current = true;
    const restoredItems = Array.isArray(metadata.items) ? metadata.items : [];
    setActivated(true);
    setAccordionOpen(true);
    setPending(operation.status === "QUEUED" || operation.status === "RUNNING" || operation.status === "CANCEL_REQUESTED");
    setItems(restoredItems);
    setPrompts(Array.isArray(metadata.prompts) ? metadata.prompts : []);
    setProgress({
      completedIdeas: Number(metadata.completedIdeas ?? operation.progressCurrent ?? 0),
      currentIdeaIndex: Number(metadata.currentIdeaIndex ?? 1),
      failedIdeas: Number(metadata.failedIdeas ?? 0),
      phase: metadata.phase ?? "preparing",
      totalIdeas,
    });
  }, [explicitWorkspaceBatch]);

  const toggleSelected = (id: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectTier = (tier: ExplicitTier, selectAll: boolean) => {
    const tierIds = conceptItems.filter((item) => item.tier === tier).map((item) => item.id);
    setSelected((current) => {
      const next = new Set(current);
      for (const id of tierIds) {
        if (selectAll) next.add(id);
        else next.delete(id);
      }
      return next;
    });
  };

  const enhance = async () => {
    if (!tags.trim() || pending) return;
    setPending(true);
    setError("");
    try {
      setEnhancedTags(await enhanceCreativeTags(tags, true));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Explicit enhancement failed");
    } finally {
      setPending(false);
    }
  };

  const generateTags = async () => {
    if (!effectiveInput || blocked || pending) return;
    setPending(true);
    setActivated(true);
    setError("");
    try {
      const explicitInput: ExplicitGenerationInput = {
        sourceText: effectiveInput,
        originalSource: tags.trim(),
        sourceType: "operator_tags_or_prose",
        origin: "explicit_tags",
        requiredSemanticAttributes: {},
        requestedImageCount: imageCount,
        lineage: {
          enhancedResult: enhancedTags.trim(),
          originalSource: tags.trim(),
        },
      };
      const preview = await createPromptPreview(
        "explicit", effectiveInput, imageCount, undefined, "explicit", explicitInput,
      );
      setPrompts(preview.prompts);
      await generationRef.current?.generate({
        creativeMode: "explicit",
        lane: "explicit",
        promptBatch: preview.prompts,
        promptCount: imageCount,
        promptSource: effectiveInput,
        promptSourceLabel: "Enhanced Explicit Tags",
        origin: "explicit_tags",
        explicitInput,
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Explicit generation failed");
    } finally {
      setPending(false);
    }
  };

  const inspire = async () => {
    if (pending) return;
    let durableOperationStarted = false;
    setPending(true);
    setError("");
    try {
      const next = await inspireExplicitContent(inspirationTierMode, inspirationCount);
      durableOperationStarted = Boolean(next.operationId);
      setInspirationOperationId(next.operationId);
      setInspirationHandedOff(false);
      if (next.hardcore.length || next.softcore.length) {
        setHardcore(next.hardcore.map(sceneFirstConcept));
        setSoftcore(next.softcore.map(sceneFirstConcept));
      }
      setSelected(new Set());
      await backgroundOperations.refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Explicit inspiration failed");
    } finally {
      if (!durableOperationStarted) setPending(false);
    }
  };

  const inspirationStatus = inspirationTierMode === "both"
    ? `Generating ${inspirationCount} ideas — ${Math.ceil(inspirationCount / 2)} Softcore + ${Math.floor(inspirationCount / 2)} Hardcore…`
    : `Generating ${inspirationCount} ${inspirationTierMode === "softcore" ? "Softcore" : "Hardcore"} ${inspirationCount === 1 ? "idea" : "ideas"}…`;

  const startOverInspiration = async () => {
    if (!inspirationOperationId) return;
    setPending(true); setError("");
    try {
      if (inspirationHandedOff) {
        dismissedInspirationOperationIds.add(inspirationOperationId);
        await dismissExplicitInspiration(inspirationOperationId);
      } else {
        await discardExplicitInspiration(inspirationOperationId);
      }
      setInspirationOperationId(""); setInspirationHandedOff(false); setHardcore([]); setSoftcore([]); setSelected(new Set()); setLane("tags");
      setItems([]); setProgress(null); setPrompts([]); setActivated(false);
      await backgroundOperations.refresh();
    } catch (reason) {
      dismissedInspirationOperationIds.delete(inspirationOperationId);
      setError(reason instanceof Error ? reason.message : "Unable to dismiss Explicit inspiration workspace.");
    }
    finally { setPending(false); }
  };

  const generateSelected = async () => {
    if (!selectedConcepts.length || blocked || pending || activeBatch || explicitStartInFlightRef.current) return;
    explicitStartInFlightRef.current = true;
    setPending(true);
    setError("");
    const batch = selectedConcepts.map((item, batchOrdinal) => ({
      error: "",
      id: `explicit-${item.id}`,
      imageUrl: "",
      jobId: null,
      ordinal: batchOrdinal,
      status: "pending" as const,
    }));
    let operationId = "";
    let startAccepted = false;
    try {
      operationId = await startExplicitGenerationBatch({
        batchId: crypto.randomUUID(),
        provider: activeProvider,
        concepts: selectedConcepts,
      });
      if (inspirationOperationId && !inspirationHandedOff) {
        await handoffExplicitInspiration(inspirationOperationId, operationId);
        setInspirationHandedOff(true);
      }
      await backgroundOperations.refresh();
      await beginExplicitGenerationBatch({
        operationId,
        concepts: selectedConcepts,
        provider: activeProvider,
        context,
        onSnapshot: (snapshot) => {
          startAccepted = true;
          setActivated(true);
          setItems(snapshot.items);
          setPrompts(snapshot.prompts);
          setProgress(snapshot);
        },
        onTerminal: (terminalStatus) => {
          if (terminalStatus !== "SUCCEEDED") return;
          setInspirationOperationId(""); setInspirationHandedOff(false);
          setHardcore([]); setSoftcore([]); setSelected(new Set()); setPrompts([]);
          setItems([]); setProgress(null); setActivated(false); setAccordionOpen(false);
          setLane("tags"); setTags(""); setEnhancedTags(""); setImageCount(1);
          setInspirationTierMode("both"); setInspirationCount(10);
          generationRef.current?.reset();
        },
      });
    } catch (reason) {
      if (reason instanceof ExplicitBatchCancelledError) {
        setError(""); setStoppedOperationId(operationId);
        return;
      }
      const message = reason instanceof Error ? reason.message : "Explicit generation failed";
      if (!startAccepted) {
        setItems([]);
        setProgress(null);
        setActivated(false);
      }
      if (operationId) {
        try {
          await updateExplicitGenerationBatch(operationId, {
            current: 0,
            total: batch.length,
            stage: "FAILED",
            message,
            metadata: {
              completedIdeas: 0,
              currentIdeaIndex: 0,
              failedIdeas: 0,
              items: batch,
              orchestrationFailure: true,
              phase: "complete",
              prompts: [],
              totalIdeas: batch.length,
            },
            terminalStatus: "FAILED",
          });
        } catch {
          // Preserve the original orchestration failure for the operator.
        }
      }
      setError(message);
    } finally {
      explicitStartInFlightRef.current = false;
      setPending(false);
      void backgroundOperations.refresh();
    }
  };

  const stopGeneration = async () => {
    if (!activeBatch || stopping) return;
    setStopping(true); setStopConfirmation(false); setError("");
    try {
      await backgroundOperations.cancel(activeBatch.operationId);
      setStoppedOperationId(activeBatch.operationId); setPending(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to stop generation.");
    } finally { setStopping(false); }
  };

  const retryFailed = async () => {
    if (!partialBatch || retryingFailed) return;
    setRetryingFailed(true); setError("");
    try {
      await retryFailedExplicitGenerationBatch(partialBatch.operationId);
      await backgroundOperations.refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to retry failed Explicit items.");
    } finally {
      setRetryingFailed(false);
    }
  };

  const resetStoppedWorkspace = async () => {
    if (!stoppedOperationId || stopping) return;
    setStopping(true); setError("");
    try {
      await resetExplicitGenerationBatch(stoppedOperationId);
      setStoppedOperationId(""); setItems([]); setProgress(null); setPrompts([]);
      setSelected(new Set()); setActivated(false); setPending(false); setLane("tags");
      generationRef.current?.reset();
      await backgroundOperations.refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to reset Content Studio.");
    } finally { setStopping(false); }
  };

  const renderTier = (tier: ExplicitTier, concepts: string[], title: string, description: string) => {
    if (!concepts.length) return null;
    const tierItems = concepts.map((concept, index) => ({
      id: conceptId(tier, index),
      concept,
    }));
    const selectedInTier = tierItems.filter((item) => selected.has(item.id)).length;
    const allTierSelected = selectedInTier === tierItems.length;
    return (
      <section aria-label={title} className={`explicit-content__tier explicit-content__tier--${tier}`}>
        <header className="explicit-content__tier-header">
          <div>
            <h3>{title}</h3>
            <p>{description}</p>
          </div>
          <label className="explicit-content__select-all">
            <input
              checked={allTierSelected}
              ref={(input) => {
                if (input) input.indeterminate = selectedInTier > 0 && !allTierSelected;
              }}
              onChange={() => selectTier(tier, !allTierSelected)}
              type="checkbox"
            />
            <span>Select all {tier} ({selectedInTier}/{tierItems.length})</span>
          </label>
        </header>
        <div className="explicit-content__concepts">
          {tierItems.map((item) => (
            <label key={item.id} className={`explicit-content__concept explicit-content__concept--${tier}`}>
              <input
                checked={selected.has(item.id)}
                onChange={() => toggleSelected(item.id)}
                type="checkbox"
              />
              <span>
                <em className={`explicit-content__badge explicit-content__badge--${tier}`}>
                  {tier === "hardcore" ? "Hardcore" : "Softcore"}
                </em>
                {item.concept}
              </span>
            </label>
          ))}
        </div>
      </section>
    );
  };

  return (
    <details
      className="creative-studio explicit-content-accordion"
      onToggle={(event) => setAccordionOpen(event.currentTarget.open)}
      open={accordionOpen}
    >
      <summary>
        <span>🔞 Explicit Content</span>
        <small>Create from tags or generate mixed hardcore + softcore PPV concepts.</small>
      </summary>
      <section aria-label="Explicit Content" className="creative-studio__content explicit-content">
      <header>
        <p className="inspire-workspace__eyebrow">Separate premium workflow</p>
        <h2>Explicit Content</h2>
        <p>Create with explicit tags or ask Grok for configurable Softcore and Hardcore concepts.</p>
      </header>
      <div className="explicit-content__inspiration-controls" aria-label="Inspire Me settings">
        <fieldset><legend>Content Level</legend><div className="explicit-content__segments">
          {(["softcore", "hardcore", "both"] as const).map((tierMode) => <button aria-pressed={inspirationTierMode === tierMode} disabled={lane === "inspire"} key={tierMode} onClick={() => setInspirationTierMode(tierMode)} type="button">{tierMode[0]!.toUpperCase() + tierMode.slice(1)}</button>)}
        </div></fieldset>
        <label><span>Number of Ideas</span><select disabled={lane === "inspire"} onChange={(event) => setInspirationCount(Number(event.target.value))} value={inspirationCount}>{EXPLICIT_IDEA_COUNTS.map((count) => <option key={count} value={count}>{count}</option>)}</select></label>
      </div>
      <div className="explicit-content__tabs">
        {lane === "tags" ? <button
          onClick={() => {
            setLane("inspire");
            if (!hasConcepts && !pending) void inspire();
          }}
          type="button"
        >Inspire Me</button> : <button onClick={() => setLane("tags")} type="button">Back to Tags</button>}
      </div>

      {lane === "tags" ? (
        <div className="explicit-content__lane creative-director-tools creative-director-tools__group">
          <label><span>Explicit Tags</span><textarea onChange={(event) => setTags(event.target.value)} rows={4} value={tags} /></label>
          <button disabled={pending || !tags.trim()} onClick={() => void enhance()} type="button">✨ Enhance Tags</button>
          <label><span>Enhanced Tags</span><textarea onChange={(event) => setEnhancedTags(event.target.value)} rows={6} value={enhancedTags} /></label>
        </div>
      ) : (
        <div className="explicit-content__lane creative-director-tools creative-director-tools__group">
          {pending && !hasConcepts && <p className="creative-director-tools__status">{inspirationStatus}</p>}
          {hasConcepts && (
            <>
              <div className="explicit-content__selection-bar">
                <label className="explicit-content__select-all">
                  <input
                    checked={allSelected}
                    ref={(input) => { if (input) input.indeterminate = selected.size > 0 && !allSelected; }}
                    onChange={() => setSelected(allSelected ? new Set() : new Set(conceptItems.map((item) => item.id)))}
                    type="checkbox"
                  />
                  <span>Select All ({selected.size} selected)</span>
                </label>
                <button onClick={() => setSelected(new Set())} type="button">Clear Selection</button>
                <button disabled={pending || backgroundOperations.active.some((operation) => operation.operationType === "content_studio_explicit_batch")} onClick={() => void startOverInspiration()} type="button">Start Over</button>
              </div>
              {renderTier(
                "hardcore",
                hardcore,
                "🔥 Hardcore",
                "Direct sexual acts and genital display for high-ticket PPV unlocks.",
              )}
              {renderTier(
                "softcore",
                softcore,
                "💋 Softcore",
                "Sexy teasing, topless, lingerie, and erotic poses without hardcore acts.",
              )}
              <button disabled={blocked || pending || Boolean(activeBatch) || selected.size === 0} onClick={() => void generateSelected()} type="button">
                🚀 Enhance &amp; Generate ({selected.size})
              </button>
            </>
          )}
          {inspirationOperation?.status === "FAILED" && <button onClick={() => { void backgroundOperations.retry(inspirationOperation.operationId).then(backgroundOperations.refresh); }} type="button">Retry Inspiration</button>}
        </div>
      )}

      {lane === "tags" && (
        <>
          <section
            aria-label="Explicit Generation Settings"
            className="explicit-content__settings creative-configuration prompt-workshop"
          >
            <h3>Generation Settings</h3>
            <label><span>Image Count</span><input aria-label="Explicit Image Count" max={12} min={1} onChange={(event) => setImageCount(Number(event.target.value))} type="number" value={imageCount} /></label>
            <label><span>Provider</span><select aria-label="Explicit Provider" onChange={(event) => setProvider(event.target.value)} value={activeProvider}>
              {configuration?.providers.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select></label>
            <details className="creative-configuration__advanced">
              <summary>Advanced Settings</summary>
              <p>Image count controls the number of images generated from this tag request.</p>
            </details>
          </section>
          <button disabled={blocked || pending || !effectiveInput} onClick={() => void generateTags()} type="button">🖼 Generate Images</button>
          <details className="explicit-content__preview">
            <summary>Prompt Preview</summary>
            {prompts.length ? prompts.map((prompt, index) => <pre key={`${index}-${prompt}`}>{prompt}</pre>) : <p>Final explicit prompts will appear here after construction.</p>}
          </details>
        </>
      )}
      {(pending || error) && <p className={error ? "generation-live__error" : "creative-director-tools__status"}>{error || "Working…"}</p>}
      {configurationError && <p className="generation-live__error">{configurationError}</p>}
      {!activeBatch && partialBatch && Number(partialBatch.metadata.failedIdeas || 0) > 0 && (
        <div className="explicit-content__partial-retry" role="status">
          <span>{Number(partialBatch.metadata.completedIdeas || 0)} completed · {Number(partialBatch.metadata.failedIdeas || 0)} failed</span>
          <button disabled={retryingFailed} onClick={() => void retryFailed()} type="button">
            {retryingFailed ? `Retrying ${Number(partialBatch.metadata.failedIdeas || 0)} failed items...` : "Retry Failed"}
          </button>
        </div>
      )}
      {stoppedOperationId && !activeBatch && <div className="content-studio-stopped" role="status"><strong>Generation stopped.</strong><span>Completed images were kept. Remaining images will not be generated.</span><button disabled={stopping} onClick={() => void resetStoppedWorkspace()} type="button">{stopping ? "Resetting..." : "Reset Studio"}</button></div>}
      <div className={activated ? "workflow-live-preview workflow-live-preview--creative" : "workflow-controller"}>
        {activated && <h3>Explicit Live Generation</h3>}
        <GenerationWorkflowSections
          context={context}
          disabled={blocked}
          onPlannerBatchItemChange={(id, changes) => setItems((current) => updatePlannerBatchItems(current, id, changes))}
          onRunStart={() => setActivated(true)}
          onReconnect={() => {
            setActivated(true);
            setAccordionOpen(true);
          }}
          onStartNewGeneration={() => {
            setItems([]);
            setProgress(null);
            setPending(false);
            setError("");
            setActivated(false);
            onStartNewGeneration?.();
          }}
          plannerBatchItems={items}
          plannerBatchProgress={progress}
          plannerBatchRunning={pending}
          reconnectOrigins={EXPLICIT_RECONNECT_ORIGINS}
          request={{
            creativeMode: "explicit",
            lane: "explicit",
            promptBatch: [],
            promptCount: lane === "tags" ? imageCount : Math.max(1, selected.size),
            promptSource: effectiveInput || "Explicit inspiration",
            promptSourceLabel: "Enhanced Explicit Tags",
            provider: activeProvider,
          }}
          ref={generationRef}
          runtimeStatusAction={activeBatch ? <button className="content-studio-stop-control__button" disabled={stopping || activeBatch.status === "CANCEL_REQUESTED"} onClick={() => setStopConfirmation(true)} type="button">{stopping || activeBatch.status === "CANCEL_REQUESTED" ? "Stopping..." : "Stop Generation"}</button> : undefined}
          workflow="manual"
        />
      </div>
      {stopConfirmation && activeBatch && <div className="content-studio-stop-dialog" role="presentation"><div aria-labelledby="stop-generation-title" aria-modal="true" role="dialog"><h2 id="stop-generation-title">Stop this generation?</h2><p>Completed images will be kept. Remaining unsubmitted images will not be generated.</p><footer><button disabled={stopping} onClick={() => setStopConfirmation(false)} type="button">Keep Generating</button><button className="content-studio-stop-control__button" disabled={stopping} onClick={() => void stopGeneration()} type="button">Stop Generation</button></footer></div></div>}
      </section>
    </details>
  );
}
