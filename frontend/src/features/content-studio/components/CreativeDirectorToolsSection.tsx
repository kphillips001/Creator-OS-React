import { useEffect, useState } from "react";

import {
  createLuckyTags,
  enhanceCreativeTags,
  surpriseCreativeTags,
} from "../../../infrastructure/api/contentStudioApi";
import {
  PROMPT_SOURCES,
  type CreativeToolInputs,
  type PromptSource,
} from "../types/contentStudioCreativeTools";

type CreativeDirectorToolsSectionProps = {
  disabled: boolean;
  onInputsChange: (inputs: CreativeToolInputs) => void;
  onPromptSourceChange: (source: PromptSource) => void;
  promptCount: number;
  promptSource: PromptSource;
  promptWorkshopHasValue: boolean;
};

type ActionName = "premiumLucky" | "premiumEnhance" | "surprise" | "explicitLucky" | "explicitEnhance";

export function CreativeDirectorToolsSection({
  disabled,
  onInputsChange,
  onPromptSourceChange,
  promptCount,
  promptSource,
  promptWorkshopHasValue,
}: CreativeDirectorToolsSectionProps) {
  const [creativeTags, setCreativeTags] = useState("");
  const [explicitTags, setExplicitTags] = useState("");
  const [enhancedTags, setEnhancedTags] = useState("");
  const [surpriseTags, setSurpriseTags] = useState("");
  const [enhancedExplicitTags, setEnhancedExplicitTags] = useState("");
  const [pendingAction, setPendingAction] = useState<ActionName | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    onInputsChange({
      creativeTags,
      enhancedExplicitTags,
      enhancedTags,
      explicitTags,
      surpriseTags,
    });
  }, [creativeTags, enhancedExplicitTags, enhancedTags, explicitTags, onInputsChange, surpriseTags]);

  const runAction = async (action: ActionName, request: () => Promise<string>) => {
    setPendingAction(action);
    setError("");
    try {
      return await request();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Creative tag action failed");
      return null;
    } finally {
      setPendingAction(null);
    }
  };

  const premiumLucky = async () => {
    const tags = await runAction("premiumLucky", () => createLuckyTags(promptCount, false));
    if (tags === null) return;
    setCreativeTags(tags);
    onPromptSourceChange("Original Tags");
  };

  const explicitLucky = async () => {
    const tags = await runAction("explicitLucky", () => createLuckyTags(promptCount, true));
    if (tags !== null) setExplicitTags(tags);
  };

  const enhancePremium = async () => {
    const tags = await runAction("premiumEnhance", () => enhanceCreativeTags(creativeTags, false));
    if (tags === null) return;
    setEnhancedTags(tags);
    onPromptSourceChange("Enhanced Tags");
  };

  const surprisePremium = async () => {
    const tags = await runAction("surprise", () => surpriseCreativeTags(creativeTags));
    if (tags === null) return;
    setSurpriseTags(tags);
    onPromptSourceChange("Surprise Me Tags");
  };

  const enhanceExplicit = async () => {
    const tags = await runAction("explicitEnhance", () => enhanceCreativeTags(explicitTags, true));
    if (tags === null) return;
    setEnhancedExplicitTags(tags);
    onPromptSourceChange("Enhanced Explicit Tags");
  };

  const busy = pendingAction !== null;
  const selectedSourceHasValue = {
    "Original Tags": Boolean(creativeTags.trim()),
    "Enhanced Tags": Boolean(enhancedTags.trim()),
    "Surprise Me Tags": Boolean(surpriseTags.trim()),
    "Enhanced Explicit Tags": Boolean(enhancedExplicitTags.trim()),
    "Prompt Workshop": promptWorkshopHasValue,
  }[promptSource];

  return (
    <section
      aria-disabled={disabled || undefined}
      aria-label="Creative Director Tools"
      className={`workflow-section creative-director-tools${disabled ? " workflow-section--disabled" : ""}`}
    >
      <h2>Creative Director Tools</h2>
      <p className="creative-director-tools__caption">
        Premium prompt helpers, enhanced tags, Surprise Me, and explicit-ready planning.
      </p>

      <div className="creative-director-tools__group">
        <label>
          <span>Premium Creative Tags</span>
          <textarea
            disabled={disabled}
            onChange={(event) => setCreativeTags(event.target.value)}
            placeholder="Enter premium scene, wardrobe, setting, mood, continuity, and framing direction."
            rows={5}
            value={creativeTags}
          />
        </label>
        <div className="creative-director-tools__actions">
          <button disabled={disabled || busy} onClick={premiumLucky} type="button">
            🎲 I Feel Lucky
          </button>
          <button disabled={disabled || busy || !creativeTags.trim()} onClick={enhancePremium} type="button">
            ✨ Enhance Premium Tags
          </button>
          <button disabled={disabled || busy || !creativeTags.trim()} onClick={surprisePremium} type="button">
            🎭 Surprise Me
          </button>
        </div>
      </div>

      <div className="creative-director-tools__derived-grid">
        <label>
          <span>Enhanced Premium Tags</span>
          <textarea disabled={disabled} onChange={(event) => setEnhancedTags(event.target.value)} rows={4} value={enhancedTags} />
        </label>
        <label>
          <span>Surprise Me Tags</span>
          <textarea disabled={disabled} onChange={(event) => setSurpriseTags(event.target.value)} rows={4} value={surpriseTags} />
        </label>
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
          <button disabled={disabled || busy} onClick={explicitLucky} type="button">
            🔥 I Feel Lucky
          </button>
          <button disabled={disabled || busy || !explicitTags.trim()} onClick={enhanceExplicit} type="button">
            ✨ Enhance Explicit Tags
          </button>
        </div>
        <label>
          <span>Enhanced Explicit Tags</span>
          <textarea
            disabled={disabled}
            onChange={(event) => setEnhancedExplicitTags(event.target.value)}
            rows={4}
            value={enhancedExplicitTags}
          />
        </label>
      </div>

      <fieldset className="creative-director-tools__sources">
        <legend>Prompt Source</legend>
        <div className="creative-director-tools__source-options">
          {PROMPT_SOURCES.map((source) => (
            <label key={source.value}>
              <input
                checked={promptSource === source.value}
                disabled={disabled}
                name="premium-studio-prompt-source"
                onChange={() => onPromptSourceChange(source.value)}
                type="radio"
                value={source.value}
              />
              <span>{source.label}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <p className={`creative-director-tools__source-status${selectedSourceHasValue ? "" : " creative-director-tools__source-status--warning"}`}>
        {selectedSourceHasValue ? `Using ${promptSource}.` : "Selected premium prompt source is empty."}
      </p>

      {pendingAction && <p className="creative-director-tools__status">Working…</p>}
      {error && <p className="creative-director-tools__status creative-director-tools__status--error" role="alert">{error}</p>}
    </section>
  );
}
