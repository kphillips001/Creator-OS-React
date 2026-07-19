type ManualPromptSectionProps = {
  disabled: boolean;
  onChange: (value: string) => void;
  value: string;
};

export function ManualPromptSection({ disabled, onChange, value }: ManualPromptSectionProps) {
  return (
    <section
      aria-disabled={disabled || undefined}
      aria-label="Manual Prompt"
      className={`workflow-section manual-prompt${disabled ? " workflow-section--disabled" : ""}`}
    >
      <h2>Manual Prompt</h2>
      <label>
        <span>Manual Prompt</span>
        <textarea
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          placeholder="Optional: paste or edit a complete premium prompt. This bypasses tag enhancement but still uses Generation Engine."
          rows={5}
          value={value}
        />
      </label>
    </section>
  );
}
