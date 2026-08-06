const STAGES = ["Understanding Ava", "Loading Creative Intelligence", "Creating today's inspiration", "Building production prompts"] as const;

type Props = { activeStage: number; stages?: readonly string[]; eyebrow?: string; title?: string; failedStage?: number };

export function InspirationProgressPanel({ activeStage, stages = STAGES, eyebrow = "Autonomous Inspiration", title = "Creating today's ideas", failedStage }: Props) {
  return <section aria-label="Inspiration Progress" className="workflow-section inspiration-progress">
    <header><p>{eyebrow}</p><h2>{title}</h2></header>
    <ol>{stages.map((stage, index) => {
      const failed = index === failedStage; const completed = index < activeStage; const active = index === activeStage;
      return <li aria-current={active ? "step" : undefined} className={failed ? "inspiration-progress__stage inspiration-progress__stage--failed" : completed ? "inspiration-progress__stage inspiration-progress__stage--complete" : active ? "inspiration-progress__stage inspiration-progress__stage--active" : "inspiration-progress__stage"} key={stage}>
        <span aria-hidden="true">{failed ? "×" : completed ? "✓" : active ? "⏳" : "○"}</span><strong>{stage}</strong>
      </li>;
    })}{stages === STAGES && <li className="inspiration-progress__stage"><span aria-hidden="true">○</span><strong>Generating images</strong></li>}</ol>
  </section>;
}
