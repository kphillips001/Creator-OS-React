import { forwardRef, useEffect, useImperativeHandle, useMemo, useState } from "react";

import { createPromptPreview } from "../../../infrastructure/api/contentStudioApi";
import type { PromptPreview, PromptPreviewSignature } from "../types/promptPreview";

type PromptPreviewSectionProps = {
  disabled: boolean;
  signature: PromptPreviewSignature;
  onPromptBatchChange: (prompts: string[]) => void;
};

export type PromptPreviewHandle = {
  buildPrompts: (signature: PromptPreviewSignature) => Promise<void>;
};

function signaturesMatch(left: PromptPreviewSignature, right: PromptPreviewSignature) {
  return left.creativeMode === right.creativeMode
    && left.promptCount === right.promptCount
    && left.creativeTags === right.creativeTags;
}

function promptBatchText(prompts: string[]) {
  return prompts.map((prompt, index) => `Prompt ${index + 1}: ${prompt}`).join("\n\n");
}

export const PromptPreviewSection = forwardRef<PromptPreviewHandle, PromptPreviewSectionProps>(function PromptPreviewSection({
  disabled,
  onPromptBatchChange,
  signature,
}, ref) {
  const [preview, setPreview] = useState<PromptPreview | null>(null);
  const [editedPrompts, setEditedPrompts] = useState<string[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [reviewOpen, setReviewOpen] = useState(false);

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

  useEffect(() => {
    if (!valid) setReviewOpen(false);
  }, [valid]);

  const create = async (regenerate: boolean, requestedSignature = signature) => {
    setPending(true);
    setError("");
    setMessage("");
    try {
      const result = await createPromptPreview(
        requestedSignature.creativeMode,
        requestedSignature.creativeTags,
        requestedSignature.promptCount,
      );
      setPreview(result);
      setEditedPrompts([...result.prompts]);
      setMessage(regenerate ? "Premium Prompt Preview regenerated." : "Premium Prompt Preview created.");
      if (regenerate) setReviewOpen(true);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Prompt Preview failed");
    } finally {
      setPending(false);
    }
  };

  useImperativeHandle(ref, () => ({
    buildPrompts: (requestedSignature) => create(false, requestedSignature),
  }));

  return (
    <>
      <section
        aria-disabled={disabled || undefined}
        aria-label="Generate Prompts"
        className={`workflow-section prompt-preview-launcher${disabled ? " workflow-section--disabled" : ""}`}
      >
        <h2>Generate Prompts</h2>
        <div className="prompt-preview__actions">
          <button disabled={disabled || pending} onClick={() => create(false)} type="button">
            Generate Prompts
          </button>
          {valid && cleanPrompts.length > 0 && (
            <button onClick={() => setReviewOpen(true)} type="button">Review Prompts</button>
          )}
        </div>
        {pending && <p className="prompt-preview__status">Working…</p>}
        {message && <p className="prompt-preview__status">{message}</p>}
        {error && <p className="prompt-preview__status prompt-preview__status--error" role="alert">{error}</p>}
      </section>

      {reviewOpen && valid && preview && (
        <div
          className="prompt-review-modal"
          onMouseDown={(event) => { if (event.target === event.currentTarget) setReviewOpen(false); }}
          role="presentation"
        >
          <section aria-label="Prompt Preview" aria-modal="true" className="prompt-review-modal__dialog prompt-preview" role="dialog">
            <h2>Prompt Preview</h2>
            <p className="prompt-preview__caption">
              These editable prompts are the prompts sent to Generation Engine for this batch.
            </p>
            <div className="prompt-preview__actions">
              <button disabled={pending} onClick={() => create(true)} type="button">
                Regenerate Prompt Preview
              </button>
              {cleanPrompts.length > 0 && (
                <a download="premium_studio_prompt_batch.txt" href={copyHref}>Copy Prompt Batch</a>
              )}
            </div>
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
            {pending && <p className="prompt-preview__status">Working…</p>}
            {message && <p className="prompt-preview__status">{message}</p>}
            {error && <p className="prompt-preview__status prompt-preview__status--error" role="alert">{error}</p>}
            <div className="prompt-review-modal__footer">
              <button onClick={() => setReviewOpen(false)} type="button">Save &amp; Close</button>
            </div>
          </section>
        </div>
      )}
    </>
  );
});
