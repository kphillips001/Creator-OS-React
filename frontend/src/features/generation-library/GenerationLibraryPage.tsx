import {
  Archive,
  ArrowLeft,
  ArrowRight,
  Camera,
  CheckSquare,
  ChevronLeft,
  ChevronRight,
  MoveRight,
  Heart,
  Pin,
  Pencil,
  Rocket,
  RotateCw,
  Search,
  Square,
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
  GenerationLibraryCard,
  GenerationLibraryResponse,
  GenerationRecord,
  AssembledPhotoshootImportResponse,
} from "./types";
import { LibraryImage } from "./LibraryImage";
import { PublishDialog } from "./PublishDialog";
import { CreatePhotoshootDialog, type PhotoshootAssembly } from "./CreatePhotoshootDialog";
import { useBackgroundOperations } from "../background-operations/BackgroundOperationsContext";
import { videoStudioLink } from "../../infrastructure/api/videoStudioApi";
import { storeMovedAssetHandoff } from "../asset-library/assetLibraryHandoff";
import "./generation-library.css";

const PHOTOSHOOT_INTAKE_OPERATION_KEY = "creator-os.generation-library.photoshoot-intake-operation";
const GENERATION_LIBRARY_PAGE_SIZE = 24;

const storedPhotoshootIntakeOperation = () => {
  try { return window.sessionStorage.getItem(PHOTOSHOOT_INTAKE_OPERATION_KEY); }
  catch { return null; }
};

const EMPTY_RESULT: GenerationLibraryResponse = {
  records: [],
  total: 0,
  page: 1,
  pageSize: GENERATION_LIBRARY_PAGE_SIZE,
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
  const [contentOrigin, setContentOrigin] = useState("");
  const [page, setPage] = useState(1);
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);
  const [previewRecord, setPreviewRecord] = useState<GenerationRecord | null>(null);
  const [promptCopied, setPromptCopied] = useState(false);
  const [pendingAction, setPendingAction] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [publishRecord, setPublishRecord] = useState<GenerationLibraryCard | null>(null);
  const [libraryVersion, setLibraryVersion] = useState(0);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [assemblyOpen, setAssemblyOpen] = useState(false);
  const [archiveConfirmationOpen, setArchiveConfirmationOpen] = useState(false);
  const [assemblyError, setAssemblyError] = useState("");
  const [intakeOperationId, setIntakeOperationId] = useState<string | null>(storedPhotoshootIntakeOperation);
  const [completedPhotoshoot, setCompletedPhotoshoot] = useState<{ deliverableId: string; count: number } | null>(null);
  const operations = useBackgroundOperations();
  const requestId = useRef(0);
  const actionInFlight = useRef(false);
  const handledIntakeOperations = useRef(new Set<string>());

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
    const params = new URLSearchParams({ page: String(page), sort: "newest" });
    if (search) params.set("search", search);
    if (contentOrigin) params.set("contentOrigin", contentOrigin);
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
  }, [contentOrigin, libraryVersion, page, search]);

  const preview = previewIndex === null ? null : previewRecord;
  const closePreview = useCallback(() => { setPreviewIndex(null); setPreviewRecord(null); }, []);
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
    if (previewIndex === null) return;
    const card = data.records[previewIndex];
    if (!card) { closePreview(); return; }
    const controller = new AbortController();
    setPreviewRecord(null);
    fetch(`/api/v1/generation-library/${encodeURIComponent(card.image_id)}`, {
      cache: "no-store", signal: controller.signal,
    })
      .then(async (response) => {
        const result = await response.json() as GenerationRecord & { detail?: string };
        if (!response.ok) throw new Error(result.detail || "Generation details unavailable");
        return result;
      })
      .then(setPreviewRecord)
      .catch((reason: unknown) => {
        if ((reason as { name?: string }).name !== "AbortError") {
          setError(reason instanceof Error ? reason.message : "Generation details unavailable");
          closePreview();
        }
      });
    return () => controller.abort();
  }, [closePreview, data.records, previewIndex]);

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

  const toggleSelected = (imageId: string) => setSelectedIds(current => {
    const next = new Set(current);
    if (next.has(imageId)) next.delete(imageId); else next.add(imageId);
    return next;
  });

  const selectedImages = useMemo(
    () => data.records.filter((record) => selectedIds.has(record.image_id)),
    [data.records, selectedIds],
  );
  const intakeOperation = useMemo(() => {
    if (intakeOperationId) return [...operations.active, ...operations.recent].find((item) => item.operationId === intakeOperationId) || null;
    return operations.active.find((item) => item.operationType === "assembled_photoshoot_intake"
      && item.originatingWorkspace === "generation_library") || null;
  }, [intakeOperationId, operations.active, operations.recent]);

  useEffect(() => {
    if (!intakeOperation || intakeOperation.status !== "SUCCEEDED") return;
    if (handledIntakeOperations.current.has(intakeOperation.operationId)) return;
    const deliverableId = String(intakeOperation.resultReference || intakeOperation.metadata.deliverable_id || "");
    if (!deliverableId) return;
    handledIntakeOperations.current.add(intakeOperation.operationId);
    const count = Number(intakeOperation.metadata.image_count || Math.max(0, intakeOperation.progressTotal - 2));
    setCompletedPhotoshoot((current) => current?.deliverableId === deliverableId
      ? current : { deliverableId, count });
    setSelectedIds(new Set());
    setAssemblyOpen(false);
    setActionMessage("");
    setLibraryVersion((current) => current + 1);
  }, [intakeOperation]);

  const createPhotoshoot = async (assembly: PhotoshootAssembly) => {
    if (assembly.imageIds.length < 2 || actionInFlight.current) return;
    actionInFlight.current = true;
    setPendingAction("photoshoot-selection");
    setActionMessage("");
    setAssemblyError("");
    try {
      const response = await fetch("/api/v1/generation-library/photoshoots/import", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          imageIds: assembly.imageIds,
          heroImageId: assembly.heroImageId,
          idempotencyKey: `generation-library-photoshoot:${assembly.imageIds.join("|")}`,
        }),
      });
      const result = await response.json() as AssembledPhotoshootImportResponse;
      if (!response.ok) throw new Error(result.detail || "Unable to create Photoshoot.");
      setIntakeOperationId(result.operationId);
      try { window.sessionStorage.setItem(PHOTOSHOOT_INTAKE_OPERATION_KEY, result.operationId); } catch { /* Durable backend state remains authoritative. */ }
      setAssemblyOpen(false);
      setActionMessage("Creating Photoshoot…");
      await operations.refresh();
    } catch (reason) {
      setAssemblyError(reason instanceof Error ? reason.message : "Unable to create Photoshoot.");
    } finally {
      actionInFlight.current = false;
      setPendingAction("");
    }
  };

  const runCardAction = async (record: GenerationLibraryCard, action: GenerationCardAction) => {
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
      if ((action === "move-to-asset-library" || action === "add-to-teasers") && (!Number.isInteger(result.asset_id) || Number(result.asset_id) <= 0)) {
        throw new Error("Asset registration completed without a canonical Asset ID.");
      }
      setActionMessage(result.message || `${action} completed.`);
      if (action === "remove") setLibraryVersion((current) => current + 1);
      if (action === "move-to-asset-library") {
        storeMovedAssetHandoff(result.asset_id!);
        navigate("/library/assets?assetType=images");
        return;
      }
      if (action === "add-to-teasers") {
        storeMovedAssetHandoff(result.asset_id!);
        navigate("/library/assets?assetType=teasers");
        return;
      }
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

  const setPostingStage = async (record: GenerationRecord, staged: boolean) => {
    if (actionInFlight.current) return;
    actionInFlight.current = true;
    setPendingAction(`${record.image_id}:posting-stage`);
    setActionMessage("");
    try {
      const response = await fetch(
        `/api/v1/generation-library/${encodeURIComponent(record.image_id)}/posting-stage`,
        { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ is_staged: staged }) },
      );
      const result = await response.json() as GenerationRecord & { detail?: string };
      if (!response.ok) throw new Error(result.detail || "Unable to update posting stage.");
      setActionMessage(staged ? "Image staged for posting." : "Image unstaged.");
      closePreview();
      setPage(1);
      setLibraryVersion((current) => current + 1);
    } catch (reason) {
      setActionMessage(reason instanceof Error ? reason.message : "Unable to update posting stage.");
    } finally {
      actionInFlight.current = false;
      setPendingAction("");
    }
  };

  const bulkClassifyContent = async (classification: "SFW" | "NSFW") => {
    if (actionInFlight.current || contentOrigin !== "UNCLASSIFIED" || !selectedIds.size) return;
    const imageIds = [...selectedIds];
    actionInFlight.current = true;
    setPendingAction("bulk-classification");
    setActionMessage("");
    try {
      const response = await fetch(
        "/api/v1/generation-library/content-classification/bulk",
        { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ image_ids: imageIds, classification }) },
      );
      const result = await response.json() as { detail?: string };
      if (!response.ok) throw new Error(result.detail || "Unable to classify selected images.");
      setActionMessage(`${imageIds.length} ${imageIds.length === 1 ? "image" : "images"} classified as ${classification}.`);
      setSelectedIds(new Set());
      setSelectionMode(false);
      setLibraryVersion((current) => current + 1);
    } catch (reason) {
      setActionMessage(reason instanceof Error ? reason.message : "Unable to classify selected images.");
    } finally {
      actionInFlight.current = false;
      setPendingAction("");
    }
  };

  const bulkArchiveContent = async () => {
    if (actionInFlight.current || contentOrigin !== "UNCLASSIFIED" || !selectedIds.size) return;
    const imageIds = [...selectedIds];
    actionInFlight.current = true;
    setPendingAction("bulk-archive");
    setActionMessage("");
    try {
      const response = await fetch("/api/v1/generation-library/archive/bulk", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image_ids: imageIds }),
      });
      const result = await response.json() as { detail?: string };
      if (!response.ok) throw new Error(result.detail || "Unable to archive selected images.");
      setArchiveConfirmationOpen(false);
      setActionMessage(`${imageIds.length} ${imageIds.length === 1 ? "image" : "images"} archived.`);
      setSelectedIds(new Set());
      setSelectionMode(false);
      setLibraryVersion((current) => current + 1);
    } catch (reason) {
      setActionMessage(reason instanceof Error ? reason.message : "Unable to archive selected images.");
    } finally {
      actionInFlight.current = false;
      setPendingAction("");
    }
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
        <label className="generation-toolbar__content-filter">
          <span className="sr-only">Content origin</span>
          <select value={contentOrigin} onChange={(event) => { setContentOrigin(event.target.value); setPage(1); }}>
            <option value="">All Content</option>
            <option value="SFW">SFW</option>
            <option value="NSFW">NSFW</option>
            <option value="UNCLASSIFIED">Unclassified</option>
          </select>
        </label>
        <button className={`generation-toolbar__select${selectionMode ? " is-active" : ""}`} onClick={() => { setSelectionMode(value => !value); setSelectedIds(new Set()); }} type="button">
          <CheckSquare size={16} /> {selectionMode ? "Exit Select" : "Select"}
        </button>
      </div>

      {(selectionMode || (intakeOperation && !["SUCCEEDED", "FAILED", "CANCELLED", "PARTIAL"].includes(intakeOperation.status))) && (
        <div className="generation-library__sticky-workspace">
          {selectionMode && <div className="generation-selection" role="toolbar" aria-label="Photoshoot selection">
            <strong>{selectedIds.size} selected</strong>
            <button onClick={() => setSelectedIds(new Set(data.records.map(record => record.image_id)))} type="button">Select All on Page</button>
            <button disabled={!selectedIds.size} onClick={() => setSelectedIds(new Set())} type="button">Clear</button>
            {contentOrigin === "UNCLASSIFIED" && selectedIds.size > 0 && <>
              <button className="generation-selection__classify" disabled={pendingAction === "bulk-classification"} onClick={() => void bulkClassifyContent("SFW")} type="button">Classify SFW</button>
              <button className="generation-selection__classify" disabled={pendingAction === "bulk-classification"} onClick={() => void bulkClassifyContent("NSFW")} type="button">Classify NSFW</button>
              <button className="generation-selection__archive" disabled={pendingAction === "bulk-archive"} onClick={() => setArchiveConfirmationOpen(true)} type="button"><Archive size={15} /> Archive</button>
            </>}
            <button className="generation-selection__move" disabled={selectedIds.size < 2 || pendingAction === "photoshoot-selection" || Boolean(intakeOperation && !["SUCCEEDED", "FAILED", "CANCELLED", "PARTIAL"].includes(intakeOperation.status))} onClick={() => { setAssemblyError(""); setAssemblyOpen(true); }} type="button"><Camera size={16} /> Create Photoshoot</button>
          </div>}
          {intakeOperation && !["SUCCEEDED", "FAILED", "CANCELLED", "PARTIAL"].includes(intakeOperation.status) && <div className="generation-library__photoshoot-operation" role="status"><strong>Creating Photoshoot…</strong><span>{intakeOperation.stageMessage || "Processing selected images"}</span></div>}
        </div>
      )}

      <div className="generation-library__summary">
        <span>{loading ? "Loading library…" : range}</span>
      </div>

      {error && <div className="generation-library__message" role="alert">{error}</div>}
      {actionMessage && (
        <div className="generation-library__action-message" role="status">
          <span>{actionMessage}</span>
          <div><button aria-label="Dismiss message" onClick={() => setActionMessage("")} type="button"><X size={14} /></button></div>
        </div>
      )}
      {intakeOperation?.status === "FAILED" && <div className="generation-library__photoshoot-operation generation-library__photoshoot-operation--error" role="alert"><strong>Photoshoot Needs Attention</strong><span>{intakeOperation.errorMessage || "Photoshoot creation failed. Your images remain in Generation Library."}</span><button onClick={() => void operations.retry(intakeOperation.operationId)} type="button">Retry</button></div>}
      {completedPhotoshoot && <div className="generation-library__photoshoot-success" role="status"><div><strong>✓ Photoshoot Created</strong><span>{completedPhotoshoot.count} images</span></div><button onClick={() => { try { window.sessionStorage.removeItem(PHOTOSHOOT_INTAKE_OPERATION_KEY); } catch { /* Ignore unavailable session storage. */ } navigate(`/library/assets?assetType=photoshoots&photoshoot=${encodeURIComponent(completedPhotoshoot.deliverableId)}`); }} type="button">Open in Asset Library</button></div>}
      {!error && !loading && data.records.length === 0 && (
        <div className="generation-library__message">No generated images match these filters.</div>
      )}
      <div className={`generation-grid${loading ? " generation-grid--loading" : ""}`}>
        {data.records.map((record, index) => {
          return (
            <article className={`generation-card${selectedIds.has(record.image_id) ? " generation-card--selected" : ""}${record.is_staged ? " generation-card--staged" : ""}`} key={record.image_id}>
              {record.is_staged && <span className="generation-card__staged-badge">STAGED</span>}
              {selectionMode && <button aria-label={`${selectedIds.has(record.image_id) ? "Deselect" : "Select"} generation ${record.image_id}`} aria-pressed={selectedIds.has(record.image_id)} className="generation-card__select" onClick={() => toggleSelected(record.image_id)} type="button">{selectedIds.has(record.image_id) ? <CheckSquare /> : <Square />}</button>}
              <button
                aria-label={`Open generation from ${record.provider_id}`}
                className="generation-card__preview"
                onClick={() => selectionMode ? toggleSelected(record.image_id) : setPreviewIndex(index)}
                type="button"
              >
                <LibraryImage priority={index < 4} record={record} />
              </button>
              {!selectionMode && <LibraryActionGroup label="Generation actions">
                <LibraryActionButton icon={Rocket} onClick={() => setPublishRecord(record)} tooltip="Publish" />
                {record.canRegenerate && <LibraryActionButton icon={RotateCw} onClick={() => navigate(`/studio/regeneration?source=${encodeURIComponent(record.image_id)}`)} tooltip="Regenerate from same recipe" />}
                <LibraryActionButton disabled={pendingAction.endsWith(":edit")} icon={Pencil} onClick={() => runCardAction(record, "edit")} tooltip="Edit Image" />
                <LibraryActionButton disabled={pendingAction === `${record.image_id}:photoshoot`} icon={Camera} onClick={() => runCardAction(record, "photoshoot")} tooltip="Create Photoshoot" />
                <LibraryActionButton icon={Video} onClick={() => navigate(videoStudioLink({ type: "generation", id: record.image_id, previewUrl: record.image_url, label: "Generation Library image" }))} tooltip="Create Video" />
                <LibraryActionButton disabled={pendingAction === `${record.image_id}:move-to-asset-library`} icon={MoveRight} onClick={() => runCardAction(record, "move-to-asset-library")} tooltip={pendingAction === `${record.image_id}:move-to-asset-library` ? "Moving / Analyzing" : "Move to Asset Library"} />
                <LibraryActionButton disabled={pendingAction === `${record.image_id}:add-to-teasers`} icon={Heart} onClick={() => runCardAction(record, "add-to-teasers")} tooltip={pendingAction === `${record.image_id}:add-to-teasers` ? "Adding / Analyzing" : "Add to Teasers"} />
                <LibraryActionButton disabled={pendingAction === `${record.image_id}:remove`} icon={Trash2} onClick={() => runCardAction(record, "remove")} tooltip="Remove Content" />
              </LibraryActionGroup>}
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
            <div className="generation-preview__image"><LibraryImage priority record={preview} src={preview.image_url} /></div>
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
              <button
                className={`generation-preview__stage${preview.is_staged ? " is-staged" : ""}`}
                disabled={pendingAction === `${preview.image_id}:posting-stage`}
                onClick={() => void setPostingStage(preview, !preview.is_staged)}
                type="button"
              >
                <Pin size={15} aria-hidden="true" />
                {pendingAction === `${preview.image_id}:posting-stage`
                  ? "Saving…"
                  : preview.is_staged ? "Unstage" : "Stage for Posting"}
              </button>
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
      {assemblyOpen && <CreatePhotoshootDialog
        images={selectedImages}
        busy={pendingAction === "photoshoot-selection"}
        error={assemblyError}
        onCancel={() => { if (pendingAction !== "photoshoot-selection") setAssemblyOpen(false); }}
        onCreate={(value) => void createPhotoshoot(value)}
      />}
      {archiveConfirmationOpen && (
        <div className="generation-archive-confirmation" role="presentation">
          <section aria-labelledby="generation-archive-title" aria-modal="true" role="dialog">
            <h2 id="generation-archive-title">Archive {selectedIds.size} selected {selectedIds.size === 1 ? "image" : "images"}?</h2>
            <p>The selected images will move to Archive / Removed Content and can be restored later.</p>
            <footer>
              <button disabled={pendingAction === "bulk-archive"} onClick={() => setArchiveConfirmationOpen(false)} type="button">Cancel</button>
              <button className="generation-archive-confirmation__submit" disabled={pendingAction === "bulk-archive"} onClick={() => void bulkArchiveContent()} type="button">{pendingAction === "bulk-archive" ? "Archiving…" : "Archive"}</button>
            </footer>
          </section>
        </div>
      )}
    </section>
  );
}
