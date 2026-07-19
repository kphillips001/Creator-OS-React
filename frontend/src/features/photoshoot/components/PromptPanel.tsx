export function PromptPanel({ disabled, prompt, onPrompt }: { disabled: boolean; prompt: string; onPrompt: (value: string) => void }) {
  return <section className="photoshoot-card" aria-labelledby="photoshoot-prompt-title"><header><h2 id="photoshoot-prompt-title">Prompt</h2><span>Manual prompt</span></header><label className="photoshoot-prompt"><span>Prompt Editor</span><textarea disabled={disabled} onChange={(event) => onPrompt(event.target.value)} placeholder="Describe the next shot while preserving the selected continuity settings." value={prompt} /></label></section>;
}
