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
  onRetry,
  providerLabel,
}: {
  activeStage: SelectedShotStage;
  error: string;
  onRetry: () => void;
  providerLabel: string;
}) {
  const complete = activeStage === 4;
  const tone: LiveProgressTone = error ? "failed" : complete ? "complete" : "active";
  return (
    <section aria-label="Selected shot progress" className="photoshoot-selected-progress">
      <LiveProgressPanel
        actions={error ? <button className="photoshoot-button photoshoot-button--primary" onClick={onRetry} type="button">Retry</button> : undefined}
        active={!error && !complete}
        progressLabel={`${Math.min(activeStage, 4)} of 4 stages`}
        progressPercent={(Math.min(activeStage, 4) / 4) * 100}
        status={error || (complete ? "Rendering complete" : "Preparing Next Shot...")}
        title="Preparing Next Shot..."
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
        {error && <p className="photoshoot-state photoshoot-state--error" role="alert">{error}</p>}
      </LiveProgressPanel>
    </section>
  );
}
