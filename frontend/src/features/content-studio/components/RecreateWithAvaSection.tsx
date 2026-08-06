import { ImageIcon, UploadCloud } from "lucide-react";
import { useEffect, useRef, useState, type ClipboardEvent, type DragEvent } from "react";
import { analyzeInspirationScene, enhanceCreativeTags, type InspirationSceneAnalysis } from "../../../infrastructure/api/contentStudioApi";
import type { RecreateRuntimeState } from "../types/recreateRuntime";

type Props = { disabled: boolean; onGenerate: (source: string, enhanced: string) => Promise<void>; onRuntimeChange: (state: RecreateRuntimeState) => void; onRuntimeReset: () => void };
type Dimensions = { width: number; height: number } | null;
const ACCEPT = ".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp";
const SUPPORTED_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);
function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function RecreateWithAvaSection({ disabled, onGenerate, onRuntimeChange, onRuntimeReset }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const runningRef = useRef(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [dimensions, setDimensions] = useState<Dimensions>(null);
  const [dragging, setDragging] = useState(false);
  const [analysis, setAnalysis] = useState<InspirationSceneAnalysis | null>(null);
  const [, setEnhanced] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!file) { setPreview(""); setDimensions(null); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    const image = new Image();
    image.onload = () => setDimensions({ width: image.naturalWidth, height: image.naturalHeight });
    image.src = url;
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const serialize = (value: InspirationSceneAnalysis) => [
    `Scene: ${value.scene}`, `Pose: ${value.pose}`, `Camera Angle: ${value.camera_angle}`,
    `Camera Framing: ${value.camera_framing}`, `Lighting: ${value.lighting}`,
    `Composition: ${value.composition}`, `Wardrobe: ${value.wardrobe_concept}`,
    `Expression: ${value.expression}`, `Mood: ${value.mood}`, `Environment: ${value.environment}`,
    `Color Palette: ${value.color_palette}`, `Styling: ${value.styling}`,
    `Elements To Preserve: ${value.elements_to_preserve.join(", ")}`,
    `Elements To Ignore: ${value.elements_to_ignore.join(", ")}`,
    "Identity Transfer Prohibited: true", "Subject identity: Ava via active canonical reference only",
  ].join("\n");

  const choose = (next: File | null) => {
    if (next && !SUPPORTED_TYPES.has(next.type)) { setError("Use one PNG, JPG, JPEG, or WEBP image."); return; }
    setFile(next); setAnalysis(null); setEnhanced(""); setError(""); onRuntimeReset();
    if (!next && inputRef.current) inputRef.current.value = "";
  };
  const drop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault(); setDragging(false);
    if (!disabled && !running) choose(event.dataTransfer.files[0] ?? null);
  };
  const paste = (event: ClipboardEvent<HTMLDivElement>) => {
    if (disabled || running) return;
    const imageItem = Array.from(event.clipboardData.items).find((item) => item.type.startsWith("image/"));
    const pasted = imageItem?.getAsFile();
    if (!pasted) return;
    event.preventDefault();
    const extension = pasted.type === "image/jpeg" ? "jpg" : pasted.type === "image/webp" ? "webp" : "png";
    choose(pasted.name ? pasted : new File([pasted], `clipboard-image.${extension}`, { type: pasted.type }));
  };
  const recreate = async () => {
    if (!file || disabled || runningRef.current) return;
    runningRef.current = true; setRunning(true); setError("");
    let activeStage = 0;
    try {
      onRuntimeChange({ activeStage: 0, message: "Uploading reference image", state: "running" });
      await Promise.resolve();
      activeStage = 1; onRuntimeChange({ activeStage, message: "Analyzing uploaded image", state: "running" });
      const value = await analyzeInspirationScene(file);
      setAnalysis(value);
      const direction = serialize(value);
      activeStage = 2; onRuntimeChange({ activeStage, message: "Building creative direction", state: "running" });
      await Promise.resolve();
      const enhancedDirection = await enhanceCreativeTags(direction, false, undefined, { origin: "recreate_with_ava" });
      setEnhanced(enhancedDirection);
      activeStage = 3; onRuntimeChange({ activeStage, message: "Generating canonical prompt", state: "running" });
      activeStage = 4;
      await onGenerate(direction, enhancedDirection);
      onRuntimeChange({ activeStage: 6, message: "Generation complete", state: "complete" });
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : "Recreate With Ava failed. Please retry.";
      const stage = detail.includes("canonical prompt") ? 3 : activeStage;
      const message = stage === 1 ? "Failed while analyzing uploaded image." : stage === 2 ? "Failed while generating creative direction." : stage === 3 ? "Failed while creating canonical prompt." : detail;
      if (stage < 4) onRuntimeChange({ activeStage: stage, failedStage: stage, message, state: "failed" });
    } finally {
      runningRef.current = false; setRunning(false);
    }
  };
  const send = () => { if (!analysis) return; sessionStorage.setItem("creator-os:photoshoot-scene", serialize(analysis)); window.location.assign("/studios/photoshoot"); };

  return <section className="creative-director-tools recreate-with-ava" aria-labelledby="recreate-with-ava-title">
    <h3 id="recreate-with-ava-title">Recreate With Ava</h3><p>Upload an inspiration image. Creator_OS analyzes the scene, removes subject identity, injects Ava, enhances the concept, and generates new images.</p>
    <div className={`recreate-upload${dragging ? " recreate-upload--dragging" : ""}${disabled || running ? " recreate-upload--disabled" : ""}`} onClick={(event) => { if (!disabled && !running) { event.currentTarget.focus(); inputRef.current?.click(); } }} onDragEnter={(event) => { event.preventDefault(); if (!disabled && !running) setDragging(true); }} onDragLeave={(event) => { event.preventDefault(); if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false); }} onDragOver={(event) => event.preventDefault()} onDrop={drop} onPaste={paste} role="button" tabIndex={disabled || running ? -1 : 0} onKeyDown={(event) => { if (!disabled && !running && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); inputRef.current?.click(); } }} aria-label={file ? "Replace inspiration image" : "Upload inspiration image"} aria-disabled={disabled || running}>
      <input ref={inputRef} className="recreate-upload__input" aria-label="Inspiration image" accept={ACCEPT} disabled={disabled || running} type="file" onChange={(event) => choose(event.target.files?.[0] ?? null)} />
      {!file ? <div className="recreate-upload__empty"><span className="recreate-upload__icon"><UploadCloud aria-hidden="true" /></span><strong>Drag &amp; Drop, Paste (Ctrl+V), or Click to Browse</strong><small>PNG, JPG, JPEG or WEBP · One image</small></div> : <div className="recreate-upload__preview">{preview && <img alt="Inspiration preview" src={preview} />}<div className="recreate-upload__details"><ImageIcon aria-hidden="true" /><div><strong>{file.name}</strong><span>{dimensions ? `${dimensions.width} × ${dimensions.height} · ` : ""}{formatSize(file.size)}</span></div></div></div>}
    </div>
    {file && <div className="recreate-upload__actions"><button disabled={running} type="button" onClick={() => choose(null)}>Remove</button><button disabled={running} type="button" onClick={() => inputRef.current?.click()}>Replace</button></div>}
    <div className="recreate-with-ava__primary-action"><button disabled={disabled || !file || running} onClick={() => void recreate()} type="button">{running ? "Recreating With Ava…" : "Recreate With Ava"}</button></div>
    {error && <p role="alert">{error}</p>}
    {analysis && <details className="recreate-with-ava__options"><summary>More Options</summary><p>Ava remains the subject. The uploaded image supplies creative inspiration only.</p><button disabled={disabled || running} onClick={send} type="button">Send to Photoshoot</button></details>}
  </section>;
}
