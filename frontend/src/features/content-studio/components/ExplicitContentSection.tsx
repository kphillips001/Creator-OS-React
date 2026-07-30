import { useMemo, useRef, useState } from "react";

import {
  createPromptPreview,
  enhanceCreativeTags,
  inspireExplicitContent,
} from "../../../infrastructure/api/contentStudioApi";
import type { ContentStudioContext } from "../types/contentStudioContext";
import type { ExplicitGenerationInput } from "../types/generation";
import { type PlannerBatchItem, updatePlannerBatchItems } from "../types/plannerBatch";
import { useContentStudioConfiguration } from "../hooks/useContentStudioConfiguration";
import {
  GenerationWorkflowSections,
  type GenerationWorkflowHandle,
  type PlannerBatchProgress,
} from "./GenerationWorkflowSections";

type ExplicitLane = "tags" | "inspire";
type ExplicitTier = "hardcore" | "softcore";

export function sceneFirstConcept(concept: string) {
  return concept.replace(/^\s*Ava(?:\s+Blackthorne)?\s*(?:[:,—-]\s*)?/i, "").trim();
}

type ExplicitConceptItem = {
  id: string;
  tier: ExplicitTier;
  concept: string;
};

function conceptId(tier: ExplicitTier, index: number): string {
  return `${tier}-${index}`;
}

export function ExplicitContentSection({ context }: { context: ContentStudioContext }) {
  const generationRef = useRef<GenerationWorkflowHandle>(null);
  const { configuration, error: configurationError } = useContentStudioConfiguration();
  const [lane, setLane] = useState<ExplicitLane>("tags");
  const [tags, setTags] = useState("");
  const [enhancedTags, setEnhancedTags] = useState("");
  const [provider, setProvider] = useState("");
  const [imageCount, setImageCount] = useState(1);
  const [hardcore, setHardcore] = useState<string[]>([]);
  const [softcore, setSoftcore] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [prompts, setPrompts] = useState<string[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [activated, setActivated] = useState(false);
  const [items, setItems] = useState<PlannerBatchItem[]>([]);
  const [progress, setProgress] = useState<PlannerBatchProgress | null>(null);

  const activeProvider = provider || configuration?.defaults.provider || "";
  // The explicit enhancer guarantees preservation of all user anchors, so its
  // editable output is the authoritative replacement when one exists.
  const effectiveInput = enhancedTags.trim() || tags.trim();
  const conceptItems = useMemo<ExplicitConceptItem[]>(
    () => [
      ...hardcore.map((concept, index) => ({
        id: conceptId("hardcore", index),
        tier: "hardcore" as const,
        concept,
      })),
      ...softcore.map((concept, index) => ({
        id: conceptId("softcore", index),
        tier: "softcore" as const,
        concept,
      })),
    ],
    [hardcore, softcore],
  );
  const selectedConcepts = useMemo(
    () => conceptItems.filter((item) => selected.has(item.id)),
    [conceptItems, selected],
  );
  const blocked = context.status === "reference_missing" || !activeProvider;
  const hasConcepts = conceptItems.length > 0;
  const allSelected = hasConcepts && selected.size === conceptItems.length;

  const toggleSelected = (id: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectTier = (tier: ExplicitTier, selectAll: boolean) => {
    const tierIds = conceptItems.filter((item) => item.tier === tier).map((item) => item.id);
    setSelected((current) => {
      const next = new Set(current);
      for (const id of tierIds) {
        if (selectAll) next.add(id);
        else next.delete(id);
      }
      return next;
    });
  };

  const enhance = async () => {
    if (!tags.trim() || pending) return;
    setPending(true);
    setError("");
    try {
      setEnhancedTags(await enhanceCreativeTags(tags, true));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Explicit enhancement failed");
    } finally {
      setPending(false);
    }
  };

  const generateTags = async () => {
    if (!effectiveInput || blocked || pending) return;
    setPending(true);
    setActivated(true);
    setError("");
    try {
      const explicitInput: ExplicitGenerationInput = {
        sourceText: effectiveInput,
        originalSource: tags.trim(),
        sourceType: "operator_tags_or_prose",
        origin: "explicit_tags",
        requiredSemanticAttributes: {},
        requestedImageCount: imageCount,
        lineage: {
          enhancedResult: enhancedTags.trim(),
          originalSource: tags.trim(),
        },
      };
      const preview = await createPromptPreview(
        "explicit", effectiveInput, imageCount, undefined, "explicit", explicitInput,
      );
      setPrompts(preview.prompts);
      await generationRef.current?.generate({
        creativeMode: "explicit",
        lane: "explicit",
        promptBatch: preview.prompts,
        promptCount: imageCount,
        promptSource: effectiveInput,
        promptSourceLabel: "Enhanced Explicit Tags",
        origin: "explicit_tags",
        explicitInput,
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Explicit generation failed");
    } finally {
      setPending(false);
    }
  };

  const inspire = async () => {
    if (pending) return;
    setPending(true);
    setError("");
    try {
      const next = await inspireExplicitContent(5);
      setHardcore(next.hardcore.map(sceneFirstConcept));
      setSoftcore(next.softcore.map(sceneFirstConcept));
      setSelected(new Set());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Explicit inspiration failed");
    } finally {
      setPending(false);
    }
  };

  const generateSelected = async () => {
    if (!selectedConcepts.length || blocked || pending) return;
    setPending(true);
    setActivated(true);
    setError("");
    const batch = selectedConcepts.map((item, batchOrdinal) => ({
      error: "",
      id: `explicit-${item.id}`,
      imageUrl: "",
      jobId: null,
      ordinal: batchOrdinal,
      status: "pending" as const,
    }));
    setItems(batch);
    let completedIdeas = 0;
    let failedIdeas = 0;
    setProgress({ completedIdeas, currentIdeaIndex: 0, failedIdeas, phase: "preparing", totalIdeas: batch.length });
    const collectionId = `explicit-collection-${selectedConcepts.map(({ id }) => id).join("-")}`;
    const enhancedConcepts: string[] = [];
    for (const [index, selection] of selectedConcepts.entries()) {
      const item = batch[index]!;
      setItems((current) => updatePlannerBatchItems(current, item.id, { status: "enhancing" }));
      setProgress({ completedIdeas, currentIdeaIndex: index + 1, failedIdeas, phase: "preparing", totalIdeas: batch.length });
      try {
        enhancedConcepts.push(
          (await enhanceCreativeTags(selection.concept, true)).replace(/\s*\n+\s*/g, ", "),
        );
      } catch (reason) {
        failedIdeas += 1;
        enhancedConcepts.push("");
        setItems((current) => updatePlannerBatchItems(current, item.id, {
          error: reason instanceof Error ? reason.message : "Explicit concept failed",
          failureStage: "enhancement",
          status: "failed",
        }));
      }
    }
    const plannableSelections = selectedConcepts
      .map((selection, index) => ({ selection, enhanced: enhancedConcepts[index] ?? "", index }))
      .filter(({ enhanced }) => Boolean(enhanced));
    const originalCollection = plannableSelections.map(({ selection }) => selection.concept).join("\n");
    const enhancedCollection = plannableSelections.map(({ enhanced }) => enhanced).join("\n");
    let finalPrompts: string[] = [];
    if (plannableSelections.length) {
      const collectionInput: ExplicitGenerationInput = {
        sourceText: enhancedCollection,
        originalSource: originalCollection,
        sourceType: "selected_inspiration_concept",
        origin: "explicit_inspiration",
        requiredSemanticAttributes: {},
        requestedImageCount: plannableSelections.length,
        collectionId,
        lineage: {
          selectedConceptIds: plannableSelections.map(({ selection }) => selection.id),
          selectedConcepts: plannableSelections.map(({ selection }) => selection.concept),
        },
      };
      try {
        const preview = await createPromptPreview(
          "explicit",
          enhancedCollection,
          plannableSelections.length,
          undefined,
          "explicit",
          collectionInput,
        );
        finalPrompts = preview.prompts.slice(0, plannableSelections.length);
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "Explicit collection planning failed");
        for (const { index } of plannableSelections) {
          const item = batch[index]!;
          setItems((current) => updatePlannerBatchItems(current, item.id, {
            error: reason instanceof Error ? reason.message : "Explicit collection planning failed",
            failureStage: "planning",
            status: "failed",
          }));
        }
        failedIdeas += plannableSelections.length;
      }
    }
    for (const [plannedIndex, planned] of plannableSelections.entries()) {
      const { selection, enhanced, index } = planned;
      const item = batch[index]!;
      const providerPrompt = finalPrompts[plannedIndex];
      if (!providerPrompt) continue;
      try {
        setProgress({ completedIdeas, currentIdeaIndex: index + 1, failedIdeas, phase: "generating", totalIdeas: batch.length });
        const tierLabel = selection.tier === "hardcore" ? "Hardcore" : "Softcore";
        const explicitInput: ExplicitGenerationInput = {
          sourceText: enhanced,
          originalSource: selection.concept,
          sourceType: "selected_inspiration_concept",
          origin: "explicit_inspiration",
          conceptTier: selection.tier,
          requiredSemanticAttributes: {},
          requestedImageCount: 1,
          collectionId,
          lineage: {
            collectionPromptIndex: plannedIndex,
            plannerItemId: item.id,
            selectedConcept: selection.concept,
          },
        };
        const succeeded = await generationRef.current?.generate({
          batchItemId: item.id,
          creativeMode: "explicit",
          lane: "explicit",
          promptBatch: [providerPrompt],
          promptCount: 1,
          promptSource: enhanced,
          promptSourceLabel: "Enhanced Explicit Tags",
          origin: "explicit_inspiration",
          plannerLineage: {
            enhancedResult: enhanced,
            plannerItemId: item.id,
            plannerItemTitle: `${tierLabel} concept ${index + 1}`,
            plannerQuestion: "Explicit Inspire Me",
            selectedPlannerItem: selection.concept,
          },
          explicitInput,
        });
        if (succeeded) completedIdeas += 1;
        else failedIdeas += 1;
      } catch (reason) {
        failedIdeas += 1;
        setItems((current) => updatePlannerBatchItems(current, item.id, {
          error: reason instanceof Error ? reason.message : "Explicit concept failed",
          failureStage: "generation",
          status: "failed",
        }));
      }
    }
    setPrompts(finalPrompts.filter(Boolean));
    setProgress({
      completedIdeas,
      currentIdeaIndex: batch.length,
      failedIdeas,
      phase: "complete",
      totalIdeas: batch.length,
    });
    setPending(false);
  };

  const renderTier = (tier: ExplicitTier, concepts: string[], title: string, description: string) => {
    if (!concepts.length) return null;
    const tierItems = concepts.map((concept, index) => ({
      id: conceptId(tier, index),
      concept,
    }));
    const selectedInTier = tierItems.filter((item) => selected.has(item.id)).length;
    const allTierSelected = selectedInTier === tierItems.length;
    return (
      <section aria-label={title} className={`explicit-content__tier explicit-content__tier--${tier}`}>
        <header className="explicit-content__tier-header">
          <div>
            <h3>{title}</h3>
            <p>{description}</p>
          </div>
          <label className="explicit-content__select-all">
            <input
              checked={allTierSelected}
              ref={(input) => {
                if (input) input.indeterminate = selectedInTier > 0 && !allTierSelected;
              }}
              onChange={() => selectTier(tier, !allTierSelected)}
              type="checkbox"
            />
            <span>Select all {tier} ({selectedInTier}/{tierItems.length})</span>
          </label>
        </header>
        <div className="explicit-content__concepts">
          {tierItems.map((item) => (
            <label key={item.id} className={`explicit-content__concept explicit-content__concept--${tier}`}>
              <input
                checked={selected.has(item.id)}
                onChange={() => toggleSelected(item.id)}
                type="checkbox"
              />
              <span>
                <em className={`explicit-content__badge explicit-content__badge--${tier}`}>
                  {tier === "hardcore" ? "Hardcore" : "Softcore"}
                </em>
                {item.concept}
              </span>
            </label>
          ))}
        </div>
      </section>
    );
  };

  return (
    <details className="creative-studio explicit-content-accordion">
      <summary>
        <span>🔞 Explicit Content</span>
        <small>Create from tags or generate mixed hardcore + softcore PPV concepts.</small>
      </summary>
      <section aria-label="Explicit Content" className="creative-studio__content explicit-content">
      <header>
        <p className="inspire-workspace__eyebrow">Separate premium workflow</p>
        <h2>Explicit Content</h2>
        <p>Create with explicit tags or ask Grok for 5 hardcore and 5 softcore concepts you can mix.</p>
      </header>
      <div className="explicit-content__tabs" role="tablist">
        <button aria-selected={lane === "tags"} onClick={() => setLane("tags")} role="tab" type="button">Create From Tags</button>
        <button
          aria-selected={lane === "inspire"}
          onClick={() => {
            setLane("inspire");
            if (!hasConcepts && !pending) void inspire();
          }}
          role="tab"
          type="button"
        >
          Inspire Me
        </button>
      </div>

      {lane === "tags" ? (
        <div className="explicit-content__lane creative-director-tools creative-director-tools__group">
          <label><span>Explicit Tags</span><textarea onChange={(event) => setTags(event.target.value)} rows={4} value={tags} /></label>
          <button disabled={pending || !tags.trim()} onClick={() => void enhance()} type="button">✨ Enhance Tags</button>
          <label><span>Enhanced Tags</span><textarea onChange={(event) => setEnhancedTags(event.target.value)} rows={6} value={enhancedTags} /></label>
        </div>
      ) : (
        <div className="explicit-content__lane creative-director-tools creative-director-tools__group">
          {pending && !hasConcepts && <p className="creative-director-tools__status">Creating inspiration…</p>}
          {hasConcepts && (
            <>
              <div className="explicit-content__selection-bar">
                <label className="explicit-content__select-all">
                  <input
                    checked={allSelected}
                    ref={(input) => { if (input) input.indeterminate = selected.size > 0 && !allSelected; }}
                    onChange={() => setSelected(allSelected ? new Set() : new Set(conceptItems.map((item) => item.id)))}
                    type="checkbox"
                  />
                  <span>Select All ({selected.size} selected)</span>
                </label>
                <button onClick={() => setSelected(new Set())} type="button">Clear Selection</button>
              </div>
              {renderTier(
                "hardcore",
                hardcore,
                "🔥 Hardcore",
                "Direct sexual acts and genital display for high-ticket PPV unlocks.",
              )}
              {renderTier(
                "softcore",
                softcore,
                "💋 Softcore",
                "Sexy teasing, topless, lingerie, and erotic poses without hardcore acts.",
              )}
              <button disabled={blocked || pending || selected.size === 0} onClick={() => void generateSelected()} type="button">
                🚀 Enhance &amp; Generate ({selected.size})
              </button>
            </>
          )}
        </div>
      )}

      {lane === "tags" && (
        <>
          <section
            aria-label="Explicit Generation Settings"
            className="explicit-content__settings creative-configuration prompt-workshop"
          >
            <h3>Generation Settings</h3>
            <label><span>Image Count</span><input aria-label="Explicit Image Count" max={12} min={1} onChange={(event) => setImageCount(Number(event.target.value))} type="number" value={imageCount} /></label>
            <label><span>Provider</span><select aria-label="Explicit Provider" onChange={(event) => setProvider(event.target.value)} value={activeProvider}>
              {configuration?.providers.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select></label>
            <details className="creative-configuration__advanced">
              <summary>Advanced Settings</summary>
              <p>Image count controls the number of images generated from this tag request.</p>
            </details>
          </section>
          <button disabled={blocked || pending || !effectiveInput} onClick={() => void generateTags()} type="button">🖼 Generate Images</button>
          <details className="explicit-content__preview">
            <summary>Prompt Preview</summary>
            {prompts.length ? prompts.map((prompt, index) => <pre key={`${index}-${prompt}`}>{prompt}</pre>) : <p>Final explicit prompts will appear here after construction.</p>}
          </details>
        </>
      )}
      {(pending || error) && <p className={error ? "generation-live__error" : "creative-director-tools__status"}>{error || "Working…"}</p>}
      {configurationError && <p className="generation-live__error">{configurationError}</p>}
      <div className={activated ? "workflow-live-preview workflow-live-preview--creative" : "workflow-controller"}>
        {activated && <h3>Explicit Live Generation</h3>}
        <GenerationWorkflowSections
          context={context}
          disabled={blocked}
          onAskAnotherQuestion={() => undefined}
          onContinueExploring={() => undefined}
          onPlannerBatchItemChange={(id, changes) => setItems((current) => updatePlannerBatchItems(current, id, changes))}
          onRunStart={() => setActivated(true)}
          onStartNewSession={() => undefined}
          plannerBatchItems={items}
          plannerBatchProgress={progress}
          plannerBatchRunning={pending}
          request={{
            creativeMode: "explicit",
            lane: "explicit",
            promptBatch: [],
            promptCount: lane === "tags" ? imageCount : Math.max(1, selected.size),
            promptSource: effectiveInput || "Explicit inspiration",
            promptSourceLabel: "Enhanced Explicit Tags",
            provider: activeProvider,
          }}
          ref={generationRef}
          workflow="manual"
        />
      </div>
      </section>
    </details>
  );
}
