import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import { askPromptPlanner } from "../../../infrastructure/api/contentStudioApi";
import type { CanonicalPlannerItem, PromptPlannerHistoryItem } from "../types/promptPlanner";

const ACCEPTED_IMAGES = ".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp";

type CanonicalPromptPlannerSectionProps = {
  disabled: boolean;
  generateDisabled?: boolean;
  generationProgress?: { current: number; total: number } | null;
  onEnhanceAndGenerateIdeas?: (ideas: CanonicalPlannerItem[]) => void;
  processing?: boolean;
};

export type CanonicalPromptPlannerHandle = {
  askAnotherQuestion: () => void;
  continueExploring: () => void;
  startNewSession: () => void;
};

function plainTitle(value: string) {
  return value
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/__(.*?)__/g, "$1")
    .replace(/`(.*?)`/g, "$1")
    .replace(/[*_~]/g, "")
    .trim();
}

export function parsePlannerResponse(answer: string, plannerQuestion: string) {
  const narrative: string[] = [];
  const parsed: Array<{ lineIndex: number; titleLine: string; continuation: string[] }> = [];
  let current: (typeof parsed)[number] | null = null;
  let separated = false;

  answer.split(/\r?\n/).forEach((line, lineIndex) => {
    const match = line.match(/^\s*(?:\d+[.)]|[-*+])\s+(.+?)\s*$/);
    if (match?.[1]) {
      current = { lineIndex, titleLine: match[1], continuation: [] };
      parsed.push(current);
      separated = false;
      return;
    }
    if (!line.trim()) {
      if (current) current.continuation.push("");
      return;
    }
    const globalSection = /^#{1,6}\s+/.test(line)
      || /^```/.test(line.trim())
      || /^\*[^*].*\*$/.test(line.trim())
      || (
      Boolean(current?.continuation.some((item) => item.trim()))
      && /^[A-Z][^.!?]{1,80}:$/.test(line.trim())
    );
    if (!current || separated || globalSection) {
      separated = separated || globalSection;
      narrative.push(line);
      return;
    }
    current.continuation.push(line.trim());
  });

  const ideas = parsed.map((item) => {
    const description = item.continuation.join("\n").trim();
    const title = plainTitle(item.titleLine);
    return {
      description,
      fullText: description ? `${title} — ${description}` : title,
      id: `line-${item.lineIndex}`,
      origin: "canonical_planner" as const,
      plannerQuestion,
      title,
    };
  });
  return { ideas, narrative: narrative.join("\n").trim() };
}

export const CanonicalPromptPlannerSection = forwardRef<CanonicalPromptPlannerHandle, CanonicalPromptPlannerSectionProps>(function CanonicalPromptPlannerSection({
  disabled,
  generateDisabled = false,
  generationProgress = null,
  onEnhanceAndGenerateIdeas,
  processing = false,
}, ref) {
  const [question, setQuestion] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [history, setHistory] = useState<PromptPlannerHistoryItem[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [selectedIdeaIds, setSelectedIdeaIds] = useState<Set<string>>(() => new Set());
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const responsesRef = useRef<HTMLDivElement>(null);
  const selectAllRef = useRef<HTMLInputElement>(null);
  const visibleIdeas = useMemo(() => history.flatMap((item, index) => (
    parsePlannerResponse(item.answer, item.question).ideas.map((idea) => ({
      ...idea,
      id: `${history.length}-${index}-${idea.id}`,
    }))
  )), [history]);
  const allSelected = visibleIdeas.length > 0 && visibleIdeas.every((idea) => selectedIdeaIds.has(idea.id));
  const selectedIdeas = visibleIdeas.filter((idea) => selectedIdeaIds.has(idea.id));

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = selectedIdeas.length > 0 && !allSelected;
    }
  }, [allSelected, selectedIdeas.length]);

  const focusQuestion = () => {
    inputRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  useImperativeHandle(ref, () => ({
    askAnotherQuestion: focusQuestion,
    continueExploring: () => responsesRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
    startNewSession: () => {
      setQuestion("");
      setImage(null);
      setHistory([]);
      setSelectedIdeaIds(new Set());
      setError("");
      if (fileRef.current) fileRef.current.value = "";
      focusQuestion();
    },
  }));

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
        setSelectedIdeaIds(new Set());
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
      <h2>Canonical Prompt Planner Q&amp;A</h2>
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
            <button disabled={pending} onClick={() => { resetForm(); setHistory([]); setSelectedIdeaIds(new Set()); }} type="button">Clear</button>
          </div>
          {error && <p className="canonical-prompt-planner__error" role="alert">{error}</p>}
          {history.length > 0 && (
            <div className="canonical-prompt-planner__history" ref={responsesRef}>
              <h3>Canonical Prompt Planner Responses</h3>
              {visibleIdeas.length > 0 && (
                <div className="canonical-prompt-planner__selection-toolbar">
                  <label>
                    <input
                      checked={allSelected}
                      disabled={processing}
                      onChange={(event) => setSelectedIdeaIds(event.target.checked
                        ? new Set(visibleIdeas.map((idea) => idea.id))
                        : new Set())}
                      ref={selectAllRef}
                      type="checkbox"
                    />
                    <span>Select All</span>
                  </label>
                  <span>Selected: {selectedIdeas.length}</span>
                </div>
              )}
              {history.map((item, index) => {
                const parsed = parsePlannerResponse(item.answer, item.question);
                const ideas = parsed.ideas;
                const narrative = parsed.narrative;
                return (
                <article className="canonical-prompt-planner__response" key={`${history.length}-${index}-${item.question}`}>
                  {item.imageName && <p className="canonical-prompt-planner__image-name">{item.imageName}</p>}
                  <div className="canonical-prompt-planner__response-section">
                    <h4>Question</h4>
                    <p>{item.question}</p>
                  </div>
                  <div className="canonical-prompt-planner__response-section">
                    <h4>Answer</h4>
                    {narrative && <div className="canonical-prompt-planner__markdown">
                      <ReactMarkdown>{narrative}</ReactMarkdown>
                    </div>}
                    {ideas.length > 0 && (
                    <div className="canonical-prompt-planner__recommendations">
                      {ideas.map((idea) => {
                        const ideaId = `${history.length}-${index}-${idea.id}`;
                        return (
                          <label className="canonical-prompt-planner__recommendation" key={ideaId}>
                            <input
                              aria-label={`Select ${idea.fullText}`}
                              checked={selectedIdeaIds.has(ideaId)}
                              disabled={processing}
                              onChange={(event) => setSelectedIdeaIds((current) => {
                                const next = new Set(current);
                                if (event.target.checked) next.add(ideaId);
                                else next.delete(ideaId);
                                return next;
                              })}
                              type="checkbox"
                            />
                            <div className="canonical-prompt-planner__idea-text">
                              <ReactMarkdown>{
                                idea.description
                                  ? `**${idea.title}** — ${idea.description}`
                                  : `**${idea.title}**`
                              }</ReactMarkdown>
                            </div>
                          </label>
                        );
                      })}
                    </div>
                    )}
                  </div>
                </article>
                );
              })}
              {visibleIdeas.length > 0 && (
                <div className="canonical-prompt-planner__bulk-actions">
                  <button
                    className="canonical-prompt-planner__enhance-generate"
                    disabled={disabled || generateDisabled || processing || selectedIdeas.length === 0}
                    onClick={() => onEnhanceAndGenerateIdeas?.(selectedIdeas)}
                    type="button"
                  >
                    {processing ? "Enhancing & Generating…" : `🚀 Enhance & Generate (${selectedIdeas.length})`}
                  </button>
                  <button disabled={processing || selectedIdeas.length === 0} onClick={() => setSelectedIdeaIds(new Set())} type="button">
                    Clear Selection
                  </button>
                  {processing && generationProgress && (
                    <span aria-live="polite">Processing {generationProgress.current} of {generationProgress.total}</span>
                  )}
                </div>
              )}
              <button disabled={pending} onClick={resetForm} type="button">
                Ask Canonical Prompt Planner another question
              </button>
            </div>
          )}
      </div>
    </section>
  );
});
