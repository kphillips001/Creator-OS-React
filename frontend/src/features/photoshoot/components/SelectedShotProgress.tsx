import { LiveProgressPanel, type LiveProgressTone } from "../../../shared/ui/LiveProgressPanel";

export type SelectedShotStage = 0 | 1 | 2 | 3 | 4;

const STAGES = [
  "Developing creative direction",
  "Preserving photoshoot continuity",
  "Building canonical prompt",
  "Rendering with Seedream 5.0 Pro",
] as const;

export function SelectedShotProgress({
  activeStage,
  error,
  finalizationRequired = false,
  preparationRecoveryRequired = false,
  onRetry,
  onRetryFinalization,
  onRetryPreparation,
  providerLabel,
}: {
  activeStage: SelectedShotStage;
  error: string;
  finalizationRequired?: boolean;
  preparationRecoveryRequired?: boolean;
  onRetry: () => void;
  onRetryFinalization?: () => void;
  onRetryPreparation?: () => void;
  providerLabel: string;
}) {
  const complete = activeStage === 4;
  const recoveryRequired = finalizationRequired || preparationRecoveryRequired;
  const tone: LiveProgressTone = recoveryRequired ? "waiting" : error ? "failed" : complete ? "complete" : "active";
  return (
    <section aria-label="Selected shot progress" className="photoshoot-selected-progress">
      <LiveProgressPanel
        actions={preparationRecoveryRequired
          ? <button className="photoshoot-button photoshoot-button--primary" onClick={onRetryPreparation} type="button">Retry Preparation</button>
          : finalizationRequired
          ? <button className="photoshoot-button photoshoot-button--primary" onClick={onRetryFinalization} type="button">Retry Finalization</button>
          : error ? <button className="photoshoot-button photoshoot-button--primary" onClick={onRetry} type="button">Retry</button> : undefined}
        active={!error && !complete}
        progressLabel={`${Math.min(activeStage, 4)} of 4 stages`}
        progressPercent={(Math.min(activeStage, 4) / 4) * 100}
        status={preparationRecoveryRequired ? "Generation preparation needs recovery" : finalizationRequired ? "Image generated — finalization required" : error || (complete ? "Rendering complete" : "Preparing Next Shot...")}
        title={preparationRecoveryRequired ? "Generation preparation needs recovery" : finalizationRequired ? "Image generated — finalization required" : "Preparing Next Shot..."}
        tone={tone}
      >
        <ol className="photoshoot-selected-progress__stages">
          {STAGES.map((label, index) => {
            const completed = index < activeStage;
            const active = index === activeStage && !complete && !error;
            return <li aria-current={active ? "step" : undefined} className={completed ? "is-complete" : active ? "is-active" : ""} key={label}>
              <span aria-hidden="true">{completed ? "✓" : active ? "⏳" : "○"}</span>
              <strong>{complete && index === 3 ? "Rendering complete" : index === 3 ? `Rendering with ${providerLabel}` : label}</strong>
            </li>;
          })}
        </ol>
      </LiveProgressPanel>
    </section>
  );
}
