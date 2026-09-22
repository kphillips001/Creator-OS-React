type ManualPromptSectionProps = {
  disabled: boolean;
  generating: boolean;
  generationDisabled: boolean;
  onChange: (value: string) => void;
  onGenerate: () => void;
  sourceDescription: string;
  value: string;
};

export function ManualPromptSection({
  disabled, generating, generationDisabled, onChange, onGenerate, sourceDescription, value,
}: ManualPromptSectionProps) {
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
      <p className="manual-prompt__source">{sourceDescription}</p>
      <button
        disabled={disabled || generationDisabled || generating || !value.trim()}
        onClick={onGenerate}
        type="button"
      >
        {generating ? "Creating Images..." : "🚀 Create Images from Prompt"}
      </button>
    </section>
  );
}
