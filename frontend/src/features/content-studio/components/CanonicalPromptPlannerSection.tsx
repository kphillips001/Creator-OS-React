import { useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import { askPromptPlanner } from "../../../infrastructure/api/contentStudioApi";
import type { PromptPlannerHistoryItem } from "../types/promptPlanner";

const ACCEPTED_IMAGES = ".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp";

type CanonicalPromptPlannerSectionProps = {
  disabled: boolean;
};

export function CanonicalPromptPlannerSection({ disabled }: CanonicalPromptPlannerSectionProps) {
  const [question, setQuestion] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [history, setHistory] = useState<PromptPlannerHistoryItem[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function resetForm() {
    setQuestion("");
    setImage(null);
    setError("");
    if (fileRef.current) fileRef.current.value = "";
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  async function submit() {
    const submittedQuestion = question.trim();
    if (!submittedQuestion || pending || disabled) return;
    setPending(true);
    setError("");
    try {
      const answer = await askPromptPlanner(submittedQuestion, image);
      if (answer) {
        setHistory((items) => [{
          answer,
          imageName: image?.name ?? "",
          question: submittedQuestion,
        }, ...items]);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Canonical Prompt Planner request failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <section aria-disabled={disabled || undefined} aria-label="Canonical Prompt Planner Q&A" className="workflow-section canonical-prompt-planner">
      <details>
        <summary><h2>Canonical Prompt Planner Q&amp;A</h2></summary>
        <div className="canonical-prompt-planner__content">
          <label>
            <span>Ask Canonical Prompt Planner</span>
            <textarea
              disabled={disabled || pending}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask anything. Example: give me 10 flirty X captions, critique a pose, rewrite a caption, or brainstorm premium shot ideas."
              ref={inputRef}
              rows={5}
              value={question}
            />
          </label>
          <label>
            <span>Add Image</span>
            <input
              accept={ACCEPTED_IMAGES}
              aria-label="Add Image"
              disabled={disabled || pending}
              onChange={(event) => setImage(event.target.files?.[0] ?? null)}
              ref={fileRef}
              type="file"
            />
            <small>Optional. Add an image when you want the planner to analyze it.</small>
          </label>
          <div className="canonical-prompt-planner__actions">
            <button disabled={disabled || pending || !question.trim()} onClick={() => void submit()} type="button">
              {pending ? "Asking Canonical Prompt Planner..." : "Ask Planner"}
            </button>
            <button disabled={pending} onClick={() => { resetForm(); setHistory([]); }} type="button">Clear</button>
          </div>
          {error && <p className="canonical-prompt-planner__error" role="alert">{error}</p>}
          {history.length > 0 && (
            <div className="canonical-prompt-planner__history">
              <h3>Canonical Prompt Planner Responses</h3>
              {history.map((item, index) => (
                <article className="canonical-prompt-planner__response" key={`${history.length}-${index}-${item.question}`}>
                  {item.imageName && <p className="canonical-prompt-planner__image-name">{item.imageName}</p>}
                  <div className="canonical-prompt-planner__response-section">
                    <h4>Question</h4>
                    <p>{item.question}</p>
                  </div>
                  <div className="canonical-prompt-planner__response-section">
                    <h4>Answer</h4>
                    <div className="canonical-prompt-planner__markdown">
                      <ReactMarkdown>{item.answer}</ReactMarkdown>
                    </div>
                  </div>
                  <div className="canonical-prompt-planner__response-actions">
                    <button onClick={() => void navigator.clipboard?.writeText(item.answer)} type="button">Copy</button>
                  </div>
                </article>
              ))}
              <button disabled={pending} onClick={resetForm} type="button">
                Ask Canonical Prompt Planner another question
              </button>
            </div>
          )}
        </div>
      </details>
    </section>
  );
}
