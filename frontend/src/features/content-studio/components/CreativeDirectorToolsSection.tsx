import { useEffect, useState, type ReactNode } from "react";

import {
  createLuckyTags,
  enhanceCreativeTags,
  surpriseCreativeTags,
} from "../../../infrastructure/api/contentStudioApi";
import type { CreativeToolInputs, PromptSource } from "../types/contentStudioCreativeTools";

type CreativeDirectorToolsSectionProps = {
  disabled: boolean;
  ideaEnhancement: { id: string; text: string } | null;
  onIdeaEnhancementComplete: () => void;
  onInputsChange: (inputs: CreativeToolInputs) => void;
  onPremiumEnhanced: (originalTags: string, enhancedTags: string) => Promise<void>;
  onPromptSourceChange: (source: PromptSource) => void;
  planner: ReactNode;
  promptCount: number;
};

type ActionName = "premiumLucky" | "premiumEnhance" | "surprise" | "explicitLucky" | "explicitEnhance";

export function CreativeDirectorToolsSection({
  disabled,
  ideaEnhancement,
  onIdeaEnhancementComplete,
  onInputsChange,
  onPremiumEnhanced,
  onPromptSourceChange,
  planner,
  promptCount,
}: CreativeDirectorToolsSectionProps) {
  const [creativeTags, setCreativeTags] = useState("");
  const [explicitTags, setExplicitTags] = useState("");
  const [enhancedTags, setEnhancedTags] = useState("");
  const [surpriseTags, setSurpriseTags] = useState("");
  const [enhancedExplicitTags, setEnhancedExplicitTags] = useState("");
  const [pendingAction, setPendingAction] = useState<ActionName | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!ideaEnhancement) return;
    let active = true;
    setError("");
    enhanceCreativeTags(ideaEnhancement.text, false)
      .then((tags) => {
        if (!active) return;
        setEnhancedTags(tags);
        onPromptSourceChange("Enhanced Tags");
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Creative tag action failed");
      })
      .finally(() => { if (active) onIdeaEnhancementComplete(); });
    return () => { active = false; };
  }, [ideaEnhancement, onIdeaEnhancementComplete, onPromptSourceChange]);

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
    await onPremiumEnhanced(creativeTags, tags);
  };

  const surprisePremium = async () => {
    const tags = await runAction("surprise", () => surpriseCreativeTags(creativeTags));
    if (tags === null) return;
    setSurpriseTags(tags);
    onInputsChange({ creativeTags, enhancedExplicitTags, enhancedTags, explicitTags, surpriseTags: tags });
    onPromptSourceChange("Surprise Me Tags");
  };

  const enhanceExplicit = async () => {
    const tags = await runAction("explicitEnhance", () => enhanceCreativeTags(explicitTags, true));
    if (tags === null) return;
    setEnhancedExplicitTags(tags);
    onPromptSourceChange("Enhanced Explicit Tags");
  };

  const busy = pendingAction !== null;
  return (
    <section
      aria-disabled={disabled || undefined}
      aria-label="Creative Direction Workspace"
      className={`workflow-section creative-director-tools${disabled ? " workflow-section--disabled" : ""}`}
    >
      <h2>Creative Direction</h2>
      <p className="creative-director-tools__caption">
        Premium prompt helpers, enhanced tags, Surprise Me, and explicit-ready planning.
      </p>

      <div className="creative-director-tools__group">
        <label>
          <span>Creative Direction</span>
          <textarea
            disabled={disabled}
            onChange={(event) => {
              setCreativeTags(event.target.value);
              onPromptSourceChange("Original Tags");
            }}
            placeholder="Enter premium scene, wardrobe, setting, mood, continuity, and framing direction."
            rows={5}
            value={creativeTags}
          />
        </label>
        {planner}
        <div className="creative-director-tools__actions">
          <button disabled={disabled || busy} onClick={premiumLucky} type="button">
            🎲 I Feel Lucky
          </button>
          <button disabled={disabled || busy || !creativeTags.trim()} onClick={enhancePremium} type="button">
            ✨ Enhance &amp; Build Prompts
          </button>
          <button disabled={disabled || busy || !creativeTags.trim()} onClick={surprisePremium} type="button">
            🎭 Surprise Me
          </button>
        </div>
      </div>

      <div className="creative-director-tools__derived-grid">
        <label>
          <span>Enhanced Premium Tags</span>
          <textarea disabled={disabled} onChange={(event) => {
            setEnhancedTags(event.target.value);
            onPromptSourceChange("Enhanced Tags");
          }} rows={4} value={enhancedTags} />
        </label>
        <label>
          <span>Surprise Me Tags</span>
          <textarea disabled={disabled} onChange={(event) => {
            setSurpriseTags(event.target.value);
            onPromptSourceChange("Surprise Me Tags");
          }} rows={4} value={surpriseTags} />
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
            onChange={(event) => {
              setEnhancedExplicitTags(event.target.value);
              onPromptSourceChange("Enhanced Explicit Tags");
            }}
            rows={4}
            value={enhancedExplicitTags}
          />
        </label>
      </div>

      {pendingAction && <p className="creative-director-tools__status">Working…</p>}
      {error && <p className="creative-director-tools__status creative-director-tools__status--error" role="alert">{error}</p>}
    </section>
  );
}
