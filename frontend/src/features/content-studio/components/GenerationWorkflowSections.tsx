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

type GenerationWorkflowSectionsProps = {
  context: ContentStudioContext;
  disabled: boolean;
  onAskAnotherQuestion: () => void;
  onContinueExploring: () => void;
  onManualGenerationStart?: () => void;
  onRunStart?: () => void;
  onPlannerBatchItemChange?: (id: string, changes: Partial<PlannerBatchItem>) => void;
  onStartNewSession: () => void;
  plannerBatchItems?: PlannerBatchItem[];
  plannerBatchProgress?: PlannerBatchProgress | null;
  plannerBatchRunning?: boolean;
  request: Omit<GenerationSubmission, "creatorContext">;
  workflow: "autonomous" | "manual";
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
  inspire: () => Promise<boolean>;
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
  context, disabled, onAskAnotherQuestion, onContinueExploring, onManualGenerationStart, onPlannerBatchItemChange, onRunStart,
  onStartNewSession, plannerBatchItems = [], plannerBatchProgress = null, plannerBatchRunning = false, request, workflow,
}, ref) {
  const [runId, setRunId] = useState("");
  const [generation, setGeneration] = useState<ContentStudioGeneration | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [reservedCount, setReservedCount] = useState(request.promptCount);
  const [autonomousRun, setAutonomousRun] = useState(false);
  const completionRef = useRef<((succeeded: boolean) => void) | null>(null);
  const activeBatchItemIdRef = useRef<string | null>(null);

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
          const batchItemId = activeBatchItemIdRef.current;
          if (batchItemId) {
            onPlannerBatchItemChange?.(batchItemId, { error: message, status: "failed" });
            activeBatchItemIdRef.current = null;
          }
          completionRef.current?.(false);
          completionRef.current = null;
        });
    }, 350);
    return () => { active = false; window.clearTimeout(timer); };
  }, [generation, onPlannerBatchItemChange, runId]);

  async function generate(overrides?: Partial<Omit<GenerationSubmission, "creatorContext">> & { batchItemId?: string }) {
    if (disabled || submitting) return false;
    onRunStart?.();
    setAutonomousRun(false);
    if (!overrides) onManualGenerationStart?.();
    const { batchItemId, ...requestOverrides } = overrides ?? {};
    const generationRequest = { ...request, ...requestOverrides };
    const completion = new Promise<boolean>((resolve) => { completionRef.current = resolve; });
    activeBatchItemIdRef.current = batchItemId ?? null;
    if (batchItemId) onPlannerBatchItemChange?.(batchItemId, { error: "", status: "submitting" });
    setSubmitting(true);
    setReservedCount(generationRequest.promptCount);
    setGeneration(null);
    setError("");
    try {
      const nextRunId = await submitContentStudioGeneration({
        ...generationRequest,
        creatorContext: {
          activeReferenceAssetId: context.activeReference?.assetId ?? null,
          status: context.status,
        },
      });
      setRunId(nextRunId);
      if (batchItemId) onPlannerBatchItemChange?.(batchItemId, { status: "generating" });
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Generation submission failed";
      setError(message);
      if (batchItemId) onPlannerBatchItemChange?.(batchItemId, { error: message, status: "failed" });
      completionRef.current?.(false);
      completionRef.current = null;
    } finally {
      setSubmitting(false);
    }
    return completion;
  }

  async function inspire() {
    if (submitting || !request.provider) return false;
    onRunStart?.();
    const completion = new Promise<boolean>((resolve) => {
      completionRef.current = resolve;
    });
    activeBatchItemIdRef.current = null;
    setAutonomousRun(true);
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
      completionRef.current?.(false);
      completionRef.current = null;
    } finally {
      setSubmitting(false);
    }
    return completion;
  }

  useImperativeHandle(ref, () => ({ generate, inspire }));

  useEffect(() => {
    if (!generation || !TERMINAL.has(generation.status)) return;
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
            jobId: generation.jobId,
            status: "failed",
          });
      activeBatchItemIdRef.current = null;
    }
    completionRef.current?.(generation.status !== "failed");
    completionRef.current = null;
  }, [generation, onPlannerBatchItemChange]);

  const active = submitting || Boolean(runId && (!generation || !TERMINAL.has(generation.status)));
  const inspirationStage = autonomousRun
    ? inspirationProgressStage(generation, submitting, runId)
    : 4;
  const showInspirationProgress = autonomousRun && active && inspirationStage < 4;
  const showLiveGeneration = !autonomousRun || inspirationStage >= 4 || !active;
  const slotCount = runId ? reservedCount : request.promptCount;
  const showNextStep = Boolean(
    generation && NEXT_STEP_STATUSES.has(generation.status) && generation.images.length > 0
    && !autonomousRun
    && (!plannerBatchProgress || plannerBatchProgress.phase === "complete"),
  );
  const aggregateProcessed = plannerBatchProgress
    ? plannerBatchProgress.completedIdeas + plannerBatchProgress.failedIdeas
    : 0;
  const aggregateStatus = plannerBatchProgress
    ? plannerBatchProgress.phase === "complete"
      ? plannerBatchProgress.failedIdeas === 0
        ? "Generation batch completed successfully."
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
          status={plannerBatchProgress ? aggregateStatus : generation?.message || (active ? `Queued Image 1 of ${slotCount}` : "Ready")}
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
            <span>Provider: {generation?.provider ?? request.provider}</span>
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
                    />
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
        {showNextStep && <section aria-label="Next Step" className="generation-next-step">
          <h2>Next Step</h2>
          <p>Continue building on this creative direction or begin a new one.</p>
          <div className="generation-next-step__actions">
            <button onClick={onContinueExploring} type="button"><strong>✨ Continue Exploring</strong><span>Continue using ideas from the current Creative Director response.</span></button>
            <button onClick={onAskAnotherQuestion} type="button"><strong>📝 Ask Another Question</strong><span>Continue brainstorming within the current creative conversation.</span></button>
            <button onClick={onStartNewSession} type="button"><strong>🗑 Start New Session</strong><span>Begin a completely new creative direction.</span></button>
          </div>
        </section>}
      </section>}
    </>
  );
});
