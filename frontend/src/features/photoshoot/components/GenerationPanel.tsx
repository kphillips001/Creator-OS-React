export function GenerationPanel({ disabled, status, provider, onGenerate }: { disabled: boolean; status: string; provider: string; onGenerate: () => void }) {
  return <section className="photoshoot-card photoshoot-generation" aria-labelledby="photoshoot-generation-title"><div><h2 id="photoshoot-generation-title">Generation</h2><p>{status ? `${provider} · ${status}` : "Ready for the next manual shot."}</p></div><button className="photoshoot-button photoshoot-button--primary" disabled={disabled} onClick={onGenerate} type="button">Generate Shot</button></section>;
}
