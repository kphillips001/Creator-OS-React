import { useEffect, useState } from "react";

import { useContentStudioConfiguration } from "../hooks/useContentStudioConfiguration";

const TITLE = "Premium Creative Mode / Prompt Count / Provider";
const STANDARD_MODE_VALUE = "premium_teaser";
const SPICY_MODE_VALUE = "spicy";
const MODE_LABELS: Record<string, string> = {
  [STANDARD_MODE_VALUE]: "Standard",
  [SPICY_MODE_VALUE]: "Spicy",
};

type CreativeConfigurationSectionProps = {
  onCreativeModeChange: (creativeMode: string) => void;
  onPromptCountChange: (promptCount: number) => void;
  onProviderChange: (provider: string) => void;
};

export function CreativeConfigurationSection({
  onCreativeModeChange,
  onPromptCountChange,
  onProviderChange,
}: CreativeConfigurationSectionProps) {
  const { configuration, error, loading } = useContentStudioConfiguration();
  const [mode, setMode] = useState("");
  const [promptCount, setPromptCount] = useState(1);
  const [provider, setProvider] = useState("");

  useEffect(() => {
    if (!configuration) return;
    const nextMode = (
      configuration.defaults.mode === SPICY_MODE_VALUE
        ? SPICY_MODE_VALUE
        : STANDARD_MODE_VALUE
    );
    setMode(nextMode);
    onCreativeModeChange(nextMode);
    setPromptCount(configuration.promptCount.default);
    onPromptCountChange(configuration.promptCount.default);
    setProvider(configuration.defaults.provider);
    onProviderChange(configuration.defaults.provider);
  }, [configuration, onCreativeModeChange, onPromptCountChange, onProviderChange]);

  const updatePromptCount = (value: number) => {
    if (!configuration) return;
    const nextPromptCount = Math.min(
      Math.max(value, configuration.promptCount.minimum),
      configuration.promptCount.maximum,
    );
    setPromptCount(nextPromptCount);
    onPromptCountChange(nextPromptCount);
  };

  const visibleModes = configuration?.modes.filter(
    (option) => option.value in MODE_LABELS,
  ) ?? [];

  return (
    <section className="workflow-section" aria-label={TITLE}>
      <h2>{TITLE}</h2>
      {loading && <p className="creative-configuration__status">Loading creative settings…</p>}
      {error && <p className="creative-configuration__status creative-configuration__status--error" role="alert">{error}</p>}
      {configuration && (
        <div className="creative-configuration">
          <label>
            <span>Premium Creative Mode</span>
            <select
              value={mode}
              onChange={(event) => {
                setMode(event.target.value);
                onCreativeModeChange(event.target.value);
              }}
            >
              {visibleModes.map((option) => (
                <option key={option.value} value={option.value}>{MODE_LABELS[option.value]}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Prompt Count</span>
            <div className="creative-configuration__range">
              <input
                max={configuration.promptCount.maximum}
                min={configuration.promptCount.minimum}
                onChange={(event) => updatePromptCount(Number(event.target.value))}
                type="range"
                value={promptCount}
              />
              <output>{promptCount}</output>
            </div>
          </label>
          <label>
            <span>Provider</span>
            <select value={provider} onChange={(event) => {
              setProvider(event.target.value);
              onProviderChange(event.target.value);
            }}>
              {configuration.providers.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
        </div>
      )}
    </section>
  );
}
