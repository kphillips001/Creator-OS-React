import { LibraryImage } from "../../generation-library/LibraryImage";
import type { GenerationRecord } from "../../generation-library/types";

export function SeedImageCard({ seed, onReturn }: { seed: GenerationRecord; onReturn: () => void }) {
  return <section className="photoshoot-card photoshoot-seed" aria-labelledby="photoshoot-seed-title"><header><h2 id="photoshoot-seed-title">Selected Seed Image</h2><span>Continuity reference</span></header><div className="photoshoot-seed__image"><LibraryImage priority record={seed} /></div><button className="photoshoot-button photoshoot-button--secondary" onClick={onReturn} type="button">Return to Library</button></section>;
}
