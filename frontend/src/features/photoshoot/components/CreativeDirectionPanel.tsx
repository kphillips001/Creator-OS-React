import type { CreativeDirectorRecommendation } from "../types";

type Props = {
  disabled: boolean; busy: boolean; guidance: string; ideas: string[]; selectedIdea: string;
  creativeMode?: string;
  recommendation: CreativeDirectorRecommendation | null; directionApproved: boolean;
  onGuidance: (value: string) => void; onDirect: () => void; onAsk: () => void; onDifferentIdeas: () => void;
  onSelectIdea: (value: string) => void; onGenerateSelected: () => void;
  onDirectSelected: () => void;
  onChooseAnother: () => void;
  planningStatus?: { currentShot: number; planningShot: number; targetShotCount: number; remainingShots: number; editorialStage: string; explanation: string };
};

const details: Array<[keyof CreativeDirectorRecommendation, string]> = [
  ["reasoning", "Reasoning"], ["emotion", "Emotion"], ["camera_framing", "Camera Framing"],
  ["lighting", "Lighting"], ["pose_composition", "Pose / Composition"], ["continuity_notes", "Continuity Notes"],
];

export function CreativeDirectionPanel(props: Props) {
  const hasIdeas = props.ideas.length > 0;
  const isExplicit = String(props.creativeMode || "").toLowerCase() === "explicit";
  const planning = props.planningStatus || { currentShot: 1, planningShot: 2, targetShotCount: 10, remainingShots: 9, editorialStage: "Beginning", explanation: "Continuing from the latest approved shot." };
  return <section className="photoshoot-card photoshoot-creative-director" aria-labelledby="photoshoot-direction-title">
    <header><h2 id="photoshoot-direction-title">AI Creative Director</h2><span>Plan the strongest next photograph</span></header>
    <div className="photoshoot-planning-status">
      {!hasIdeas && !props.recommendation && <em>Ready for Next Shot</em>}
      {planning.targetShotCount === 0 ? (
        <><strong>Open-ended Photoshoot</strong><span>{planning.currentShot} approved</span><p>No target length selected. The AI will continue planning the next natural shot until the operator ends the session.</p></>
      ) : (
        <><strong>Planning Shot {planning.planningShot} of {planning.targetShotCount}</strong><span>{planning.currentShot} of {planning.targetShotCount} approved · {planning.editorialStage} · {planning.remainingShots} remaining</span><p>{planning.explanation}</p></>
      )}
    </div>
    <label><span>Direct the Next Shot (Optional)</span><textarea disabled={props.disabled} onChange={(event) => props.onGuidance(event.target.value)} placeholder={"Describe exactly what should happen next...\n\nExamples:\n• Have her lift her shirt.\n• Walk toward the window.\n• Sit on the edge of the bed.\n• Turn around and look over your shoulder."} value={props.guidance} /></label>
    <div className="photoshoot-creative-actions">
      <button className="photoshoot-button photoshoot-button--primary" disabled={props.disabled || props.busy || !props.guidance.trim()} onClick={props.onDirect} type="button">Direct Shot</button>
      <button className="photoshoot-button photoshoot-button--secondary" disabled={props.disabled || props.busy} onClick={props.onAsk} type="button">Ask AI</button>
      {hasIdeas && <button className="photoshoot-button photoshoot-button--secondary" disabled={props.disabled || props.busy} onClick={props.onDifferentIdeas} type="button">Different Ideas</button>}
    </div>
    {hasIdeas && <fieldset className="photoshoot-inspiration"><legend>{isExplicit ? "AI Ideas · #1 is the recommended natural next step" : "AI Ideas"}</legend><div className="photoshoot-inspiration__grid">{props.ideas.map((idea, index) => {
      const selected = props.selectedIdea === idea;
      const recommended = isExplicit && index === 0;
      return <label className={selected ? "photoshoot-inspiration__idea photoshoot-inspiration__idea--selected" : "photoshoot-inspiration__idea"} key={`${index}:${idea}`}><input checked={selected} disabled={props.disabled || props.directionApproved} name="photoshoot-inspiration" onChange={() => props.onSelectIdea(idea)} type="radio" /><span>{recommended ? <em className="photoshoot-inspiration__badge">Recommended natural next</em> : null}<strong>{index + 1}.</strong> {idea}</span></label>;
    })}</div></fieldset>}
    {props.selectedIdea && !props.directionApproved && <div className="photoshoot-selected-direction"><h3>{isExplicit && props.selectedIdea === props.ideas[0] ? "Recommended Natural Next" : "Selected Direction"}</h3><p>{props.selectedIdea}</p><div className="photoshoot-creative-actions"><button className="photoshoot-button photoshoot-button--primary" disabled={props.disabled || props.busy} onClick={props.onGenerateSelected} type="button">Generate Selected Shot</button><button className="photoshoot-button photoshoot-button--secondary" disabled={props.disabled || props.busy} onClick={props.onDirectSelected} type="button">Direct Shot</button></div></div>}
    {props.recommendation && <details className="photoshoot-recommendation photoshoot-recommendation--collapsible"><summary>View Creative Direction</summary><article><h3>{props.recommendation.title || "Next Shot"}</h3><p>{props.recommendation.creative_direction}</p><dl>{details.map(([key, label]) => props.recommendation?.[key] ? <div key={key}><dt>{label}</dt><dd>{props.recommendation[key]}</dd></div> : null)}</dl><div className="photoshoot-creative-actions"><button className="photoshoot-button photoshoot-button--secondary" disabled={props.disabled || props.busy || props.directionApproved} onClick={props.onChooseAnother} type="button">Choose Another Idea</button><button className="photoshoot-button photoshoot-button--secondary" disabled={props.disabled || props.busy} onClick={props.onDifferentIdeas} type="button">Ask for Different Ideas</button></div></article></details>}
  </section>;
}
