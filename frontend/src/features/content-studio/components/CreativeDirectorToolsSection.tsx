import { forwardRef, useEffect, useImperativeHandle, useState, type ReactNode } from "react";

import { enhanceCreativeTags } from "../../../infrastructure/api/contentStudioApi";
import type { CreativeToolInputs, PromptSource } from "../types/contentStudioCreativeTools";
import type { CanonicalPlannerItem } from "../types/promptPlanner";

type CreativeDirectorToolsSectionProps = {
  creatingImages: boolean;
  disabled: boolean;
  onCreateImages: (creativeConcept: string) => Promise<void>;
  onInputsChange: (inputs: CreativeToolInputs) => void;
  onPromptSourceChange: (source: PromptSource) => void;
  planner: ReactNode;
  promptCount: number;
};

export type CreativeDirectorToolsHandle = {
  enhanceIdea: (item: CanonicalPlannerItem) => Promise<string | null>;
};

export const CreativeDirectorToolsSection = forwardRef<CreativeDirectorToolsHandle, CreativeDirectorToolsSectionProps>(function CreativeDirectorToolsSection({
  creatingImages,
  disabled,
  onCreateImages,
  onInputsChange,
  onPromptSourceChange,
  planner,
}, ref) {
  const [creativeTags, setCreativeTags] = useState("");
  const [explicitTags, setExplicitTags] = useState("");
  const [enhancedTags, setEnhancedTags] = useState("");
  const [enhancedExplicitTags, setEnhancedExplicitTags] = useState("");
  const [explicitPending, setExplicitPending] = useState(false);
  const [error, setError] = useState("");

  useImperativeHandle(ref, () => ({
    enhanceIdea: async (item: CanonicalPlannerItem) => {
      try {
        const tags = await enhanceCreativeTags(item.fullText, false, undefined, {
          origin: item.origin,
          plannerItemId: item.id,
          plannerItemTitle: item.title,
          plannerQuestion: item.plannerQuestion,
        });
        setEnhancedTags(tags);
        onPromptSourceChange("Enhanced Tags");
        return tags;
      } catch (reason: unknown) {
        setError(reason instanceof Error ? reason.message : "Creative tag action failed");
        return null;
      }
    },
  }), [onPromptSourceChange]);

  useEffect(() => {
    onInputsChange({
      creativeTags,
      enhancedExplicitTags,
      enhancedTags,
      explicitTags,
    });
  }, [creativeTags, enhancedExplicitTags, enhancedTags, explicitTags, onInputsChange]);

  const enhanceExplicit = async () => {
    setExplicitPending(true);
    setError("");
    try {
      const tags = await enhanceCreativeTags(explicitTags, true);
      setEnhancedExplicitTags(tags);
      onPromptSourceChange("Enhanced Explicit Tags");
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Creative tag action failed");
    } finally {
      setExplicitPending(false);
    }
  };

  return (
    <section
      aria-disabled={disabled || undefined}
      aria-label="Creative Direction Workspace"
      className={`workflow-section creative-director-tools${disabled ? " workflow-section--disabled" : ""}`}
    >
      <h2>Creative Direction</h2>
      <p className="creative-director-tools__caption">
        Create images from a manual concept or use the Canonical Prompt Planner.
      </p>

      <div className="creative-director-tools__group">
        <label>
          <span>Creative Concept</span>
          <textarea
            disabled={disabled || creatingImages}
            onChange={(event) => {
              setCreativeTags(event.target.value);
              onPromptSourceChange("Original Tags");
            }}
            placeholder="Enter a believable moment or activity from Ava’s life."
            rows={5}
            value={creativeTags}
          />
        </label>
        <div className="creative-director-tools__actions">
          <button
            disabled={disabled || creatingImages || !creativeTags.trim()}
            onClick={() => void onCreateImages(creativeTags)}
            type="button"
          >
            {creatingImages ? "Creating Images..." : "🚀 Create Images"}
          </button>
        </div>
        {planner}
      </div>

      <div className="creative-director-tools__group creative-director-tools__group--explicit">
        <label>
          <span>Explicit Tags</span>
          <textarea
            disabled={disabled}
            onChange={(event) => setExplicitTags(event.target.value)}
            placeholder="Optional explicit-ready premium direction for the explicit tag lane."
            rows={4}
            value={explicitTags}
          />
        </label>
        <div className="creative-director-tools__actions">
          <button disabled={disabled || explicitPending || !explicitTags.trim()} onClick={() => void enhanceExplicit()} type="button">
            ✨ Enhance Explicit Tags
          </button>
        </div>
        <label>
          <span>Enhanced Explicit Tags</span>
          <textarea
            disabled={disabled}
            onChange={(event) => {
              setEnhancedExplicitTags(event.target.value);
              onPromptSourceChange("Enhanced Explicit Tags");
            }}
            rows={4}
            value={enhancedExplicitTags}
          />
        </label>
      </div>

      {explicitPending && <p className="creative-director-tools__status">Working…</p>}
      {error && <p className="creative-director-tools__status creative-director-tools__status--error" role="alert">{error}</p>}
    </section>
  );
});
