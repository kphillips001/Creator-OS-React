import { useState } from "react";

import { ActiveReferenceSection } from "./ActiveReferenceSection";
import { CanonicalPromptPlannerSection } from "./CanonicalPromptPlannerSection";
import { CreativeConfigurationSection } from "./CreativeConfigurationSection";
import { CreativeDirectorToolsSection } from "./CreativeDirectorToolsSection";
import { ManualPromptSection } from "./ManualPromptSection";
import { GenerationWorkflowSections } from "./GenerationWorkflowSections";
import { PromptPreviewSection } from "./PromptPreviewSection";
import { PromptWorkshopSection } from "./PromptWorkshopSection";
import { WorkflowSection } from "./WorkflowSection";
import type { ContentStudioContext } from "../types/contentStudioContext";
import type {
  CreativeToolInputs,
  PromptSource,
} from "../types/contentStudioCreativeTools";

const WORKFLOW_SECTIONS = [
  "Premium Creative Mode / Prompt Count / Provider",
  "Creative Director Tools",
  "Canonical Prompt Planner Q&A",
  "Prompt Workshop",
  "Manual Prompt",
  "Prompt Preview",
  "Generate Images",
  "Live Generation",
] as const;

const REFERENCE_DEPENDENT_SECTIONS = new Set<string>([
  "Creative Director Tools",
  "Prompt Workshop",
  "Manual Prompt",
  "Prompt Preview",
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

function selectedPromptInput(source: PromptSource, inputs: CreativeToolInputs, manualPrompt: string) {
  const manual = manualPrompt.trim();
  if (manual) return manual;
  if (source === "Enhanced Tags") {
    const enhanced = inputs.enhancedTags.trim();
    if (!enhanced) return "";
    return (
      `[ORIGINAL USER TAGS — mandatory: ${inputs.creativeTags.trim().replaceAll("\n", ", ")}] `
      + `[ENHANCED SUGGESTIONS — vary any wardrobe detail not present in ORIGINAL USER TAGS: ${enhanced.replaceAll("\n", ", ")}]`
    );
  }
  if (source === "Surprise Me Tags") return inputs.surpriseTags.trim();
  if (source === "Enhanced Explicit Tags") return inputs.enhancedExplicitTags.trim();
  if (source === "Prompt Workshop") return manual;
  return inputs.creativeTags.trim();
}

export function ContentStudioWorkflow({ context, error, loading }: ContentStudioWorkflowProps) {
  const [promptCount, setPromptCount] = useState<number | null>(null);
  const [creativeMode, setCreativeMode] = useState<string | null>(null);
  const [creativeInputs, setCreativeInputs] = useState<CreativeToolInputs>(EMPTY_CREATIVE_INPUTS);
  const [promptSource, setPromptSource] = useState<PromptSource>("Original Tags");
  const [manualPrompt, setManualPrompt] = useState("");
  const [provider, setProvider] = useState<string | null>(null);
  const [previewPromptBatch, setPreviewPromptBatch] = useState<string[]>([]);
  const [workshopBatch, setWorkshopBatch] = useState({ prompts: [] as string[], source: "" });
  const blocked = Boolean(error) || context?.status === "profile_missing";
  const referenceMissing = context?.status === "reference_missing";
  const effectivePromptInput = selectedPromptInput(promptSource, creativeInputs, manualPrompt);
  const authoringDisabled = Boolean(referenceMissing) || promptCount === null;
  const previewDisabled = authoringDisabled || creativeMode === null || !effectivePromptInput;
  const generationDisabled = previewDisabled || provider === null;

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
            onInputsChange={setCreativeInputs}
            onPromptSourceChange={setPromptSource}
            promptCount={promptCount ?? 1}
            promptSource={promptSource}
            promptWorkshopHasValue={Boolean(
              manualPrompt.trim() || workshopBatch.prompts.some((prompt) => prompt.trim()),
            )}
          />
          {WORKFLOW_SECTIONS.slice(2).map((title) => title === "Canonical Prompt Planner Q&A" ? (
            <CanonicalPromptPlannerSection disabled={false} key={title} />
          ) : title === "Prompt Workshop" ? (
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
          ) : title === "Prompt Preview" ? (
            <PromptPreviewSection
              disabled={previewDisabled}
              key={title}
              onPromptBatchChange={setPreviewPromptBatch}
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
