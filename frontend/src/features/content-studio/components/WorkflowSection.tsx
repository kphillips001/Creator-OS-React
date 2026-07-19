type WorkflowSectionProps = {
  disabled?: boolean;
  title: string;
};

export function WorkflowSection({ disabled = false, title }: WorkflowSectionProps) {
  return (
    <section
      aria-disabled={disabled || undefined}
      aria-label={title}
      className={`workflow-section${disabled ? " workflow-section--disabled" : ""}`}
    >
      <h2>{title}</h2>
      <div className="workflow-section__content" />
    </section>
  );
}
