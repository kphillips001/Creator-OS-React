const STAGES = [
  "Understanding Ava",
  "Loading Creative Intelligence",
  "Creating today's inspiration",
  "Building production prompts",
] as const;

type Props = {
  activeStage: number;
};

export function InspirationProgressPanel({ activeStage }: Props) {
  return (
    <section
      aria-label="Inspiration Progress"
      className="workflow-section inspiration-progress"
    >
      <header>
        <p>Autonomous Inspiration</p>
        <h2>Creating today&apos;s ideas</h2>
      </header>
      <ol>
        {STAGES.map((stage, index) => {
          const completed = index < activeStage;
          const active = index === activeStage;
          return (
            <li
              aria-current={active ? "step" : undefined}
              className={completed
                ? "inspiration-progress__stage inspiration-progress__stage--complete"
                : active
                  ? "inspiration-progress__stage inspiration-progress__stage--active"
                  : "inspiration-progress__stage"}
              key={stage}
            >
              <span aria-hidden="true">{completed ? "✓" : active ? "⏳" : "○"}</span>
              <strong>{stage}</strong>
            </li>
          );
        })}
        <li className="inspiration-progress__stage">
          <span aria-hidden="true">○</span>
          <strong>Generating images</strong>
        </li>
      </ol>
    </section>
  );
}
