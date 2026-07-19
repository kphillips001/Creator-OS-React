import { useEffect, useMemo, useState } from "react";

import { createPromptPreview } from "../../../infrastructure/api/contentStudioApi";
import type {
  PromptPreview,
  PromptPreviewSignature,
} from "../types/promptPreview";

type PromptPreviewSectionProps = {
  disabled: boolean;
  signature: PromptPreviewSignature;
  onPromptBatchChange: (prompts: string[]) => void;
};

function signaturesMatch(left: PromptPreviewSignature, right: PromptPreviewSignature) {
  return left.creativeMode === right.creativeMode
    && left.promptCount === right.promptCount
    && left.creativeTags === right.creativeTags;
}

function promptBatchText(prompts: string[]) {
  return prompts.map((prompt, index) => `Prompt ${index + 1}: ${prompt}`).join("\n\n");
}

export function PromptPreviewSection({ disabled, onPromptBatchChange, signature }: PromptPreviewSectionProps) {
  const [preview, setPreview] = useState<PromptPreview | null>(null);
  const [editedPrompts, setEditedPrompts] = useState<string[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const valid = Boolean(preview && signaturesMatch(preview.signature, signature));
  const cleanPrompts = useMemo(
    () => editedPrompts.map((prompt) => prompt.trim()).filter(Boolean),
    [editedPrompts],
  );
  const copyText = promptBatchText(cleanPrompts);
  const copyHref = `data:text/plain;charset=utf-8,${encodeURIComponent(copyText)}`;

  useEffect(() => {
    onPromptBatchChange(valid ? cleanPrompts : []);
  }, [cleanPrompts, onPromptBatchChange, valid]);

  const create = async (regenerate: boolean) => {
    setPending(true);
    setError("");
    setMessage("");
    try {
      const result = await createPromptPreview(
        signature.creativeMode,
        signature.creativeTags,
        signature.promptCount,
      );
      setPreview(result);
      setEditedPrompts([...result.prompts]);
      setMessage(regenerate ? "Premium Prompt Preview regenerated." : "Premium Prompt Preview created.");
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Prompt Preview failed");
    } finally {
      setPending(false);
    }
  };

  return (
    <section
      aria-disabled={disabled || undefined}
      aria-label="Prompt Preview"
      className={`workflow-section prompt-preview${disabled ? " workflow-section--disabled" : ""}`}
    >
      <h2>Prompt Preview</h2>
      <p className="prompt-preview__caption">
        These editable prompts are the prompts sent to Generation Engine for this batch.
      </p>
      <div className="prompt-preview__actions">
        <button disabled={disabled || pending} onClick={() => create(false)} type="button">
          Create Prompt Preview
        </button>
        <button disabled={disabled || pending} onClick={() => create(true)} type="button">
          Regenerate Prompt Preview
        </button>
        {valid && cleanPrompts.length > 0 && (
          <a download="premium_studio_prompt_batch.txt" href={copyHref}>Copy Prompt Batch</a>
        )}
      </div>

      {valid && preview ? (
        <div className="prompt-preview__content">
          {editedPrompts.map((prompt, index) => (
            <label key={`${preview.planId}-${index + 1}`}>
              <span>Prompt {index + 1}</span>
              <textarea
                onChange={(event) => setEditedPrompts((current) => current.map((item, itemIndex) => (
                  itemIndex === index ? event.target.value : item
                )))}
                rows={7}
                value={prompt}
              />
            </label>
          ))}
          <details className="prompt-preview__advanced">
            <summary>Advanced Details</summary>
            <p>Prompt Plan: {preview.planId}</p>
            <p>Creative Mode: {preview.creativeMode}</p>
            <p>{preview.creativeRationale}</p>
            <pre>{JSON.stringify(preview.promptMetadata, null, 2)}</pre>
          </details>
        </div>
      ) : (
        <p className="prompt-preview__empty">
          Prompt Preview is ready when you create, regenerate, or generate images.
        </p>
      )}

      {pending && <p className="prompt-preview__status">Working…</p>}
      {message && <p className="prompt-preview__status">{message}</p>}
      {error && <p className="prompt-preview__status prompt-preview__status--error" role="alert">{error}</p>}
    </section>
  );
}
