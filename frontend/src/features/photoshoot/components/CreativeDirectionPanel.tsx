import { useState } from "react";

import type { CreativeDirectorRecommendation } from "../types";

type Props = {
  disabled: boolean; busy: boolean; guidance: string; ideas: string[]; selectedIdea: string;
  inspirationEdits?: Record<string, string>;
  existingIdeasAvailable?: boolean;
  ideaUsage?: Record<string, string[]>;
  recommendedIdea?: string;
  creativeMode?: string;
  recommendation: CreativeDirectorRecommendation | null; directionApproved: boolean;
  onGuidance: (value: string) => void; onDirect: () => void; onAsk: () => void; onDifferentIdeas: () => void;
  onUseExistingIdeas?: () => void;
  onSelectIdea: (value: string) => void; onGenerateSelected: () => void;
  onDirectionEditSave?: (idea: string, value: string) => void;
  onDirectSelected: () => void;
  onChooseAnother: () => void;
  planningStatus?: { currentShot: number; planningShot: number; targetShotCount: number; remainingShots: number; editorialStage: string; explanation: string };
};

const details: Array<[keyof CreativeDirectorRecommendation, string]> = [
  ["reasoning", "Reasoning"], ["emotion", "Emotion"], ["camera_framing", "Camera Framing"],
  ["lighting", "Lighting"], ["pose_composition", "Pose / Composition"], ["continuity_notes", "Continuity Notes"],
];

export function CreativeDirectionPanel(props: Props) {
  const [directEditorOpen, setDirectEditorOpen] = useState(false);
  const [editingIdea, setEditingIdea] = useState("");
  const [editDraft, setEditDraft] = useState("");
  const hasIdeas = props.ideas.length > 0;
  const isExplicit = String(props.creativeMode || "").toLowerCase() === "explicit";
  const planning = props.planningStatus || { currentShot: 1, planningShot: 2, targetShotCount: 5, remainingShots: 4, editorialStage: "Beginning", explanation: "Continuing from the latest approved shot." };
  const effectiveDirection = (idea: string) => props.inspirationEdits?.[idea]?.trim() || idea;
  const beginEdit = (idea: string) => {
    if (props.disabled || props.directionApproved) return;
    if (props.selectedIdea !== idea) props.onSelectIdea(idea);
    setEditDraft(effectiveDirection(idea));
    setEditingIdea(idea);
  };
  const finishEdit = (idea: string) => {
    if (!editDraft.trim()) return;
    props.onDirectionEditSave?.(idea, editDraft.trim());
    setEditingIdea("");
  };
  const cancelEdit = () => {
    setEditDraft("");
    setEditingIdea("");
  };
  return <section className="photoshoot-card photoshoot-creative-director" aria-labelledby="photoshoot-direction-title">
    <header><h2 id="photoshoot-direction-title">AI Creative Director</h2><span>Plan the strongest next photograph</span></header>
    <div className="photoshoot-planning-status">
      {!hasIdeas && !props.recommendation && <em>Ready for Next Shot</em>}
      {planning.targetShotCount === 0 ? (
        <><strong>CREATIVE FREEFLOW</strong><span>{planning.currentShot} approved</span><p>Exploring another distinct shot while preserving scene and visual continuity.</p></>
      ) : (
        <><strong>Planning Shot {planning.planningShot} of {planning.targetShotCount}</strong><span>{planning.currentShot} of {planning.targetShotCount} approved · {planning.editorialStage} · {planning.remainingShots} remaining</span><p>{planning.explanation}</p></>
      )}
    </div>
    <div className="photoshoot-creative-actions">
      <button className="photoshoot-button photoshoot-button--secondary" disabled={props.disabled || props.busy} onClick={props.onAsk} type="button">Ask AI</button>
      {props.existingIdeasAvailable && <button className="photoshoot-button photoshoot-button--secondary" disabled={props.disabled || props.busy} onClick={props.onUseExistingIdeas} type="button">Use Existing Ideas</button>}
      <button aria-expanded={directEditorOpen} className="photoshoot-button photoshoot-button--secondary" disabled={props.disabled || props.busy} onClick={() => { setDirectEditorOpen(true); props.onDirectSelected(); }} type="button">Direct Shot</button>
      {hasIdeas && <button className="photoshoot-button photoshoot-button--secondary" disabled={props.disabled || props.busy} onClick={props.onDifferentIdeas} type="button">Different Ideas</button>}
    </div>
    {directEditorOpen && <section aria-label="Direct the Next Shot" className="photoshoot-direct-editor"><h3>Direct the Next Shot</h3><p>Describe exactly what Ava should do next.</p><label><span className="photoshoot-sr-only">Direct the Next Shot prompt</span><textarea autoFocus disabled={props.disabled || props.busy} onChange={(event) => props.onGuidance(event.target.value)} value={props.guidance} /></label><div className="photoshoot-creative-actions"><button className="photoshoot-button photoshoot-button--primary" disabled={props.disabled || props.busy || !props.guidance.trim()} onClick={() => { setDirectEditorOpen(false); props.onDirect(); }} type="button">Generate Direct Shot</button><button className="photoshoot-button photoshoot-button--secondary" disabled={props.busy} onClick={() => setDirectEditorOpen(false)} type="button">Cancel</button></div></section>}
    {hasIdeas && <fieldset className="photoshoot-inspiration"><legend>{isExplicit ? "AI Ideas · #1 is the recommended natural next step" : "AI Ideas"}</legend><div className="photoshoot-inspiration__grid">{props.ideas.map((idea, index) => {
      const selected = props.selectedIdea === idea;
      const recommended = props.recommendedIdea ? idea === props.recommendedIdea : isExplicit && index === 0;
      const edited = Boolean(props.inspirationEdits?.[idea]?.trim());
      const used = props.ideaUsage?.[idea] || [];
      return <div className={`${selected ? "photoshoot-inspiration__idea photoshoot-inspiration__idea--selected" : "photoshoot-inspiration__idea"}${editingIdea === idea ? " photoshoot-inspiration__idea--editing" : ""}`} key={idea} onDoubleClick={() => beginEdit(idea)}><label><input aria-label={`${index + 1}. ${effectiveDirection(idea)}`} checked={selected} disabled={props.disabled || props.directionApproved} name="photoshoot-inspiration" onChange={() => props.onSelectIdea(idea)} type="radio" /><span>{recommended ? <em className="photoshoot-inspiration__badge">Recommended natural next</em> : null}{used.length ? <em className="photoshoot-inspiration__used">✓ Used — {used.join(", ")}</em> : null}{edited ? <em className="photoshoot-inspiration__edited">Edited</em> : null}<strong>{index + 1}.</strong>{editingIdea !== idea ? ` ${effectiveDirection(idea)}` : null}</span></label>{editingIdea === idea && <div className="photoshoot-inspiration__editor" onClick={(event) => event.stopPropagation()} onDoubleClick={(event) => event.stopPropagation()}><textarea aria-label={`Edit direction ${index + 1}`} autoFocus onChange={(event) => setEditDraft(event.target.value)} onKeyDown={(event) => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter") finishEdit(idea); else if (event.key === "Escape") cancelEdit(); }} value={editDraft} /><div><button disabled={!editDraft.trim()} onClick={() => finishEdit(idea)} type="button">Done</button><button onClick={cancelEdit} type="button">Cancel</button></div></div>}</div>;
    })}</div></fieldset>}
    {props.selectedIdea && !props.directionApproved && <div className="photoshoot-selected-direction"><h3>{isExplicit && props.selectedIdea === props.ideas[0] ? "Recommended Natural Next" : "Selected Direction"}</h3><p>{effectiveDirection(props.selectedIdea)}</p><div className="photoshoot-creative-actions"><button className="photoshoot-button photoshoot-button--primary" disabled={props.disabled || props.busy} onClick={props.onGenerateSelected} type="button">Generate Selected Shot</button></div></div>}
    {props.recommendation && <details className="photoshoot-recommendation photoshoot-recommendation--collapsible"><summary>View Creative Direction</summary><article><h3>{props.recommendation.title || "Next Shot"}</h3><p>{props.recommendation.creative_direction}</p><dl>{details.map(([key, label]) => props.recommendation?.[key] ? <div key={key}><dt>{label}</dt><dd>{props.recommendation[key]}</dd></div> : null)}</dl><div className="photoshoot-creative-actions"><button className="photoshoot-button photoshoot-button--secondary" disabled={props.disabled || props.busy || props.directionApproved} onClick={props.onChooseAnother} type="button">Choose Another Idea</button><button className="photoshoot-button photoshoot-button--secondary" disabled={props.disabled || props.busy} onClick={props.onDifferentIdeas} type="button">Ask for Different Ideas</button></div></article></details>}
  </section>;
}
