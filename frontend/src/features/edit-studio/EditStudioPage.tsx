import { ImagePlus, Pencil, Scissors, Sparkles, Video } from "lucide-react";
import { memo, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { PageHeader } from "../../shared/ui/PageHeader";
import {
  approveEditCandidate,
  discardEditCandidate,
  editCandidateAgain,
  generateEdit,
  getEditGenerationStatus,
  getEditStudioReferences,
  returnEditStudioToLibrary,
  uploadEditStudioReference,
  useAsPhotoshootTeaser,
} from "../../infrastructure/api/editStudioApi";
import { LibraryImage } from "../generation-library/LibraryImage";
import type { GenerationRecord } from "../generation-library/types";
import type {
  EditMode,
  EditStudioReferenceAsset,
  EditStudioReferenceDraft,
  ReferenceSource,
} from "./types";
import { useEditStudio } from "./useEditStudio";
import "./edit-studio.css";
import { videoStudioLink } from "../../infrastructure/api/videoStudioApi";
import { CropTool } from "./QuickEditWorkspace";
import { quickEditTools } from "./quickEditTools";

let nextReferenceId = 0;
const StableSourceImage = memo(LibraryImage);

export function EditStudioPage() {
  const navigate = useNavigate();
  const { context, loading, error } = useEditStudio();
  const [editMode, setEditMode] = useState<EditMode | null>(null);
  const [editPath, setEditPath] = useState<"chooser" | "quick" | "crop" | "ai">("chooser");
  const [provider, setProvider] = useState("");
  const [prompt, setPrompt] = useState("");
  const [references, setReferences] = useState<EditStudioReferenceDraft[]>([]);
  const [referenceAssets, setReferenceAssets] = useState<EditStudioReferenceAsset[]>([]);
  const [referencesLoading, setReferencesLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [generationJobId, setGenerationJobId] = useState("");
  const [candidate, setCandidate] = useState<GenerationRecord | null>(null);
  const [workingSource, setWorkingSource] = useState<GenerationRecord | null>(null);
  const sourceImageId = context?.status === "ready" ? context.pendingImage.image_id : "";
  const teaserIntentId = context?.status === "ready" && context.pendingImage.generation_metadata.purpose === "PHOTOSHOOT_SESSION_TEASER"
    ? String(context.pendingImage.generation_metadata.teaser_intent_id || "") : "";
  const lastSourceImageId = useRef("");

  useLayoutEffect(() => {
    if (context?.status !== "ready") return;
    if (lastSourceImageId.current === context.pendingImage.image_id) return;
    lastSourceImageId.current = context.pendingImage.image_id;
    setEditMode(null);
    setEditPath("chooser");
    setProvider(context.providers[0]?.value || "");
    setPrompt("");
    setReferences([]);
    setBusy(false);
    setActionError("");
    setActionMessage("");
    setGenerationJobId("");
    setCandidate(context.candidateImage);
    setWorkingSource(context.pendingImage);
  }, [context, sourceImageId]);

  useEffect(() => {
    if (!generationJobId) return undefined;
    const controller = new AbortController();
    let timer: number | undefined;
    const poll = async () => {
      try {
        const status = await getEditGenerationStatus(generationJobId, controller.signal);
        if (status.candidate) {
          setCandidate(status.candidate);
          setGenerationJobId("");
          setActionMessage("Edit generated. Review before approving.");
          return;
        }
        if (["failed", "cancelled"].includes(status.generationStatus)) {
          setGenerationJobId("");
          setActionError(status.error || `Edit generation ${status.generationStatus}.`);
          return;
        }
        timer = window.setTimeout(poll, 750);
      } catch (pollError) {
        if ((pollError as { name?: string }).name === "AbortError") return;
        setGenerationJobId("");
        setActionError(pollError instanceof Error ? pollError.message : "Unable to check edit generation.");
      }
    };
    void poll();
    return () => {
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [generationJobId]);

  useEffect(() => {
    const defaultProvider = context?.providers[0];
    if (defaultProvider && !provider) {
      setProvider(defaultProvider.value);
    }
  }, [context, provider]);

  useEffect(() => {
    if (context?.status !== "ready") return undefined;
    const controller = new AbortController();
    getEditStudioReferences(controller.signal)
      .then((assets) => {
        setReferenceAssets(assets);
        setReferencesLoading(false);
      })
      .catch((loadError: unknown) => {
        if ((loadError as { name?: string }).name !== "AbortError") {
          console.error("Unable to load Edit Studio references", loadError);
          setReferencesLoading(false);
        }
      });
    return () => controller.abort();
  }, [context?.status]);

  const incompleteReference = references.some((reference) => (
    reference.source === "upload" ? !reference.file && !reference.assetId : !reference.assetId
  ));
  const generationRunning = Boolean(generationJobId);
  const generateDisabled = busy || generationRunning || !prompt.trim() || !provider || (
    editMode === "multi_image" && incompleteReference
  );

  function addReference() {
    setReferences((current) => [...current, {
      id: `edit-reference-${++nextReferenceId}`,
      source: "reference_library",
      assetId: null,
      file: null,
    }]);
  }

  function updateReference(id: string, update: Partial<EditStudioReferenceDraft>) {
    setReferences((current) => current.map((reference) => (
      reference.id === id ? { ...reference, ...update } : reference
    )));
  }

  async function handleReturnToLibrary() {
    setBusy(true);
    setActionError("");
    try {
      await returnEditStudioToLibrary();
      setReferences([]);
      setEditMode(null);
      setPrompt("");
      navigate("/library/generations");
    } catch (returnError) {
      setActionError(returnError instanceof Error ? returnError.message : "Unable to return image to Generation Library.");
    } finally {
      setBusy(false);
    }
  }

  async function handleGenerateEdit() {
    if (!context || context.status !== "ready" || !workingSource || !editMode || generateDisabled) return;
    setBusy(true);
    setActionError("");
    setActionMessage("");
    try {
      const resolvedReferences = [];
      for (const reference of editMode === "multi_image" ? references : []) {
        let assetId = reference.assetId;
        if (!assetId && reference.file) {
          const uploaded = await uploadEditStudioReference(reference.file);
          assetId = uploaded.assetId;
          setReferenceAssets((current) => [uploaded, ...current.filter((item) => item.assetId !== uploaded.assetId)]);
          updateReference(reference.id, { assetId });
        }
        if (!assetId) throw new Error("Select an image for every reference row.");
        resolvedReferences.push({ source: reference.source, assetId });
      }
      const result = await generateEdit({
        sourceImageId: workingSource.image_id,
        originalSourceImageId: context.pendingImage.image_id,
        editMode,
        providerId: provider,
        prompt: prompt.trim(),
        references: resolvedReferences,
      });
      setActionMessage(result.message);
      setGenerationJobId(result.generation_job_id);
    } catch (generateError) {
      setActionError(generateError instanceof Error ? generateError.message : "Unable to generate edit.");
    } finally {
      setBusy(false);
    }
  }

  async function handleReviewAction(action: "approve" | "edit_again" | "discard") {
    if (!candidate || busy) return;
    setBusy(true);
    setActionError("");
    try {
      if (action === "approve") {
        const approved = await approveEditCandidate(candidate.image_id);
        if (context?.status !== "ready" || approved.updatedRecord.image_id !== context.pendingImage.image_id) {
          throw new Error("Approved edit did not replace the expected Generation Library record.");
        }
        navigate("/library/generations");
        return;
      }
      if (action === "edit_again") {
        const nextSource = await editCandidateAgain(candidate.image_id);
        setWorkingSource(nextSource);
        setCandidate(null);
        setEditMode(null);
        setPrompt("");
        setReferences([]);
        setActionMessage("Continue editing the approved candidate.");
        return;
      }
      const result = await discardEditCandidate(candidate.image_id);
      setCandidate(null);
      setWorkingSource(context?.status === "ready" ? context.pendingImage : null);
      setActionMessage(result.message);
    } catch (reviewError) {
      setActionError(reviewError instanceof Error ? reviewError.message : "Unable to update edit candidate.");
    } finally {
      setBusy(false);
    }
  }

  async function handleUseAsTeaser() {
    if (!candidate || !teaserIntentId || busy) return;
    setBusy(true); setActionError("");
    try {
      const result = await useAsPhotoshootTeaser(teaserIntentId, candidate.image_id);
      navigate(`/library/assets?assetType=photoshoots&photoshoot=${encodeURIComponent(result.deliverableId)}&teaserAdded=1`);
    } catch (useError) {
      setActionError(useError instanceof Error ? useError.message : "Unable to add the Session teaser.");
    } finally { setBusy(false); }
  }

  return (
    <section className="edit-studio">
      <PageHeader
        title={teaserIntentId ? "Edit Studio · Session Teaser" : "Edit Studio"}
        description={teaserIntentId ? "Create a safer opening image, then return it to the originating Photoshoot." : "Quick image adjustments and AI-powered editing workflows."}
      />

      {loading && <div className="edit-studio__state" role="status">Loading Edit Studio…</div>}
      {error && <div className="edit-studio__state edit-studio__state--error" role="alert">{error}</div>}
      {!loading && !error && context?.status === "profile_missing" && (
        <div className="edit-studio__state" role="alert">Creator Profile required before using Edit Studio.</div>
      )}
      {!loading && !error && context?.status === "image_missing" && (
        <div className="edit-studio__state">Choose an image in Generation Library and click ✏️ Edit to start.</div>
      )}

      {!loading && !error && context?.status === "ready" && (
        <div className="edit-studio__workflow">
          {actionError && <p className="edit-studio__action-error" role="alert">{actionError}</p>}
          {actionMessage && <p className="edit-studio__action-success" role="status">{actionMessage}</p>}
          {candidate ? (
            <section className="edit-studio__section edit-studio__review" aria-label="Edit candidate review">
              <div className="edit-studio__review-grid">
                <div><h2>Original Image</h2><div className="edit-studio__review-image"><StableSourceImage priority record={context.pendingImage} /></div></div>
                <div><h2>Edited Candidate</h2><div className="edit-studio__review-image"><LibraryImage priority record={candidate} /></div></div>
              </div>
              <div className="edit-studio__review-actions">
                {teaserIntentId ? <button className="edit-studio__primary" disabled={busy} onClick={() => void handleUseAsTeaser()} type="button">Use as Photoshoot Teaser</button> : <button className="edit-studio__primary" disabled={busy} onClick={() => void handleReviewAction("approve")} type="button">Approve</button>}
                <button className="edit-studio__secondary" disabled={busy} onClick={() => void handleReviewAction("edit_again")} type="button">Edit Again</button>
                <button className="edit-studio__remove-reference" disabled={busy} onClick={() => void handleReviewAction("discard")} type="button">Discard</button>
              </div>
            </section>
          ) : (<>
          <section className="edit-studio__section" aria-labelledby="edit-source-title">
            <h2 id="edit-source-title">Selected Source Image</h2>
            <div className="edit-studio__source-image"><StableSourceImage priority record={workingSource || context.pendingImage} /></div>
            <button className="edit-studio__secondary" disabled={busy || generationRunning} onClick={handleReturnToLibrary} type="button">Return to Library</button>
            {workingSource && workingSource.image_id !== context.pendingImage.image_id && <button className="edit-studio__secondary" disabled={busy || generationRunning} onClick={() => navigate(videoStudioLink({ type: "edit_result", id: workingSource.image_id, previewUrl: workingSource.image_url, label: "Approved edit" }))} type="button"><Video size={16} /> Create Video</button>}
          </section>

          {generationRunning && <section className="edit-studio__section edit-studio__generation" aria-live="polite"><span className="edit-studio__spinner" aria-hidden="true" /><div><h2>Generating Edit...</h2><p>{context.providers.find((item) => item.value === provider)?.label || provider}</p></div></section>}

          {editPath === "chooser" && <section className="edit-studio__section" aria-labelledby="edit-type-title">
            <h2 id="edit-type-title">Choose Edit Type</h2>
            <div className="edit-studio__mode-grid">
              <button className="edit-studio__mode" disabled={generationRunning} onClick={() => setEditPath("quick")} type="button">
                <Scissors aria-hidden="true" size={21} /><span><strong>Quick Edit</strong><small>Crop, resize, rotate &amp; other image adjustments</small><small>No AI generation</small></span>
              </button>
              <button className="edit-studio__mode" disabled={generationRunning} onClick={() => setEditPath("ai")} type="button">
                <Sparkles aria-hidden="true" size={22} /><span><strong>AI Edit</strong><small>Edit or transform images with AI</small><small>AI-powered</small></span>
              </button>
            </div>
          </section>}

          {editPath === "quick" && <section className="edit-studio__section" aria-labelledby="quick-edit-title"><div className="edit-studio__nested-heading"><div><h2 id="quick-edit-title">Choose Quick Edit Tool</h2><p>Deterministic adjustments with no AI generation.</p></div><button className="edit-studio__secondary" onClick={() => setEditPath("chooser")} type="button">Back to Edit Types</button></div><div className="edit-studio__mode-grid">{quickEditTools.map((tool) => <button className="edit-studio__mode" key={tool.id} onClick={() => setEditPath(tool.id)} type="button"><tool.icon aria-hidden="true" size={21} /><span><strong>{tool.title}</strong><small>{tool.description}</small></span></button>)}</div></section>}

          {editPath === "crop" && workingSource && <CropTool source={workingSource} onBack={() => setEditPath("quick")} onApplied={(message) => { setActionMessage(message); navigate("/library/generations"); }} />}

          {editPath === "ai" && <section className="edit-studio__section" aria-labelledby="ai-edit-title"><div className="edit-studio__nested-heading"><div><h2 id="ai-edit-title">Choose AI Edit Type</h2></div><button className="edit-studio__secondary" onClick={() => { setEditMode(null); setEditPath("chooser"); }} type="button">Back to Edit Types</button></div><div className="edit-studio__mode-grid">
            <button aria-pressed={editMode === "single_image"} className="edit-studio__mode" disabled={generationRunning} onClick={() => setEditMode("single_image")} type="button"><Pencil aria-hidden="true" size={21} /><span><strong>Single Edit</strong><small>Edit this image</small></span></button>
            <button aria-pressed={editMode === "multi_image"} className="edit-studio__mode" disabled={generationRunning} onClick={() => setEditMode("multi_image")} type="button"><ImagePlus aria-hidden="true" size={22} /><span><strong>Multi Edit</strong><small>Use one or more reference images</small></span></button>
          </div></section>}

          {editPath === "ai" && editMode && (
            <section className="edit-studio__section edit-studio__form" aria-label={editMode === "single_image" ? "Single Edit controls" : "Multi Edit controls"}>
              <fieldset className="edit-studio__form-fields" disabled={generationRunning}>
              <label><span>Provider</span><select onChange={(event) => setProvider(event.target.value)} value={provider}>
                {context.providers.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select></label>

              {editMode === "multi_image" && (
                <div className="edit-studio__reference">
                  <div className="edit-studio__reference-heading"><h3>Reference Images</h3><button className="edit-studio__secondary" onClick={addReference} type="button">+ Add Reference</button></div>
                  <p className="edit-studio__reference-empty">Optional. Add one or more reference images to guide the edit.</p>
                  {!referencesLoading && referenceAssets.length === 0 && <p className="edit-studio__reference-empty edit-studio__reference-empty--notice">No creative reference images available.<br />Use Upload to add one.</p>}
                  {references.map((reference, index) => {
                    const selected = referenceAssets.find((asset) => asset.assetId === reference.assetId);
                    return (
                      <div className="edit-studio__reference-row" key={reference.id}>
                        <h4>Reference Image {index + 1}</h4>
                        <label><span>Source</span><select aria-label={`Reference ${index + 1} Asset Source`} onChange={(event) => updateReference(reference.id, { source: event.target.value as ReferenceSource, assetId: null, file: null })} value={reference.source}>
                          <option value="reference_library">Reference Library</option><option value="upload">Upload</option>
                        </select></label>
                        {reference.source === "reference_library" ? (
                          <label><span>Reference Image</span><select aria-label={`Reference ${index + 1} Reference Image`} onChange={(event) => updateReference(reference.id, { assetId: Number(event.target.value) || null })} value={reference.assetId ?? ""}>
                            <option value="">Select a reference image...</option>{referenceAssets.map((asset) => <option key={asset.assetId} value={asset.assetId}>{asset.label}</option>)}
                            </select><small>Choose a creative reference from your Reference Library or upload one.</small></label>
                        ) : (
                          <label className="edit-studio__upload"><span>Reference Image</span><input accept="image/jpeg,image/png,image/webp" aria-label={`Reference ${index + 1} Upload`} onChange={(event) => updateReference(reference.id, { file: event.target.files?.[0] || null, assetId: null })} type="file" /><small>Choose a creative reference from your Reference Library or upload one.</small></label>
                        )}
                        <button className="edit-studio__remove-reference" onClick={() => setReferences((current) => current.filter((item) => item.id !== reference.id))} type="button">Remove</button>
                        <div className="edit-studio__reference-selection">{reference.file?.name || selected?.label || "No image selected"}</div>
                      </div>
                    );
                  })}
                </div>
              )}

              <label><span>Prompt</span><textarea onChange={(event) => setPrompt(event.target.value)} placeholder={editMode === "single_image" ? "Describe the exact change. Keep everything else the same." : "Describe how the original image should use the selected reference images."} rows={6} value={prompt} /></label>
              <button className="edit-studio__primary" disabled={generateDisabled} onClick={handleGenerateEdit} type="button">{busy ? "Working…" : "Generate Edit"}</button>
              </fieldset>
            </section>
          )}
          </>)}
        </div>
      )}
    </section>
  );
}
