import { useCallback, useRef, useState } from "react";

import { ActiveReferenceSection } from "./ActiveReferenceSection";
import { CanonicalPromptPlannerSection, type CanonicalPromptPlannerHandle } from "./CanonicalPromptPlannerSection";
import { CreativeConfigurationSection } from "./CreativeConfigurationSection";
import { CreativeDirectorToolsSection } from "./CreativeDirectorToolsSection";
import { ManualPromptSection } from "./ManualPromptSection";
import { GenerationWorkflowSections } from "./GenerationWorkflowSections";
import { PromptPreviewSection, type PromptPreviewHandle } from "./PromptPreviewSection";
import { PromptWorkshopSection } from "./PromptWorkshopSection";
import { WorkflowSection } from "./WorkflowSection";
import type { ContentStudioContext } from "../types/contentStudioContext";
import type {
  CreativeToolInputs,
  PromptSource,
} from "../types/contentStudioCreativeTools";

const WORKFLOW_SECTIONS = [
  "Creative Settings",
  "Creative Direction",
  "Prompt Workshop",
  "Manual Prompt",
  "Generate Prompts",
  "Generate Images",
  "Live Generation",
] as const;

const REFERENCE_DEPENDENT_SECTIONS = new Set<string>([
  "Creative Direction",
  "Prompt Workshop",
  "Manual Prompt",
  "Generate Prompts",
  "Generate Images",
  "Live Generation",
]);

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
  surpriseTags: "",
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
  if (source === "Surprise Me Tags") return inputs.surpriseTags.trim();
  if (source === "Enhanced Explicit Tags") return inputs.enhancedExplicitTags.trim();
  if (source === "Prompt Workshop") return manual;
  return inputs.creativeTags.trim();
}

export function ContentStudioWorkflow({ context, error, loading }: ContentStudioWorkflowProps) {
  const plannerRef = useRef<CanonicalPromptPlannerHandle>(null);
  const promptPreviewRef = useRef<PromptPreviewHandle>(null);
  const [promptCount, setPromptCount] = useState<number | null>(null);
  const [creativeMode, setCreativeMode] = useState<string | null>(null);
  const [creativeInputs, setCreativeInputs] = useState<CreativeToolInputs>(EMPTY_CREATIVE_INPUTS);
  const [promptSource, setPromptSource] = useState<PromptSource>("Original Tags");
  const [manualPrompt, setManualPrompt] = useState("");
  const [provider, setProvider] = useState<string | null>(null);
  const [previewPromptBatch, setPreviewPromptBatch] = useState<string[]>([]);
  const [, setWorkshopBatch] = useState({ prompts: [] as string[], source: "" });
  const [ideaEnhancement, setIdeaEnhancement] = useState<{ id: string; text: string } | null>(null);
  const blocked = Boolean(error) || context?.status === "profile_missing";
  const referenceMissing = context?.status === "reference_missing";
  const effectivePromptInput = selectedPromptInput(promptSource, creativeInputs, manualPrompt);
  const authoringDisabled = Boolean(referenceMissing) || promptCount === null;
  const previewDisabled = authoringDisabled || creativeMode === null || !effectivePromptInput;
  const generationDisabled = previewDisabled || provider === null;
  const requestIdeaEnhancement = useCallback((id: string, text: string) => {
    setIdeaEnhancement((current) => current ?? { id, text });
  }, []);
  const completeIdeaEnhancement = useCallback(() => setIdeaEnhancement(null), []);

  return (
    <div className="content-studio__workflow">
      <ActiveReferenceSection context={context} error={error} loading={loading} />
      {context?.status === "profile_missing" && (
        <p className="content-studio__blocking-message" role="alert">
          Creator Profile required before using Content Studio.
        </p>
      )}
      {referenceMissing && (
        <p className="content-studio__reference-warning">
          Select an active Reference Image before creating premium work.
        </p>
      )}
      {!loading && !blocked && (
        <>
          <CreativeConfigurationSection
            onCreativeModeChange={setCreativeMode}
            onPromptCountChange={setPromptCount}
            onProviderChange={setProvider}
          />
          <CreativeDirectorToolsSection
            disabled={authoringDisabled}
            ideaEnhancement={ideaEnhancement}
            onIdeaEnhancementComplete={completeIdeaEnhancement}
            onInputsChange={setCreativeInputs}
            onPremiumEnhanced={(originalTags, enhancedTags) => promptPreviewRef.current?.buildPrompts({
              creativeMode: creativeMode ?? "",
              creativeTags: enhancedPromptInput(originalTags, enhancedTags),
              promptCount: promptCount ?? 1,
            }) ?? Promise.resolve()}
            onPromptSourceChange={setPromptSource}
            planner={(
              <CanonicalPromptPlannerSection
                disabled={false}
                enhancingIdeaId={ideaEnhancement?.id ?? null}
                onEnhanceIdea={requestIdeaEnhancement}
                ref={plannerRef}
              />
            )}
            promptCount={promptCount ?? 1}
          />
          {WORKFLOW_SECTIONS.slice(2).map((title) => title === "Prompt Workshop" ? (
            <PromptWorkshopSection
              disabled={authoringDisabled}
              key={title}
              onSelectPromptSource={() => setPromptSource("Prompt Workshop")}
              onStoreBatch={(prompts, source) => {
                setWorkshopBatch({ prompts, source });
                setManualPrompt(prompts[0] ?? "");
              }}
              onUsePrompt={setManualPrompt}
              promptCount={promptCount ?? 1}
            />
          ) : title === "Manual Prompt" ? (
            <ManualPromptSection
              disabled={authoringDisabled}
              key={title}
              onChange={setManualPrompt}
              value={manualPrompt}
            />
          ) : title === "Generate Prompts" ? (
            <PromptPreviewSection
              disabled={previewDisabled}
              key={title}
              onPromptBatchChange={setPreviewPromptBatch}
              ref={promptPreviewRef}
              signature={{
                creativeMode: creativeMode ?? "",
                creativeTags: effectivePromptInput,
                promptCount: promptCount ?? 1,
              }}
            />
          ) : title === "Generate Images" && context ? (
            <GenerationWorkflowSections
              context={context}
              disabled={generationDisabled}
              key={title}
              onAskAnotherQuestion={() => plannerRef.current?.askAnotherQuestion()}
              onContinueExploring={() => plannerRef.current?.continueExploring()}
              onStartNewSession={() => plannerRef.current?.startNewSession()}
              request={{
                creativeMode: creativeMode ?? "",
                promptBatch: previewPromptBatch,
                promptCount: promptCount ?? 1,
                promptSource: effectivePromptInput,
                promptSourceLabel: manualPrompt.trim() ? "Manual Prompt" : promptSource,
                provider: provider ?? "",
              }}
            />
          ) : title === "Live Generation" ? null : (
            <WorkflowSection
              disabled={referenceMissing && REFERENCE_DEPENDENT_SECTIONS.has(title)}
              key={title}
              title={title}
            />
          ))}
        </>
      )}
    </div>
  );
}
