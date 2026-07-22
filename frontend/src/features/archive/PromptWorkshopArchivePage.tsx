import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  getPromptWorkshopArchive,
  markPromptWorkshopPromptUsed,
} from "../../infrastructure/api/contentStudioApi";
import { PageHeader } from "../../shared/ui/PageHeader";
import {
  PROMPT_WORKSHOP_ARCHIVE_HANDOFF_KEY,
  type PromptWorkshopArchiveHandoff,
  type PromptWorkshopBatch,
} from "../content-studio/types/promptWorkshop";
import "./archive.css";

export function PromptWorkshopArchivePage() {
  const navigate = useNavigate();
  const [batches, setBatches] = useState<PromptWorkshopBatch[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [promptNumber, setPromptNumber] = useState(1);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    getPromptWorkshopArchive(controller.signal)
      .then((archive) => {
        setBatches(archive);
        setSelectedBatchId(archive[0]?.batchId ?? "");
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Prompt Workshop archive failed");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  const selectedBatch = useMemo(
    () => batches.find((batch) => batch.batchId === selectedBatchId) ?? null,
    [batches, selectedBatchId],
  );
  const safePromptNumber = Math.min(
    Math.max(1, promptNumber),
    Math.max(1, selectedBatch?.prompts.length ?? 0),
  );

  const handoff = (action: PromptWorkshopArchiveHandoff["action"]) => {
    if (!selectedBatch) return;
    sessionStorage.setItem(PROMPT_WORKSHOP_ARCHIVE_HANDOFF_KEY, JSON.stringify({
      action, batch: selectedBatch, promptNumber: safePromptNumber,
    } satisfies PromptWorkshopArchiveHandoff));
    navigate("/studio/content");
  };

  const useArchived = async () => {
    if (!selectedBatch) return;
    setPending(true);
    setError("");
    setMessage("");
    try {
      await markPromptWorkshopPromptUsed(selectedBatch.batchId, safePromptNumber);
      setBatches((current) => current.map((batch) => (
        batch.batchId === selectedBatch.batchId && !batch.usedPromptNumbers.includes(safePromptNumber)
          ? { ...batch, usedPromptNumbers: [...batch.usedPromptNumbers, safePromptNumber] }
          : batch
      )));
      setMessage("Archived prompt marked as used.");
      handoff("use");
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Prompt Workshop usage update failed");
    } finally {
      setPending(false);
    }
  };

  return (
    <section className="archive-page prompt-workshop-archive">
      <PageHeader
        title="Prompt Workshop Archive"
        description="Browse historical Prompt Workshop batches and their prompts."
      />
      {loading && <p className="prompt-workshop-archive__state">Loading archive…</p>}
      {!loading && !error && batches.length === 0 && (
        <p className="prompt-workshop-archive__state">No Prompt Workshop batches have been archived yet.</p>
      )}
      {selectedBatch && (
        <div className="prompt-workshop-archive__panel">
          <label>
            <span>Archived prompt batch</span>
            <select
              onChange={(event) => {
                setSelectedBatchId(event.target.value);
                setPromptNumber(1);
                setMessage("");
              }}
              value={selectedBatchId}
            >
              {batches.map((batch) => (
                <option key={batch.batchId} value={batch.batchId}>
                  {`${batch.createdAt.slice(0, 19)} | ${batch.lane} | ${batch.requestText.slice(0, 60)}`}
                </option>
              ))}
            </select>
          </label>
          <p className="prompt-workshop-archive__brief">{selectedBatch.requestText}</p>
          <ol>
            {selectedBatch.prompts.map((prompt, index) => (
              <li key={`${selectedBatch.batchId}-${index + 1}`}>
                {selectedBatch.usedPromptNumbers.includes(index + 1) && <strong>used </strong>}
                {prompt}
              </li>
            ))}
          </ol>
          <label className="prompt-workshop-archive__number">
            <span>Archived prompt number</span>
            <input
              max={Math.max(1, selectedBatch.prompts.length)}
              min={1}
              onChange={(event) => setPromptNumber(Number(event.target.value))}
              type="number"
              value={safePromptNumber}
            />
          </label>
          <div className="prompt-workshop-archive__actions">
            <button disabled={pending} onClick={useArchived} type="button">
              {pending ? "Saving…" : "Use Archived"}
            </button>
            <button disabled={pending} onClick={() => handoff("load")} type="button">Load Batch</button>
          </div>
        </div>
      )}
      {message && <p className="prompt-workshop-archive__state">{message}</p>}
      {error && <p className="prompt-workshop-archive__state prompt-workshop-archive__state--error" role="alert">{error}</p>}
    </section>
  );
}
