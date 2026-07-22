import { useEffect, useMemo, useState } from "react";

import {
  generatePromptWorkshopBatch,
  markPromptWorkshopPromptUsed,
} from "../../../infrastructure/api/contentStudioApi";
import {
  PROMPT_WORKSHOP_ARCHIVE_HANDOFF_KEY,
  type PromptWorkshopArchiveHandoff,
  type PromptWorkshopLane,
} from "../types/promptWorkshop";

type PromptWorkshopSectionProps = {
  disabled: boolean;
  onSelectPromptSource: () => void;
  onStoreBatch: (prompts: string[], source: string) => void;
  onUsePrompt: (prompt: string) => void;
  promptCount: number;
};

export function PromptWorkshopSection({
  disabled,
  onSelectPromptSource,
  onStoreBatch,
  onUsePrompt,
  promptCount,
}: PromptWorkshopSectionProps) {
  const [lane, setLane] = useState<PromptWorkshopLane>("premium");
  const [brief, setBrief] = useState("");
  const [batchId, setBatchId] = useState("");
  const [prompts, setPrompts] = useState<string[]>([]);
  const [selectedNumber, setSelectedNumber] = useState(1);
  const [copiedPrompt, setCopiedPrompt] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const serialized = sessionStorage.getItem(PROMPT_WORKSHOP_ARCHIVE_HANDOFF_KEY);
    if (!serialized) return;
    sessionStorage.removeItem(PROMPT_WORKSHOP_ARCHIVE_HANDOFF_KEY);
    try {
      const handoff = JSON.parse(serialized) as PromptWorkshopArchiveHandoff;
      const prompt = handoff.batch.prompts[handoff.promptNumber - 1] ?? "";
      if (handoff.action === "use" && prompt) {
        onUsePrompt(prompt);
        onSelectPromptSource();
        setMessage("Archived prompt selected.");
        return;
      }
      if (handoff.action === "load") {
        setBatchId(handoff.batch.batchId);
        setPrompts([...handoff.batch.prompts]);
        setSelectedNumber(1);
        onStoreBatch(handoff.batch.prompts, "Prompt Workshop Archive");
        setMessage("Archived prompt batch loaded.");
      }
    } catch {
      setError("Archived Prompt Workshop selection could not be loaded.");
    }
  }, [onSelectPromptSource, onStoreBatch, onUsePrompt]);

  const cleanPrompts = useMemo(
    () => prompts.map((prompt) => prompt.trim()).filter(Boolean),
    [prompts],
  );
  const safeSelectedNumber = Math.min(Math.max(1, selectedNumber), Math.max(1, cleanPrompts.length));
  const selectedPrompt = cleanPrompts[safeSelectedNumber - 1] ?? "";

  const run = async (action: () => Promise<void>) => {
    setPending(true);
    setError("");
    setMessage("");
    try {
      await action();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Prompt Workshop failed");
    } finally {
      setPending(false);
    }
  };

  const generate = () => run(async () => {
    const batch = await generatePromptWorkshopBatch(lane, brief, promptCount);
    setBatchId(batch.batchId);
    setPrompts([...batch.prompts]);
    setSelectedNumber(1);
    setCopiedPrompt("");
    onStoreBatch(batch.prompts, "Prompt Workshop");
    setMessage("Prompt Workshop prompts created.");
  });

  const acceptSelected = () => run(async () => {
    if (!selectedPrompt) return;
    if (batchId) await markPromptWorkshopPromptUsed(batchId, safeSelectedNumber);
    onUsePrompt(selectedPrompt);
    onSelectPromptSource();
    setMessage("Selected prompt accepted.");
  });

  const acceptAll = () => {
    onStoreBatch(cleanPrompts, "Prompt Workshop");
    onSelectPromptSource();
    setMessage("Prompt batch accepted.");
  };

  const copyPrompt = async () => {
    setCopiedPrompt(selectedPrompt);
    try {
      await navigator.clipboard?.writeText(selectedPrompt);
      setMessage("Prompt copied.");
    } catch {
      setMessage("Prompt ready to copy below.");
    }
  };

  return (
    <section
      aria-disabled={disabled || undefined}
      aria-label="Prompt Workshop"
      className={`workflow-section prompt-workshop${disabled ? " workflow-section--disabled" : ""}`}
    >
      <h2>Prompt Workshop</h2>
      <p className="prompt-workshop__caption">
        Preview and edit the exact prompts the canonical planner will send to generation.
      </p>

      <div className="prompt-workshop__controls">
        <label>
          <span>Prompt Mode</span>
          <select value={lane} onChange={(event) => setLane(event.target.value as PromptWorkshopLane)}>
            <option value="premium">Premium</option>
            <option value="explicit">Explicit</option>
          </select>
        </label>
        <label className="prompt-workshop__brief">
          <span>Prompt Workshop Brief</span>
          <textarea
            disabled={disabled}
            onChange={(event) => setBrief(event.target.value)}
            placeholder="Example: hotel mirror lingerie set with warm lamp light and playful confidence"
            rows={4}
            value={brief}
          />
        </label>
        <button disabled={disabled || pending || !brief.trim()} onClick={generate} type="button">
          Generate Prompts
        </button>
      </div>

      {prompts.length > 0 && (
        <div className="prompt-workshop__results">
          {prompts.map((prompt, index) => (
            <label key={`${batchId || "draft"}-${index + 1}`}>
              <span>Prompt {index + 1}</span>
              <textarea
                onChange={(event) => setPrompts((current) => current.map((item, itemIndex) => (
                  itemIndex === index ? event.target.value : item
                )))}
                rows={6}
                value={prompt}
              />
            </label>
          ))}
          {cleanPrompts.length === 0 ? (
            <p className="prompt-workshop__warning">At least one Prompt Workshop prompt is required.</p>
          ) : (
            <>
              <label className="prompt-workshop__number">
                <span>Selected prompt</span>
                <input
                  max={cleanPrompts.length}
                  min={1}
                  onChange={(event) => setSelectedNumber(Number(event.target.value))}
                  type="number"
                  value={safeSelectedNumber}
                />
              </label>
              <div className="prompt-workshop__actions">
                <button disabled={pending} onClick={acceptSelected} type="button">Accept Selected</button>
                <button disabled={pending} onClick={acceptAll} type="button">Accept All</button>
                <button disabled={pending} onClick={copyPrompt} type="button">Copy Prompt</button>
              </div>
            </>
          )}
          {copiedPrompt && <pre className="prompt-workshop__copied">{copiedPrompt}</pre>}
        </div>
      )}

      {pending && <p className="prompt-workshop__status">Working…</p>}
      {message && <p className="prompt-workshop__status">{message}</p>}
      {error && <p className="prompt-workshop__status prompt-workshop__status--error" role="alert">{error}</p>}
    </section>
  );
}
