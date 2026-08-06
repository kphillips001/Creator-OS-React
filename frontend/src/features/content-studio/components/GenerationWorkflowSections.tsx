import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type CSSProperties } from "react";

import {
  getContentStudioGeneration,
  submitAutonomousInspiration,
  submitContentStudioGeneration,
} from "../../../infrastructure/api/contentStudioApi";
import type { ContentStudioContext } from "../types/contentStudioContext";
import type { ContentStudioGeneration, GenerationSubmission } from "../types/generation";
import type { PlannerBatchItem } from "../types/plannerBatch";
import { LiveProgressPanel } from "../../../shared/ui/LiveProgressPanel";
import { InspirationProgressPanel } from "./InspirationProgressPanel";
import { RECREATE_RUNTIME_STAGES, type RecreateRuntimeState } from "../types/recreateRuntime";

type GenerationWorkflowSectionsProps = {
  context: ContentStudioContext;
  disabled: boolean;
  onManualGenerationStart?: () => void;
  onRunStart?: () => void;
  onPlannerBatchItemChange?: (id: string, changes: Partial<PlannerBatchItem>) => void;
  onStartNewGeneration?: () => void;
  plannerBatchItems?: PlannerBatchItem[];
  plannerBatchProgress?: PlannerBatchProgress | null;
  plannerBatchRunning?: boolean;
  request: Omit<GenerationSubmission, "creatorContext">;
  workflow: "autonomous" | "manual";
  recreateRuntime?: RecreateRuntimeState | null;
  onRecreateRuntimeChange?: (state: RecreateRuntimeState) => void;
};

export type PlannerBatchProgress = {
  totalIdeas: number;
  currentIdeaIndex: number;
  completedIdeas: number;
  failedIdeas: number;
  phase: "preparing" | "generating" | "complete";
};

export type GenerationWorkflowHandle = {
  generate: (overrides?: Partial<Omit<GenerationSubmission, "creatorContext">> & { batchItemId?: string }) => Promise<boolean>;
  generateWithResult: (overrides?: Partial<Omit<GenerationSubmission, "creatorContext">> & { batchItemId?: string }) => Promise<GenerationAttemptResult>;
  inspire: () => Promise<boolean>;
  reset: () => void;
};

export type GenerationAttemptResult = {
  status: "blocked" | "failed" | "cancelled" | "completed";
  stage: "gate" | "submission" | "provider" | "complete";
  accepted: boolean;
  reason: string;
};

const TERMINAL = new Set(["succeeded", "partial", "failed"]);
const NEXT_STEP_STATUSES = new Set(["succeeded", "partial"]);

export function inspirationProgressStage(
  generation: ContentStudioGeneration | null,
  submitting: boolean,
  runId: string,
): number {
  if (submitting && !runId) return 0;
  if (!generation) return 1;
  if (
    generation.jobId
    || generation.status === "running"
    || TERMINAL.has(generation.status)
  ) return 4;
  if (generation.message.toLowerCase().includes("prompt plan")) return 3;
  if (generation.status === "planning") return 2;
  return 1;
}

export const GenerationWorkflowSections = forwardRef<GenerationWorkflowHandle, GenerationWorkflowSectionsProps>(function GenerationWorkflowSections({
  context, disabled, onManualGenerationStart, onPlannerBatchItemChange, onRunStart,
  onStartNewGeneration, plannerBatchItems = [], plannerBatchProgress = null, plannerBatchRunning = false, request, workflow, recreateRuntime, onRecreateRuntimeChange,
}, ref) {
  const [runId, setRunId] = useState("");
  const [generation, setGeneration] = useState<ContentStudioGeneration | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [reservedCount, setReservedCount] = useState(request.promptCount);
  const [autonomousRun, setAutonomousRun] = useState(false);
  const [activeOrigin, setActiveOrigin] = useState<GenerationSubmission["origin"] | null>(null);
  const completionRef = useRef<((result: GenerationAttemptResult) => void) | null>(null);
  const activeBatchItemIdRef = useRef<string | null>(null);

  function reset() {
    if (completionRef.current && recreateRuntime) onRecreateRuntimeChange?.({ activeStage: recreateRuntime.activeStage, failedStage: recreateRuntime.activeStage, message: "Generation cancelled.", state: "failed" });
    completionRef.current?.({ accepted: Boolean(runId), reason: "Generation cancelled.", stage: runId ? "provider" : "submission", status: "cancelled" });
    completionRef.current = null;
    activeBatchItemIdRef.current = null;
    setRunId("");
    setGeneration(null);
    setSubmitting(false);
    setError("");
    setReservedCount(request.promptCount);
    setAutonomousRun(false);
    setActiveOrigin(null);
  }

  useEffect(() => {
    if (!runId || (generation && TERMINAL.has(generation.status))) return;
    let active = true;
    const timer = window.setTimeout(() => {
      getContentStudioGeneration(runId)
        .then((result) => { if (active) setGeneration(result); })
        .catch((reason: unknown) => {
          if (!active) return;
          const message = reason instanceof Error ? reason.message : "Generation status failed";
          setError(message);
          if (recreateRuntime) onRecreateRuntimeChange?.({ activeStage: 5, failedStage: 5, message: "Generation polling failed.", state: "failed" });
          const batchItemId = activeBatchItemIdRef.current;
          if (batchItemId) {
            onPlannerBatchItemChange?.(batchItemId, {
              error: message,
              failureStage: "generation",
              status: "failed",
            });
            activeBatchItemIdRef.current = null;
          }
          completionRef.current?.({ accepted: true, reason: "Generation polling failed.", stage: "provider", status: "failed" });
          completionRef.current = null;
        });
    }, 350);
    return () => { active = false; window.clearTimeout(timer); };
  }, [generation, onPlannerBatchItemChange, onRecreateRuntimeChange, recreateRuntime, runId]);

  async function generateWithResult(overrides?: Partial<Omit<GenerationSubmission, "creatorContext">> & { batchItemId?: string }): Promise<GenerationAttemptResult> {
    const { batchItemId, ...requestOverrides } = overrides ?? {};
    const generationRequest = { ...request, ...requestOverrides };
    const overrideReady = Boolean(
      overrides
      && Array.isArray(overrides.promptBatch)
      && overrides.promptBatch.some((prompt) => String(prompt).trim())
      && String(overrides.promptSource || "").trim()
      && String(generationRequest.provider || "").trim()
      && String(generationRequest.creativeMode || "").trim()
      && String(generationRequest.promptSourceLabel || "").trim()
      && Number(generationRequest.promptCount) >= 1
      && context.status === "ready"
      && context.activeReference?.assetId != null
    );
    if (submitting) return { accepted: false, reason: "Generation submission is already running.", stage: "gate", status: "blocked" };
    if (disabled && !overrideReady) {
      const result: GenerationAttemptResult = { accepted: false, reason: "Generation submission was blocked because the generation request was incomplete.", stage: "gate", status: "blocked" };
      if (recreateRuntime) onRecreateRuntimeChange?.({ activeStage: 4, failedStage: 4, message: result.reason, state: "failed" });
      return result;
    }
    onRunStart?.();
    setAutonomousRun(false);
    setActiveOrigin(generationRequest.origin ?? null);
    if (!overrides) onManualGenerationStart?.();
    const completion = new Promise<GenerationAttemptResult>((resolve) => { completionRef.current = resolve; });
    activeBatchItemIdRef.current = batchItemId ?? null;
    if (batchItemId) onPlannerBatchItemChange?.(batchItemId, { error: "", status: "submitting" });
    setSubmitting(true);
    setReservedCount(generationRequest.promptCount);
    setGeneration(null);
    setError("");
    try {
      if (recreateRuntime) onRecreateRuntimeChange?.({ activeStage: 4, message: "Submitting generation to provider", state: "running" });
      const nextRunId = await submitContentStudioGeneration({
        ...generationRequest,
        creatorContext: {
          activeReferenceAssetId: context.activeReference?.assetId ?? null,
          status: context.status,
        },
      });
      setRunId(nextRunId);
      if (recreateRuntime) onRecreateRuntimeChange?.({ activeStage: 5, message: "Waiting for provider", state: "running" });
      if (batchItemId) onPlannerBatchItemChange?.(batchItemId, { status: "generating" });
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Generation submission failed";
      setError(message);
      if (recreateRuntime) onRecreateRuntimeChange?.({ activeStage: 4, failedStage: 4, message: "Failed while submitting generation.", state: "failed" });
      if (batchItemId) {
        onPlannerBatchItemChange?.(batchItemId, {
          error: message,
          failureStage: "generation",
          status: "failed",
        });
      }
      completionRef.current?.({ accepted: false, reason: message || "Failed while submitting generation.", stage: "submission", status: "failed" });
      completionRef.current = null;
    } finally {
      setSubmitting(false);
    }
    return completion;
  }

  async function generate(overrides?: Partial<Omit<GenerationSubmission, "creatorContext">> & { batchItemId?: string }) {
    return (await generateWithResult(overrides)).status === "completed";
  }

  async function inspire() {
    if (submitting || !request.provider) return false;
    onRunStart?.();
    const completion = new Promise<GenerationAttemptResult>((resolve) => {
      completionRef.current = resolve;
    });
    activeBatchItemIdRef.current = null;
    setAutonomousRun(true);
    setActiveOrigin(null);
    setSubmitting(true);
    setReservedCount(6);
    setRunId("");
    setGeneration(null);
    setError("");
    try {
      const nextRunId = await submitAutonomousInspiration(request.provider);
      setRunId(nextRunId);
    } catch (reason) {
      setError(reason instanceof Error
        ? reason.message
        : "Autonomous inspiration submission failed");
      completionRef.current?.({ accepted: false, reason: "Autonomous inspiration submission failed.", stage: "submission", status: "failed" });
      completionRef.current = null;
    } finally {
      setSubmitting(false);
    }
    return (await completion).status === "completed";
  }

  useImperativeHandle(ref, () => ({ generate, generateWithResult, inspire, reset }));

  useEffect(() => {
    if (!generation || !TERMINAL.has(generation.status)) return;
    const wasAwaitingCompletion = completionRef.current !== null;
    const batchItemId = activeBatchItemIdRef.current;
    if (batchItemId) {
      const image = generation.images[0];
      onPlannerBatchItemChange?.(batchItemId, generation.status !== "failed" && image
        ? {
            error: "",
            imageUrl: image.url,
            jobId: generation.jobId,
            status: "completed",
          }
        : {
            error: generation.message || "Generation failed",
            failureStage: "generation",
            jobId: generation.jobId,
            status: "failed",
          });
      activeBatchItemIdRef.current = null;
    }
    completionRef.current?.(generation.status === "failed"
      ? { accepted: true, reason: generation.message || "Provider generation failed.", stage: "provider", status: "failed" }
      : { accepted: true, reason: "Generation complete", stage: "complete", status: "completed" });
    if (recreateRuntime && wasAwaitingCompletion) onRecreateRuntimeChange?.(generation.status === "failed"
      ? { activeStage: 5, failedStage: 5, message: generation.message || "Provider generation failed.", state: "failed" }
      : { activeStage: 6, message: "Generation complete", state: "complete" });
    completionRef.current = null;
  }, [generation, onPlannerBatchItemChange, onRecreateRuntimeChange, recreateRuntime]);

  const active = submitting || Boolean(runId && (!generation || !TERMINAL.has(generation.status)));
  const inspirationStage = autonomousRun
    ? inspirationProgressStage(generation, submitting, runId)
    : 4;
  const showInspirationProgress = autonomousRun && active && inspirationStage < 4;
  const showLiveGeneration = !autonomousRun || inspirationStage >= 4 || !active;
  const slotCount = runId ? reservedCount : request.promptCount;
  const singleImageMode = activeOrigin === "recreate_with_ava";
  const generationComplete = plannerBatchProgress
    ? plannerBatchProgress.totalIdeas > 0
      && plannerBatchProgress.completedIdeas === plannerBatchProgress.totalIdeas
    : Boolean(
        generation
        && generation.totalCount > 0
        && generation.completedCount === generation.totalCount,
      );
  const showCompletion = generationComplete && !autonomousRun;
  const aggregateProcessed = plannerBatchProgress
    ? plannerBatchProgress.completedIdeas + plannerBatchProgress.failedIdeas
    : 0;
  const failedBatchItems = plannerBatchItems.filter((item) => item.status === "failed");
  const sharedFailureReason = failedBatchItems.length > 0
    && failedBatchItems.every((item) => item.error === failedBatchItems[0]?.error)
    ? failedBatchItems[0]?.error ?? ""
    : "";
  const sharedFailureStage = failedBatchItems.length > 0
    && failedBatchItems.every((item) => item.failureStage === failedBatchItems[0]?.failureStage)
    ? failedBatchItems[0]?.failureStage
    : undefined;
  const allBatchItemsFailed = Boolean(
    plannerBatchProgress
    && plannerBatchProgress.failedIdeas === plannerBatchProgress.totalIdeas,
  );
  const providerWasContacted = plannerBatchItems.some(
    (item) => Boolean(item.jobId) || item.status === "completed",
  );
  const aggregateStatus = plannerBatchProgress
    ? plannerBatchProgress.phase === "complete"
      ? plannerBatchProgress.failedIdeas === 0
        ? "Generation batch completed successfully."
        : allBatchItemsFailed && sharedFailureStage === "enhancement"
          ? `Enhancement failed for ${plannerBatchProgress.failedIdeas} of ${plannerBatchProgress.totalIdeas} concepts.${sharedFailureReason ? ` ${sharedFailureReason}.` : ""}`
          : allBatchItemsFailed && sharedFailureStage === "planning"
            ? `Prompt planning failed for ${plannerBatchProgress.failedIdeas} concepts.${sharedFailureReason ? ` ${sharedFailureReason}.` : ""}`
            : `Generation batch completed with ${plannerBatchProgress.failedIdeas} failed.`
      : plannerBatchProgress.phase === "preparing"
        ? `Preparing idea ${plannerBatchProgress.currentIdeaIndex} of ${plannerBatchProgress.totalIdeas}...`
        : `Generating idea ${plannerBatchProgress.currentIdeaIndex} of ${plannerBatchProgress.totalIdeas}...`
    : "";
  return (
    <>
      {workflow === "manual" && error && (
        <p className="generation-live__error" role="alert">{error}</p>
      )}
      {workflow === "autonomous" && error && (
        <p className="generation-live__error" role="alert">{error}</p>
      )}
      {showInspirationProgress && (
        <InspirationProgressPanel activeStage={inspirationStage} />
      )}
      {recreateRuntime && <InspirationProgressPanel activeStage={recreateRuntime.state === "complete" ? RECREATE_RUNTIME_STAGES.length : recreateRuntime.activeStage} eyebrow="Recreate With Ava" failedStage={recreateRuntime.failedStage} stages={RECREATE_RUNTIME_STAGES} title="Creative Studio Status" />}
      {recreateRuntime?.state === "failed" && <p className="generation-live__error" role="alert">{recreateRuntime.message}</p>}
      {recreateRuntime && !runId && <section aria-label="Recreate Live Preview" className="workflow-section generation-live"><LiveProgressPanel active={recreateRuntime.state === "running"} progressLabel={`${Math.min(recreateRuntime.activeStage + 1, RECREATE_RUNTIME_STAGES.length)} of ${RECREATE_RUNTIME_STAGES.length} stages`} progressPercent={(recreateRuntime.activeStage + (recreateRuntime.state === "complete" ? 1 : 0)) / RECREATE_RUNTIME_STAGES.length * 100} status={recreateRuntime.message} title="Creative Studio Live Preview" tone={recreateRuntime.state === "failed" ? "failed" : recreateRuntime.state === "complete" ? "complete" : "active"}><div className="generation-live__metrics"><span>Prompt: {recreateRuntime.activeStage >= 3 ? "Canonical planning active" : "Preparing direction"}</span><span>Provider: {request.provider || "Not selected"}</span></div></LiveProgressPanel></section>}
      {showLiveGeneration && (active || generation || plannerBatchProgress) && <section aria-label="Live Generation" className="workflow-section generation-live">
        {!generation && !active && <p>Generated images will appear here as each provider result completes.</p>}
        <LiveProgressPanel
          active={plannerBatchProgress ? plannerBatchRunning : active}
          progressLabel={plannerBatchProgress
            ? `${aggregateProcessed} of ${plannerBatchProgress.totalIdeas} Processed`
            : `${generation?.processedCount ?? 0} of ${generation?.totalCount ?? slotCount} Processed`}
          progressPercent={plannerBatchProgress
            ? aggregateProcessed / Math.max(1, plannerBatchProgress.totalIdeas) * 100
            : generation?.progress ?? 0}
          status={plannerBatchProgress ? aggregateStatus : singleImageMode && active ? "Generating Ava recreation..." : generation?.message || (active ? `Queued Image 1 of ${slotCount}` : "Ready")}
          title="Live Generation"
          tone={plannerBatchProgress
            ? plannerBatchProgress.phase === "complete"
              ? plannerBatchProgress.failedIdeas > 0 ? "failed" : "complete"
              : "active"
            : generation?.status === "failed" ? "failed" : generation && NEXT_STEP_STATUSES.has(generation.status) ? "complete" : "active"}
        >
          <div className="generation-live__metrics">
            <span>Completed: {plannerBatchProgress?.completedIdeas ?? generation?.completedCount ?? 0}</span>
            <span>Failed: {plannerBatchProgress?.failedIdeas ?? generation?.failedCount ?? 0}</span>
            <span>
              Provider: {plannerBatchProgress && !providerWasContacted
                ? `Not contacted (selected: ${request.provider})`
                : generation?.provider ?? request.provider}
            </span>
          </div>
        </LiveProgressPanel>
        {plannerBatchProgress ? (
          <div
            aria-label="Generated image slots"
            className="generation-live__images"
            style={{ "--generation-columns": Math.min(5, plannerBatchProgress.totalIdeas) } as CSSProperties}
          >
            {plannerBatchItems.filter((item) => item.status !== "pending").map((item) => {
              const displayNumber = item.ordinal + 1;
              const completed = item.status === "completed" && Boolean(item.imageUrl);
              return (
                <figure
                  className={completed ? "generation-live__slot generation-live__slot--complete" : "generation-live__slot"}
                  key={item.id}
                >
                  {completed ? (
                    <img
                      alt={`Generated image ${displayNumber} of ${plannerBatchProgress.totalIdeas}`}
                      src={item.imageUrl}
                    />
                  ) : item.status === "failed" ? (
                    <div
                      aria-label={`Generation failed for image ${displayNumber} of ${plannerBatchProgress.totalIdeas}`}
                      className="generation-live__placeholder"
                      role="img"
                      title={item.error}
                    >
                      <span className="generation-live__failure-reason">
                        {sharedFailureReason
                          ? item.failureStage === "enhancement" ? "Enhancement failed" : item.failureStage === "planning" ? "Planning failed" : "Generation failed"
                          : item.error}
                      </span>
                    </div>
                  ) : (
                    <div
                      aria-label={`Waiting for generated image ${displayNumber} of ${plannerBatchProgress.totalIdeas}`}
                      className="generation-live__placeholder"
                      role="img"
                    />
                  )}
                  <figcaption>{displayNumber} of {plannerBatchProgress.totalIdeas}</figcaption>
                </figure>
              );
            })}
          </div>
        ) : (
          <div
            aria-label="Generated image slots"
            className="generation-live__images"
            style={{ "--generation-columns": Math.min(5, slotCount) } as CSSProperties}
          >
            {Array.from({ length: slotCount }, (_, index) => {
              const image = generation?.images.find((candidate) => candidate.index === index);
              return (
                <figure className={image ? "generation-live__slot generation-live__slot--complete" : "generation-live__slot"} key={index}>
                  {image ? (
                    <img alt={`Generated image ${index + 1} of ${slotCount}`} src={image.url} />
                  ) : (
                    <div
                      aria-label={`Waiting for generated image ${index + 1} of ${slotCount}`}
                      className="generation-live__placeholder"
                      role="img"
                    />
                  )}
                  <figcaption>{index + 1} of {slotCount}</figcaption>
                </figure>
              );
            })}
          </div>
        )}
        {showCompletion && (
          <section aria-label="Generation Complete" className="generation-complete">
            <h2>✓ Generation Complete</h2>
            <button
              className="generation-complete__button"
              onClick={() => {
                reset();
                onStartNewGeneration?.();
              }}
              type="button"
            >
              Start New Generation
            </button>
          </section>
        )}
      </section>}
    </>
  );
});
