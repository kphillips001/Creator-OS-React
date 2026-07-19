import { useEffect, useState, type CSSProperties } from "react";

import { getContentStudioGeneration, submitContentStudioGeneration } from "../../../infrastructure/api/contentStudioApi";
import type { ContentStudioContext } from "../types/contentStudioContext";
import type { ContentStudioGeneration, GenerationSubmission } from "../types/generation";

type GenerationWorkflowSectionsProps = {
  context: ContentStudioContext;
  disabled: boolean;
  request: Omit<GenerationSubmission, "creatorContext">;
};

const TERMINAL = new Set(["succeeded", "partial", "failed"]);

export function GenerationWorkflowSections({ context, disabled, request }: GenerationWorkflowSectionsProps) {
  const [runId, setRunId] = useState("");
  const [generation, setGeneration] = useState<ContentStudioGeneration | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [reservedCount, setReservedCount] = useState(request.promptCount);

  useEffect(() => {
    if (!runId || (generation && TERMINAL.has(generation.status))) return;
    let active = true;
    const timer = window.setTimeout(() => {
      getContentStudioGeneration(runId)
        .then((result) => { if (active) setGeneration(result); })
        .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Generation status failed"); });
    }, 350);
    return () => { active = false; window.clearTimeout(timer); };
  }, [generation, runId]);

  async function generate() {
    if (disabled || submitting) return;
    setSubmitting(true);
    setReservedCount(request.promptCount);
    setGeneration(null);
    setError("");
    try {
      const nextRunId = await submitContentStudioGeneration({
        ...request,
        creatorContext: {
          activeReferenceAssetId: context.activeReference?.assetId ?? null,
          status: context.status,
        },
      });
      setRunId(nextRunId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Generation submission failed");
    } finally {
      setSubmitting(false);
    }
  }

  const active = submitting || Boolean(runId && (!generation || !TERMINAL.has(generation.status)));
  const slotCount = runId ? reservedCount : request.promptCount;
  return (
    <>
      <section aria-disabled={disabled || undefined} aria-label="Generate Images" className="workflow-section generate-images">
        <button disabled={disabled || active} onClick={() => void generate()} type="button">
          {active ? "Generating Images..." : "Generate Premium Images"}
        </button>
        {error && <p className="generation-live__error" role="alert">{error}</p>}
      </section>
      {(active || generation) && <section aria-label="Live Generation" className="workflow-section generation-live">
        <h2>Live Generation</h2>
        {!generation && !active && <p>Generated images will appear here as each provider result completes.</p>}
        {active && !generation && <p role="status">Queued Image 1 of {request.promptCount}</p>}
        {generation && (
          <p className={`generation-live__status generation-live__status--${generation.status}`} role="status">
            {generation.message}
          </p>
        )}
        <progress aria-label="Generation progress" max="100" value={generation?.progress ?? 0} />
        <div className="generation-live__metrics">
          <span>Completed: {generation?.completedCount ?? 0}</span>
          <span>Failed: {generation?.failedCount ?? 0}</span>
          <span>Processed: {generation?.processedCount ?? 0} / {generation?.totalCount ?? slotCount}</span>
          <span>Provider: {generation?.provider ?? request.provider}</span>
        </div>
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
      </section>}
    </>
  );
}
