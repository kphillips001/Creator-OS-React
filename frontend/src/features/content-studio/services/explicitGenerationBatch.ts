import {
  activateExplicitGenerationBatch,
  createPromptPreview,
  enhanceCreativeTags,
  getContentStudioGeneration,
  getBackgroundOperation,
  submitContentStudioGeneration,
  updateExplicitGenerationBatch,
} from "../../../infrastructure/api/contentStudioApi";
import type { ContentStudioContext } from "../types/contentStudioContext";
import type { ExplicitGenerationInput } from "../types/generation";
import type { PlannerBatchItem } from "../types/plannerBatch";

export type ExplicitBatchConcept = {
  id: string;
  tier: "hardcore" | "softcore";
  concept: string;
};

export type ExplicitBatchSnapshot = {
  completedIdeas: number;
  currentIdeaIndex: number;
  failedIdeas: number;
  phase: "preparing" | "generating" | "complete";
  totalIdeas: number;
  items: PlannerBatchItem[];
  prompts: string[];
};

const runningBatches = new Map<string, Promise<void>>();
const TERMINAL = new Set(["succeeded", "partial", "failed"]);
const CANCELLED = new Set(["CANCEL_REQUESTED", "CANCELLED"]);

export class ExplicitBatchCancelledError extends Error {
  constructor() { super("Generation stopped. Completed images were preserved."); }
}

function wait(milliseconds: number) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function assertNotCancelled(operationId: string) {
  try {
    const operation = await getBackgroundOperation(operationId);
    if (CANCELLED.has(operation.status)) throw new ExplicitBatchCancelledError();
  } catch (reason) {
    if (reason instanceof ExplicitBatchCancelledError) throw reason;
    // A transient status-read failure must not convert a healthy provider job
    // into a failed batch. The canonical progress endpoint independently
    // rejects every late mutation once cancellation is persisted.
  }
}

async function waitForGeneration(runId: string, operationId: string) {
  for (;;) {
    await assertNotCancelled(operationId);
    const generation = await getContentStudioGeneration(runId);
    await assertNotCancelled(operationId);
    if (TERMINAL.has(generation.status)) return generation;
    await wait(350);
  }
}

function patchItem(items: PlannerBatchItem[], id: string, changes: Partial<PlannerBatchItem>) {
  return items.map((item) => item.id === id ? { ...item, ...changes } : item);
}

async function persist(operationId: string, snapshot: ExplicitBatchSnapshot, terminalStatus?: "SUCCEEDED" | "PARTIAL" | "FAILED") {
  const current = snapshot.completedIdeas + snapshot.failedIdeas;
  const message = snapshot.phase === "complete"
    ? `${current} of ${snapshot.totalIdeas} ideas processed.`
    : snapshot.phase === "generating"
      ? `Generating idea ${snapshot.currentIdeaIndex} of ${snapshot.totalIdeas}...`
      : `Preparing idea ${snapshot.currentIdeaIndex} of ${snapshot.totalIdeas}...`;
  await updateExplicitGenerationBatch(operationId, {
    current,
    total: snapshot.totalIdeas,
    stage: snapshot.phase.toUpperCase(),
    message,
    metadata: snapshot,
    terminalStatus,
  });
}

export function beginExplicitGenerationBatch(args: {
  operationId: string;
  concepts: ExplicitBatchConcept[];
  provider: string;
  context: ContentStudioContext;
  onSnapshot?: (snapshot: ExplicitBatchSnapshot) => void;
  onTerminal?: (status: "SUCCEEDED" | "PARTIAL" | "FAILED") => void;
}) {
  const existing = runningBatches.get(args.operationId);
  if (existing) return existing;

  const promise = (async () => {
    const totalIdeas = args.concepts.length;
    const collectionId = `explicit-collection-${args.concepts.map(({ id }) => id).join("-")}`;
    let snapshot: ExplicitBatchSnapshot = {
      completedIdeas: 0,
      currentIdeaIndex: 1,
      failedIdeas: 0,
      phase: "preparing",
      totalIdeas,
      items: args.concepts.map((concept, ordinal) => ({
        error: "", id: `explicit-${concept.id}`, imageUrl: "", jobId: null, ordinal, status: "pending",
      })),
      prompts: [],
    };
    const publish = async (terminalStatus?: "SUCCEEDED" | "PARTIAL" | "FAILED") => {
      args.onSnapshot?.(snapshot);
      await persist(args.operationId, snapshot, terminalStatus);
    };
    await activateExplicitGenerationBatch(args.operationId);
    await assertNotCancelled(args.operationId);
    await publish();

    for (const [index, selection] of args.concepts.entries()) {
      await assertNotCancelled(args.operationId);
      const item = snapshot.items[index]!;
      snapshot = { ...snapshot, currentIdeaIndex: index + 1, phase: "preparing", items: patchItem(snapshot.items, item.id, { status: "enhancing" }) };
      await publish();
      let enhanced: string;
      try {
        enhanced = (await enhanceCreativeTags(selection.concept, true)).replace(/\s*\n+\s*/g, ", ");
        await assertNotCancelled(args.operationId);
      } catch (reason) {
        if (reason instanceof ExplicitBatchCancelledError) throw reason;
        snapshot = {
          ...snapshot,
          failedIdeas: snapshot.failedIdeas + 1,
          items: patchItem(snapshot.items, item.id, {
            error: reason instanceof Error ? reason.message : "Explicit concept failed",
            failureStage: "enhancement", status: "failed",
          }),
        };
        await publish();
        continue;
      }

      const explicitInput: ExplicitGenerationInput = {
        sourceText: enhanced,
        originalSource: selection.concept,
        sourceType: "selected_inspiration_concept",
        origin: "explicit_inspiration",
        conceptTier: selection.tier,
        requiredSemanticAttributes: {},
        requestedImageCount: 1,
        collectionId,
        lineage: { collectionPromptIndex: index, plannerItemId: item.id, selectedConcept: selection.concept },
      };
      let providerPrompt: string;
      try {
        await assertNotCancelled(args.operationId);
        const preview = await createPromptPreview("explicit", enhanced, 1, undefined, "explicit", explicitInput);
        await assertNotCancelled(args.operationId);
        providerPrompt = preview.prompts[0] ?? "";
        if (!providerPrompt) throw new Error("Explicit prompt planning returned no prompt");
        snapshot = { ...snapshot, prompts: [...snapshot.prompts, providerPrompt] };
      } catch (reason) {
        if (reason instanceof ExplicitBatchCancelledError) throw reason;
        snapshot = {
          ...snapshot,
          failedIdeas: snapshot.failedIdeas + 1,
          items: patchItem(snapshot.items, item.id, {
            error: reason instanceof Error ? reason.message : "Explicit prompt planning failed",
            failureStage: "planning", status: "failed",
          }),
        };
        await publish();
        continue;
      }

      try {
        await assertNotCancelled(args.operationId);
        snapshot = { ...snapshot, phase: "generating", items: patchItem(snapshot.items, item.id, { status: "submitting" }) };
        await publish();
        await assertNotCancelled(args.operationId);
        const tierLabel = selection.tier === "hardcore" ? "Hardcore" : "Softcore";
        const runId = await submitContentStudioGeneration({
          provider: args.provider,
          creativeMode: "explicit", lane: "explicit", promptBatch: [providerPrompt], promptCount: 1,
          promptSource: enhanced, promptSourceLabel: "Enhanced Explicit Tags", origin: "explicit_inspiration",
          creatorContext: { activeReferenceAssetId: args.context.activeReference?.assetId ?? null, status: args.context.status },
          plannerLineage: {
            enhancedResult: enhanced, plannerItemId: item.id,
            plannerItemTitle: `${tierLabel} concept ${index + 1}`,
            plannerQuestion: "Explicit Inspire Me", selectedPlannerItem: selection.concept,
          },
          explicitInput,
        });
        await assertNotCancelled(args.operationId);
        snapshot = { ...snapshot, items: patchItem(snapshot.items, item.id, { jobId: runId, status: "generating" }) };
        await publish();
        const generation = await waitForGeneration(runId, args.operationId);
        await assertNotCancelled(args.operationId);
        const image = generation.images[0];
        if (generation.status === "failed" || !image) throw new Error(generation.message || "Generation failed");
        snapshot = {
          ...snapshot, completedIdeas: snapshot.completedIdeas + 1,
          items: patchItem(snapshot.items, item.id, { error: "", imageUrl: image.url, jobId: generation.jobId ?? runId, status: "completed" }),
        };
      } catch (reason) {
        if (reason instanceof ExplicitBatchCancelledError) throw reason;
        snapshot = {
          ...snapshot, failedIdeas: snapshot.failedIdeas + 1,
          items: patchItem(snapshot.items, item.id, {
            error: reason instanceof Error ? reason.message : "Explicit concept failed",
            failureStage: "generation", status: "failed",
          }),
        };
      }
      await publish();
    }

    await assertNotCancelled(args.operationId);
    snapshot = { ...snapshot, currentIdeaIndex: totalIdeas, phase: "complete" };
    const terminal = snapshot.failedIdeas === 0 ? "SUCCEEDED" : snapshot.completedIdeas > 0 ? "PARTIAL" : "FAILED";
    await publish(terminal);
    args.onTerminal?.(terminal);
  })().finally(() => runningBatches.delete(args.operationId));
  runningBatches.set(args.operationId, promise);
  return promise;
}
