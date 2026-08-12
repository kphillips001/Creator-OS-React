import {
  ArrowLeft,
  ArrowRight,
  Camera,
  ChevronLeft,
  ChevronRight,
  MoveRight,
  Pencil,
  Rocket,
  RotateCw,
  Search,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Video,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { LibraryActionButton, LibraryActionGroup } from "../../shared/ui/LibraryActionButton";

import type {
  GenerationActionResponse,
  GenerationCardAction,
  GenerationLibraryResponse,
  GenerationRecord,
} from "./types";
import { LibraryImage } from "./LibraryImage";
import { PublishDialog } from "./PublishDialog";
import { videoStudioLink } from "../../infrastructure/api/videoStudioApi";
import "./generation-library.css";

const EMPTY_RESULT: GenerationLibraryResponse = {
  records: [],
  total: 0,
  page: 1,
  pageSize: 20,
  totalPages: 1,
  providers: [],
  modes: [],
};

const titleCase = (value: string) =>
  value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

const formatDate = (value: string) =>
  new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));

const metadataValue = (record: GenerationRecord, keys: string[]) => {
  for (const metadata of [record.provider_metadata, record.generation_metadata, record.prompt_metadata]) {
    for (const key of keys) {
      const value = metadata?.[key];
      if (typeof value === "string" && value.trim()) return value;
    }
  }
  return "";
};

export function GenerationLibraryPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [data, setData] = useState(EMPTY_RESULT);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [searchDraft, setSearchDraft] = useState("");
  const [search, setSearch] = useState("");
  const [provider, setProvider] = useState("");
  const [mode, setMode] = useState("");
  const [sort, setSort] = useState("newest");
  const [page, setPage] = useState(1);
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);
  const [promptCopied, setPromptCopied] = useState(false);
  const [pendingAction, setPendingAction] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [publishRecord, setPublishRecord] = useState<GenerationRecord | null>(null);
  const [libraryVersion, setLibraryVersion] = useState(0);
  const requestId = useRef(0);
  const actionInFlight = useRef(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchDraft);
      setPage(1);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [searchDraft]);

  useEffect(() => {
    const controller = new AbortController();
    const currentRequest = ++requestId.current;
    const params = new URLSearchParams({ page: String(page), sort });
    if (search) params.set("search", search);
    if (provider) params.set("provider", provider);
    if (mode) params.set("mode", mode);
    setLoading(true);
    setError("");
    fetch(`/api/v1/generation-library?${params}`, { signal: controller.signal })
      .then(async (response) => {
        const result = (await response.json()) as GenerationLibraryResponse;
        if (!response.ok || result.error) throw new Error(result.error || "Library read failed");
        return result;
      })
      .then((result) => {
        if (currentRequest === requestId.current) {
          setData(result);
          setPage(result.page);
        }
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Library read failed");
      })
      .finally(() => {
        if (currentRequest === requestId.current) setLoading(false);
      });
    return () => controller.abort();
  }, [libraryVersion, mode, page, provider, search, sort]);

  const preview = previewIndex === null ? null : data.records[previewIndex];
  const closePreview = useCallback(() => setPreviewIndex(null), []);
  const movePreview = useCallback(
    (step: number) => {
      setPreviewIndex((current) => {
        if (current === null) return current;
        return Math.max(0, Math.min(data.records.length - 1, current + step));
      });
    },
    [data.records.length],
  );

  useEffect(() => {
    if (!preview) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closePreview();
      if (event.key === "ArrowLeft") movePreview(-1);
      if (event.key === "ArrowRight") movePreview(1);
    };
    document.body.classList.add("generation-preview-open");
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.classList.remove("generation-preview-open");
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [closePreview, movePreview, preview]);

  const range = useMemo(() => {
    if (!data.total) return "0 images";
    const start = (data.page - 1) * data.pageSize + 1;
    return `${start}–${Math.min(start + data.records.length - 1, data.total)} of ${data.total}`;
  }, [data]);

  const changePage = (next: number) => {
    setPage(next);
    document.querySelector(".generation-library")?.scrollIntoView({ behavior: "smooth" });
  };

  const runCardAction = async (record: GenerationRecord, action: GenerationCardAction) => {
    if (actionInFlight.current) return;
    actionInFlight.current = true;
    const actionId = `${record.image_id}:${action}`;
    setPendingAction(actionId);
    setActionMessage("");
    try {
      const endpoint = action === "edit"
        ? `/api/v1/generation-library/${encodeURIComponent(record.image_id)}/edit`
        : `/api/v1/generation-library/${encodeURIComponent(record.image_id)}/${action}`;
      const response = await fetch(
        endpoint,
        { method: "POST" },
      );
      const result = (await response.json()) as GenerationActionResponse;
      if (!response.ok) {
        console.error("Generation Library action failed", { action, imageId: record.image_id, status: response.status, detail: result.detail || result.error });
        if (action === "photoshoot") {
          const message = result.detail?.includes("Creator Profile")
            ? "Creator Profile required before starting a Photoshoot."
            : response.status >= 500
              ? "Photoshoot Studio backend unavailable."
              : "Unable to open this image in Photoshoot Studio.";
          throw new Error(message);
        }
        throw new Error(result.detail || result.error || `${action} failed`);
      }
      if (action === "edit" && (
        result.image_id !== record.image_id
        || result.status !== "pending_edit"
        || result.review_state !== "pending_edit"
      )) {
        throw new Error("Edit Studio handoff returned an unexpected source image.");
      }
      if (action === "photoshoot" && (
        result.image_id !== record.image_id
        || result.status !== "pending_photoshoot"
        || !result.session_id
      )) throw new Error("Photoshoot handoff returned an unexpected seed image.");
      setActionMessage(result.message || `${action} completed.`);
      if (action === "remove") setLibraryVersion((current) => current + 1);
      if (action === "move-to-asset-library") setLibraryVersion((current) => current + 1);
      if (result.redirect) navigate(result.redirect);
    } catch (reason: unknown) {
      setActionMessage(reason instanceof Error ? reason.message : `${action} failed`);
    } finally {
      actionInFlight.current = false;
      setPendingAction("");
    }
  };

  const copyPrompt = async () => {
    if (!preview) return;
    await navigator.clipboard.writeText(preview.prompt_text);
    setPromptCopied(true);
    window.setTimeout(() => setPromptCopied(false), 1600);
  };

  return (
    <section className="generation-library" aria-busy={loading}>
      {(location.state as { notification?: string } | null)?.notification && <div className="generation-library-notification" role="status">{(location.state as { notification: string }).notification}</div>}
      <header className="generation-library__header">
        <div>
          <p>Creative workflow</p>
          <h1>Generation Library</h1>
          <span>Your generated media, ready to explore.</span>
        </div>
        <div className="generation-library__count">
          <Sparkles size={15} />
          <strong>{data.total}</strong> images
        </div>
      </header>

      <div className="generation-toolbar">
        <label className="generation-toolbar__search">
          <Search size={17} aria-hidden="true" />
          <span className="sr-only">Search generations</span>
          <input
            onChange={(event) => setSearchDraft(event.target.value)}
            placeholder="Search prompts, providers, or IDs"
            type="search"
            value={searchDraft}
          />
        </label>
        <div className="generation-toolbar__filters">
          <SlidersHorizontal size={16} aria-hidden="true" />
          <label>
            <span className="sr-only">Provider</span>
            <select value={provider} onChange={(event) => { setProvider(event.target.value); setPage(1); }}>
              <option value="">All providers</option>
              {data.providers.map((value) => <option key={value} value={value}>{titleCase(value)}</option>)}
            </select>
          </label>
          <label>
            <span className="sr-only">Creative mode</span>
            <select value={mode} onChange={(event) => { setMode(event.target.value); setPage(1); }}>
              <option value="">All modes</option>
              {data.modes.map((value) => <option key={value} value={value}>{titleCase(value)}</option>)}
            </select>
          </label>
          <label>
            <span className="sr-only">Sort generations</span>
            <select value={sort} onChange={(event) => { setSort(event.target.value); setPage(1); }}>
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="provider">Provider</option>
            </select>
          </label>
        </div>
      </div>

      <div className="generation-library__summary">
        <span>{loading ? "Loading library…" : range}</span>
      </div>

      {error && <div className="generation-library__message" role="alert">{error}</div>}
      {actionMessage && (
        <div className="generation-library__action-message" role="status">
          <span>{actionMessage}</span>
          <button aria-label="Dismiss message" onClick={() => setActionMessage("")} type="button"><X size={14} /></button>
        </div>
      )}
      {!error && !loading && data.records.length === 0 && (
        <div className="generation-library__message">No generated images match these filters.</div>
      )}
      <div className={`generation-grid${loading ? " generation-grid--loading" : ""}`}>
        {data.records.map((record, index) => {
          return (
            <article className="generation-card" key={record.image_id}>
              <button
                aria-label={`Open generation from ${record.provider_id}`}
                className="generation-card__preview"
                onClick={() => setPreviewIndex(index)}
                type="button"
              >
                <LibraryImage priority={index < 4} record={record} />
              </button>
              <LibraryActionGroup label="Generation actions">
                <LibraryActionButton icon={Rocket} onClick={() => setPublishRecord(record)} tooltip="Publish" />
                {record.canRegenerate && <LibraryActionButton icon={RotateCw} onClick={() => navigate(`/studio/regeneration?source=${encodeURIComponent(record.image_id)}`)} tooltip="Regenerate from same recipe" />}
                <LibraryActionButton disabled={pendingAction.endsWith(":edit")} icon={Pencil} onClick={() => runCardAction(record, "edit")} tooltip="Edit Image" />
                <LibraryActionButton disabled={pendingAction === `${record.image_id}:photoshoot`} icon={Camera} onClick={() => runCardAction(record, "photoshoot")} tooltip="Create Photoshoot" />
                <LibraryActionButton icon={Video} onClick={() => navigate(videoStudioLink({ type: "generation", id: record.image_id, previewUrl: record.image_url, label: "Generation Library image" }))} tooltip="Create Video" />
                <LibraryActionButton disabled={pendingAction === `${record.image_id}:move-to-asset-library`} icon={MoveRight} onClick={() => runCardAction(record, "move-to-asset-library")} tooltip={pendingAction === `${record.image_id}:move-to-asset-library` ? "Moving / Analyzing" : "Move to Asset Library"} />
                <LibraryActionButton disabled={pendingAction === `${record.image_id}:remove`} icon={Trash2} onClick={() => runCardAction(record, "remove")} tooltip="Remove Content" />
              </LibraryActionGroup>
            </article>
          );
        })}
      </div>

      {data.totalPages > 1 && (
        <nav className="generation-pagination" aria-label="Generation Library pages">
          <button disabled={data.page <= 1 || loading} onClick={() => changePage(data.page - 1)} type="button">
            <ChevronLeft size={16} /> Previous
          </button>
          <span>Page <strong>{data.page}</strong> of {data.totalPages}</span>
          <button disabled={data.page >= data.totalPages || loading} onClick={() => changePage(data.page + 1)} type="button">
            Next <ChevronRight size={16} />
          </button>
        </nav>
      )}

      {preview && (
        <div className="generation-preview" role="dialog" aria-modal="true" aria-label="Generation preview" onMouseDown={(event) => { if (event.target === event.currentTarget) closePreview(); }}>
          <button className="generation-preview__close" onClick={closePreview} type="button" aria-label="Close preview"><X /></button>
          <button className="generation-preview__previous" disabled={previewIndex === 0} onClick={() => movePreview(-1)} type="button" aria-label="Previous image"><ArrowLeft /></button>
          <div className="generation-preview__content">
            <div className="generation-preview__image"><LibraryImage priority record={preview} /></div>
            <aside className="generation-preview__metadata">
              <div className="generation-preview__prompt">
                <h2>Prompt</h2>
                <p>{preview.prompt_text}</p>
                <button onClick={copyPrompt} type="button">{promptCopied ? "Copied" : "Copy Prompt"}</button>
              </div>
              <dl className="generation-preview__context">
                <div><dt>Provider / model</dt><dd>{titleCase(preview.provider_id)}{metadataValue(preview, ["model", "model_name", "renderer"]) ? ` · ${metadataValue(preview, ["model", "model_name", "renderer"])}` : ""}</dd></div>
                <div><dt>Created</dt><dd>{formatDate(preview.generation_date)}</dd></div>
                <div><dt>Status</dt><dd>{titleCase(preview.status)}</dd></div>
              </dl>
              <small>Use ← and → to browse · Esc to close</small>
            </aside>
          </div>
          <button className="generation-preview__next" disabled={previewIndex === data.records.length - 1} onClick={() => movePreview(1)} type="button" aria-label="Next image"><ArrowRight /></button>
        </div>
      )}
      {publishRecord && (
        <PublishDialog
          onClose={() => setPublishRecord(null)}
          onPublished={(message) => {
            setPublishRecord(null);
            setActionMessage(message);
            setLibraryVersion((current) => current + 1);
          }}
          record={publishRecord}
        />
      )}
    </section>
  );
}
