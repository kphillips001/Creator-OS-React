import type { PhotoshootProvider, PhotoshootSessionShell } from "../types";

export function PhotoshootSettings({ session, providers, disabled, creativeMode, onMode }: { session: PhotoshootSessionShell; providers: PhotoshootProvider[]; disabled: boolean; creativeMode: string; onMode: (value: "safe" | "premium" | "explicit") => void }) {
  const renderer = providers.find((provider) => provider.value === session.providerId)?.label || session.providerId;
  return (
    <section className="photoshoot-card" aria-labelledby="photoshoot-settings-title">
      <header>
        <h2 id="photoshoot-settings-title">Photoshoot Settings</h2>
        <span>Session controls</span>
      </header>
      <div className="photoshoot-form-grid">
        <div className="photoshoot-renderer">
          <span>Renderer</span>
          <strong>{renderer}</strong>
        </div>
        <fieldset disabled={disabled}>
          <legend>Creative Mode</legend>
          <div className="photoshoot-segmented">
            {(["safe", "premium", "explicit"] as const).map((mode) => (
              <label key={mode}>
                <input checked={creativeMode === mode} name="photoshoot-mode" onChange={() => onMode(mode)} type="radio" />
                <span>{mode.charAt(0).toUpperCase() + mode.slice(1)}</span>
              </label>
            ))}
          </div>
        </fieldset>
      </div>
    </section>
  );
}
