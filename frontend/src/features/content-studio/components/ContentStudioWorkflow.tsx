import { useCallback, useEffect, useRef, useState } from "react";

import { ActiveReferenceSection } from "./ActiveReferenceSection";
import { createPromptPreview, enhanceCreativeTags } from "../../../infrastructure/api/contentStudioApi";
import { CanonicalPromptPlannerSection, type CanonicalPromptPlannerHandle } from "./CanonicalPromptPlannerSection";
import { CreativeConfigurationSection } from "./CreativeConfigurationSection";
import { CreativeDirectorToolsSection, type CreativeDirectorToolsHandle } from "./CreativeDirectorToolsSection";
import { ManualPromptSection } from "./ManualPromptSection";
import {
  GenerationWorkflowSections,
  type GenerationWorkflowHandle,
  type PlannerBatchProgress,
} from "./GenerationWorkflowSections";
import { PromptWorkshopSection } from "./PromptWorkshopSection";
import { ExplicitContentSection } from "./ExplicitContentSection";
import type { ContentStudioContext } from "../types/contentStudioContext";
import type {
  CreativeToolInputs,
  PromptSource,
} from "../types/contentStudioCreativeTools";
import { type PlannerBatchItem, updatePlannerBatchItems } from "../types/plannerBatch";
import type { CanonicalPlannerItem } from "../types/promptPlanner";

type ContentStudioWorkflowProps = {
  context: ContentStudioContext | null;
  error: string;
  loading: boolean;
};

const EMPTY_CREATIVE_INPUTS: CreativeToolInputs = {
  creativeTags: "",
  enhancedExplicitTags: "",
  enhancedTags: "",
  explicitTags: "",
};

function enhancedPromptInput(originalTags: string, enhancedTags: string) {
  return (
    `[ORIGINAL USER TAGS — mandatory: ${originalTags.trim().replaceAll("\n", ", ")}] `
    + `[ENHANCED SUGGESTIONS — vary any wardrobe detail not present in ORIGINAL USER TAGS: ${enhancedTags.trim().replaceAll("\n", ", ")}]`
  );
}

function selectedPromptInput(source: PromptSource, inputs: CreativeToolInputs, manualPrompt: string) {
  const manual = manualPrompt.trim();
  if (manual) return manual;
  if (source === "Enhanced Tags") {
    const enhanced = inputs.enhancedTags.trim();
    if (!enhanced) return "";
    return enhancedPromptInput(inputs.creativeTags, enhanced);
  }
  if (source === "Enhanced Explicit Tags") return inputs.enhancedExplicitTags.trim();
  if (source === "Prompt Workshop") return manual;
  return inputs.creativeTags.trim();
}

export function ContentStudioWorkflow({ context, error, loading }: ContentStudioWorkflowProps) {
  const plannerRef = useRef<CanonicalPromptPlannerHandle>(null);
  const creativeToolsRef = useRef<CreativeDirectorToolsHandle>(null);
  const generationRef = useRef<GenerationWorkflowHandle>(null);
  const inspirationRef = useRef<GenerationWorkflowHandle>(null);
  const generationStartedIdeaId = useRef<string | null>(null);
  const plannerBatchInFlight = useRef(false);
  const manualWorkflowInFlight = useRef(false);
  const queuedGenerationResolver = useRef<((succeeded: boolean) => void) | null>(null);
  const creativeStudioRef = useRef<HTMLDetailsElement>(null);
  const [promptCount, setPromptCount] = useState<number | null>(null);
  const [creativeMode, setCreativeMode] = useState<string | null>(null);
  const [creativeInputs, setCreativeInputs] = useState<CreativeToolInputs>(EMPTY_CREATIVE_INPUTS);
  const [promptSource, setPromptSource] = useState<PromptSource>("Original Tags");
  const [manualPrompt, setManualPrompt] = useState("");
  const [provider, setProvider] = useState<string | null>(null);
  const [, setWorkshopBatch] = useState({ prompts: [] as string[], source: "" });
  const [plannerBatchItems, setPlannerBatchItems] = useState<PlannerBatchItem[]>([]);
  const [plannerBatchProgress, setPlannerBatchProgress] = useState<PlannerBatchProgress | null>(null);
  const [plannerBatchRunning, setPlannerBatchRunning] = useState(false);
  const [queuedIdeaGeneration, setQueuedIdeaGeneration] = useState<string | null>(null);
  const [creativeStudioOpen, setCreativeStudioOpen] = useState(false);
  const [inspirationPending, setInspirationPending] = useState(false);
  const [inspirationActivated, setInspirationActivated] = useState(false);
  const [manualGenerationActivated, setManualGenerationActivated] = useState(false);
  const [manualWorkflowPending, setManualWorkflowPending] = useState(false);
  const [manualWorkflowError, setManualWorkflowError] = useState("");
  const [activePlannerGeneration, setActivePlannerGeneration] = useState<{
    item: CanonicalPlannerItem;
    enhancedResult: string;
  } | null>(null);
  const blocked = Boolean(error) || context?.status === "profile_missing";
  const referenceMissing = context?.status === "reference_missing";
  const effectivePromptInput = activePlannerGeneration
    ? enhancedPromptInput(
        activePlannerGeneration.item.fullText,
        activePlannerGeneration.enhancedResult,
      )
    : selectedPromptInput(promptSource, creativeInputs, manualPrompt);
  const authoringDisabled = Boolean(referenceMissing) || promptCount === null;
  const previewDisabled = authoringDisabled || creativeMode === null || !effectivePromptInput;
  const generationDisabled = previewDisabled || provider === null;
  const ideaGenerationDisabled = authoringDisabled || creativeMode === null || provider === null;
  const updatePlannerBatchItem = useCallback((id: string, changes: Partial<PlannerBatchItem>) => {
    setPlannerBatchItems((items) => updatePlannerBatchItems(items, id, changes));
  }, []);
  const queueEnhancedGeneration = useCallback((item: CanonicalPlannerItem, tags: string) => new Promise<boolean>((resolve) => {
    queuedGenerationResolver.current = resolve;
    setActivePlannerGeneration({ enhancedResult: tags, item });
    setCreativeInputs((current) => ({ ...current, enhancedTags: tags }));
    setPromptSource("Enhanced Tags");
    setQueuedIdeaGeneration(item.id);
  }), []);
  const enhanceAndGenerateSelected = useCallback(async (ideas: CanonicalPlannerItem[]) => {
    if (plannerBatchInFlight.current || ideas.length === 0) return;
    plannerBatchInFlight.current = true;
    setPlannerBatchRunning(true);
    setPlannerBatchItems(ideas.map((idea, ordinal) => ({
      error: "",
      id: idea.id,
      imageUrl: "",
      jobId: null,
      ordinal,
      status: "pending",
    })));
    let completedIdeas = 0;
    let failedIdeas = 0;
    setPlannerBatchProgress({
      totalIdeas: ideas.length,
      currentIdeaIndex: 0,
      completedIdeas,
      failedIdeas,
      phase: "preparing",
    });
    try {
      for (const [index, idea] of ideas.entries()) {
        setPlannerBatchItems((items) => items.map((item) => (
          item.id === idea.id ? { ...item, status: "enhancing" } : item
        )));
        setPlannerBatchProgress({
          totalIdeas: ideas.length,
          currentIdeaIndex: index + 1,
          completedIdeas,
          failedIdeas,
          phase: "preparing",
        });
        const tags = await creativeToolsRef.current?.enhanceIdea(idea);
        if (!tags) {
          failedIdeas += 1;
          setPlannerBatchItems((items) => items.map((item) => (
            item.id === idea.id ? { ...item, error: "Enhancement failed", status: "failed" } : item
          )));
          continue;
        }
        setPlannerBatchProgress({
          totalIdeas: ideas.length,
          currentIdeaIndex: index + 1,
          completedIdeas,
          failedIdeas,
          phase: "generating",
        });
        setPlannerBatchItems((items) => items.map((item) => (
          item.id === idea.id ? { ...item, status: "submitting" } : item
        )));
        const succeeded = await queueEnhancedGeneration(idea, tags);
        if (succeeded) completedIdeas += 1;
        else failedIdeas += 1;
      }
    } finally {
      plannerBatchInFlight.current = false;
      setPlannerBatchRunning(false);
      setPlannerBatchProgress({
        totalIdeas: ideas.length,
        currentIdeaIndex: ideas.length,
        completedIdeas,
        failedIdeas,
        phase: "complete",
      });
    }
  }, [queueEnhancedGeneration]);

  useEffect(() => {
    if (!queuedIdeaGeneration || generationDisabled || generationStartedIdeaId.current === queuedIdeaGeneration) return;
    generationStartedIdeaId.current = queuedIdeaGeneration;
    void generationRef.current?.generate({ batchItemId: queuedIdeaGeneration, promptCount: 1 }).then((succeeded) => {
      generationStartedIdeaId.current = null;
      setQueuedIdeaGeneration(null);
      setActivePlannerGeneration(null);
      queuedGenerationResolver.current?.(succeeded);
      queuedGenerationResolver.current = null;
    });
  }, [effectivePromptInput, generationDisabled, queuedIdeaGeneration]);

  const startInspiration = async () => {
    if (inspirationPending || ideaGenerationDisabled) return;
    setInspirationActivated(true);
    setInspirationPending(true);
    try {
      await inspirationRef.current?.inspire();
    } finally {
      setInspirationPending(false);
    }
  };

  const createManualImages = async (creativeConcept: string) => {
    if (manualWorkflowInFlight.current || ideaGenerationDisabled || !creativeConcept.trim()) return;
    manualWorkflowInFlight.current = true;
    setManualGenerationActivated(true);
    setManualWorkflowPending(true);
    setManualWorkflowError("");
    try {
      const enhancedTags = await enhanceCreativeTags(
        creativeConcept,
        false,
        undefined,
        { origin: "manual_creative_concept" },
      );
      const promptInput = enhancedPromptInput(creativeConcept, enhancedTags);
      const preview = await createPromptPreview(
        creativeMode ?? "",
        promptInput,
        promptCount ?? 1,
      );
      const succeeded = await generationRef.current?.generate({
        promptBatch: preview.prompts,
        promptCount: promptCount ?? 1,
        promptSource: promptInput,
        promptSourceLabel: "Enhanced Tags",
      });
      if (succeeded === false) setManualWorkflowError("Image generation did not complete successfully.");
    } catch (reason) {
      setManualWorkflowError(reason instanceof Error ? reason.message : "Creative Studio workflow failed");
    } finally {
      manualWorkflowInFlight.current = false;
      setManualWorkflowPending(false);
    }
  };

  const startNewGeneration = useCallback(() => {
    generationStartedIdeaId.current = null;
    plannerBatchInFlight.current = false;
    manualWorkflowInFlight.current = false;
    queuedGenerationResolver.current?.(false);
    queuedGenerationResolver.current = null;
    setPlannerBatchItems([]);
    setPlannerBatchProgress(null);
    setPlannerBatchRunning(false);
    setQueuedIdeaGeneration(null);
    setActivePlannerGeneration(null);
    setManualGenerationActivated(false);
    setManualWorkflowPending(false);
    setManualWorkflowError("");
    setCreativeStudioOpen(true);
    window.requestAnimationFrame(() => {
      creativeStudioRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }, []);

  return (
    <div className="content-studio__workflow">
      {blocked && <ActiveReferenceSection context={context} error={error} loading={loading} />}
      {context?.status === "profile_missing" && (
        <p className="content-studio__blocking-message" role="alert">
          Creator Profile required before using Content Studio.
        </p>
      )}
      {loading && <p className="content-studio__loading">Loading Content Studio…</p>}
      {!loading && !blocked && (
        <>
          <section aria-label="Inspire Me Workspace" className="inspire-workspace">
            <div className="inspire-workspace__intro">
              <p className="inspire-workspace__eyebrow">Primary workflow</p>
              <h2>✨ Inspire Me</h2>
              <p>
                Let Creator_OS automatically create today&apos;s best content for Ava using
                Creator Intelligence and Creative Intelligence.
              </p>
              <button
                disabled={ideaGenerationDisabled || inspirationPending}
                onClick={() => void startInspiration()}
                type="button"
              >
                {inspirationPending ? "Inspiring…" : "✨ Inspire Me"}
              </button>
            </div>
            <div className={inspirationActivated
              ? "workflow-live-preview workflow-live-preview--inspire"
              : "workflow-controller"}>
              {inspirationActivated && <h3>Inspire Me Status</h3>}
              {inspirationActivated && <h3>Inspire Me Live Preview</h3>}
              {context && (
                <GenerationWorkflowSections
                  context={context}
                  disabled={ideaGenerationDisabled}
                  onRunStart={() => setInspirationActivated(true)}
                  request={{
                    creativeMode: creativeMode ?? "",
                    promptBatch: [],
                    promptCount: 6,
                    promptSource: "",
                    promptSourceLabel: "Original Tags",
                    provider: provider ?? "",
                  }}
                  ref={inspirationRef}
                  workflow="autonomous"
                />
              )}
            </div>
          </section>

          <details
            className="creative-studio"
            onToggle={(event) => setCreativeStudioOpen(event.currentTarget.open)}
            open={creativeStudioOpen}
            ref={creativeStudioRef}
          >
            <summary>
              <span>🎨 Creative Studio</span>
              <small>Manual creative control, prompt planning, and advanced generation.</small>
            </summary>
            <div className="creative-studio__content">
              <ActiveReferenceSection context={context} error={error} loading={loading} />
              {referenceMissing && (
                <p className="content-studio__reference-warning">
                  Select an active Reference Image before creating premium work.
                </p>
              )}
              <CreativeDirectorToolsSection
                disabled={authoringDisabled}
                creatingImages={manualWorkflowPending}
                onInputsChange={setCreativeInputs}
                onCreateImages={createManualImages}
                onPromptSourceChange={setPromptSource}
                planner={(
                  <CanonicalPromptPlannerSection
                    disabled={false}
                    generateDisabled={ideaGenerationDisabled}
                    generationProgress={plannerBatchRunning && plannerBatchProgress ? {
                      current: plannerBatchProgress.currentIdeaIndex,
                      total: plannerBatchProgress.totalIdeas,
                    } : null}
                    onEnhanceAndGenerateIdeas={enhanceAndGenerateSelected}
                    processing={plannerBatchRunning}
                    ref={plannerRef}
                  />
                )}
                promptCount={promptCount ?? 1}
                ref={creativeToolsRef}
              />
              <CreativeConfigurationSection
                onCreativeModeChange={setCreativeMode}
                onPromptCountChange={setPromptCount}
                onProviderChange={setProvider}
              />
              <PromptWorkshopSection
                disabled={authoringDisabled}
                onSelectPromptSource={() => setPromptSource("Prompt Workshop")}
                onStoreBatch={(prompts, source) => {
                  setWorkshopBatch({ prompts, source });
                  setManualPrompt(prompts[0] ?? "");
                }}
                onUsePrompt={setManualPrompt}
                promptCount={promptCount ?? 1}
              />
              <ManualPromptSection
                disabled={authoringDisabled}
                onChange={setManualPrompt}
                value={manualPrompt}
              />
              <div className={manualGenerationActivated
                ? "workflow-live-preview workflow-live-preview--creative"
                : "workflow-controller"}>
                {manualGenerationActivated && <h3>Creative Studio Status</h3>}
                {manualGenerationActivated && manualWorkflowPending && (
                  <p className="creative-director-tools__status">Creating Images...</p>
                )}
                {manualGenerationActivated && manualWorkflowError && (
                  <p className="generation-live__error" role="alert">{manualWorkflowError}</p>
                )}
                {manualGenerationActivated && <h3>Creative Studio Live Preview</h3>}
                {context && (
                  <GenerationWorkflowSections
                    context={context}
                    disabled={generationDisabled}
                    onManualGenerationStart={() => setPlannerBatchProgress(null)}
                    onRunStart={() => setManualGenerationActivated(true)}
                    onPlannerBatchItemChange={updatePlannerBatchItem}
                    onStartNewGeneration={startNewGeneration}
                    plannerBatchProgress={plannerBatchProgress}
                    plannerBatchItems={plannerBatchItems}
                    plannerBatchRunning={plannerBatchRunning}
                    request={{
                      creativeMode: creativeMode ?? "",
                      promptBatch: [],
                      promptCount: promptCount ?? 1,
                      promptSource: effectivePromptInput,
                      promptSourceLabel: manualPrompt.trim() ? "Manual Prompt" : promptSource,
                      provider: provider ?? "",
                      ...(activePlannerGeneration ? {
                        origin: activePlannerGeneration.item.origin,
                        plannerLineage: {
                          enhancedResult: activePlannerGeneration.enhancedResult,
                          plannerItemId: activePlannerGeneration.item.id,
                          plannerItemTitle: activePlannerGeneration.item.title,
                          plannerQuestion: activePlannerGeneration.item.plannerQuestion,
                          selectedPlannerItem: activePlannerGeneration.item.fullText,
                        },
                      } : {}),
                    }}
                    ref={generationRef}
                    workflow="manual"
                  />
                )}
              </div>
            </div>
          </details>
          {context && (
            <ExplicitContentSection
              context={context}
              onStartNewGeneration={startNewGeneration}
            />
          )}
        </>
      )}
    </div>
  );
}
