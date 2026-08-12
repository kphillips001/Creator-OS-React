import { useEffect, useRef, useState } from "react";
import type { BundleTeaserReadiness } from "./types";

type MaskPoint = { x: number; y: number };
type EditorTool = "blur" | "ellipse" | "erase";
type EllipseRegion = { id: number; x: number; y: number; width: number; height: number };
type ResizeHandle = "n" | "ne" | "e" | "se" | "s" | "sw" | "w" | "nw";
type EllipseInteraction = {
  mode: "create" | "move" | "resize"; start: MaskPoint;
  ellipse: EllipseRegion; handle?: ResizeHandle;
};

async function read<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null) as T | { detail?: string } | null;
  if (!response.ok || !body) throw new Error((body as { detail?: string } | null)?.detail || "Unable to save teaser.");
  return body as T;
}

function maskHasPaint(canvas: HTMLCanvasElement): boolean {
  const context = canvas.getContext("2d");
  if (!context?.getImageData) return false;
  const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
  for (let index = 3; index < pixels.length; index += 4) if ((pixels[index] ?? 0) > 0) return true;
  return false;
}

export type SelectiveBlurSavePayload = { sourceAssetId: number; maskData: string; maskWidth: number; maskHeight: number; blurStrength: number };

export function BundleTeaserEditor({ deliverableId, state, sourceAssetId, onClose, onSaved, saveRequest }: {
  deliverableId: string; state: BundleTeaserReadiness; sourceAssetId: number;
  onClose: () => void; onSaved: (value: BundleTeaserReadiness) => void;
  saveRequest?: (payload: SelectiveBlurSavePayload) => Promise<void>;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const previewRef = useRef<HTMLCanvasElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const drawing = useRef(false);
  const interaction = useRef<EllipseInteraction | null>(null);
  const ellipsesRef = useRef<EllipseRegion[]>([]);
  const activeEllipseIdRef = useRef<number | null>(null);
  const nextEllipseId = useRef(1);
  const [tool, setTool] = useState<EditorTool>("blur");
  const [ellipses, setEllipses] = useState<EllipseRegion[]>([]);
  const [activeEllipseId, setActiveEllipseId] = useState<number | null>(null);
  const [maskSize, setMaskSize] = useState({ width: 1, height: 1 });
  const [brushSize, setBrushSize] = useState(40);
  const [blurStrength, setBlurStrength] = useState(state.sourceAssetId === sourceAssetId ? state.blurStrength : 24);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const candidate = state.candidates.find((item) => item.assetId === sourceAssetId)!;

  const replaceEllipses = (values: EllipseRegion[]) => {
    ellipsesRef.current = values;
    setEllipses(values);
  };
  const selectEllipse = (id: number | null) => {
    activeEllipseIdRef.current = id;
    setActiveEllipseId(id);
  };
  const canvas = (width: number, height: number) => {
    const value = document.createElement("canvas");
    value.width = width; value.height = height;
    return value;
  };
  const paintEllipses = (context: CanvasRenderingContext2D, values = ellipsesRef.current) => {
    context.globalCompositeOperation = "source-over";
    context.fillStyle = "#fff";
    values.forEach((ellipse) => {
      if (ellipse.width <= 0 || ellipse.height <= 0) return;
      context.beginPath();
      context.ellipse(
        ellipse.x + ellipse.width / 2, ellipse.y + ellipse.height / 2,
        ellipse.width / 2, ellipse.height / 2, 0, 0, Math.PI * 2,
      );
      context.fill();
    });
  };
  const composedMask = () => {
    const raster = canvasRef.current!;
    const result = canvas(raster.width, raster.height);
    const context = result.getContext("2d")!;
    context.drawImage(raster, 0, 0);
    paintEllipses(context);
    return result;
  };
  const renderPreview = () => {
    const image = imageRef.current, raster = canvasRef.current;
    const preview = previewRef.current;
    if (!image?.naturalWidth || !raster || !preview || !raster.width || !raster.height) return;
    preview.width = raster.width; preview.height = raster.height;
    const context = preview.getContext("2d")!;
    context.clearRect(0, 0, preview.width, preview.height);
    context.globalCompositeOperation = "source-over";
    context.filter = "none";
    context.drawImage(image, 0, 0, preview.width, preview.height);
    const blurred = canvas(preview.width, preview.height);
    const blurredContext = blurred.getContext("2d")!;
    blurredContext.filter = `blur(${blurStrength}px)`;
    blurredContext.drawImage(image, 0, 0, preview.width, preview.height);
    blurredContext.filter = "none";
    const masked = canvas(preview.width, preview.height);
    const maskedContext = masked.getContext("2d")!;
    maskedContext.drawImage(blurred, 0, 0);
    maskedContext.globalCompositeOperation = "destination-in";
    maskedContext.drawImage(composedMask(), 0, 0);
    maskedContext.globalCompositeOperation = "source-over";
    context.drawImage(masked, 0, 0);
  };

  const initialize = () => {
    const image = imageRef.current, maskCanvas = canvasRef.current;
    if (!image || !maskCanvas || !image.naturalWidth) return;
    const scale = Math.min(1, 1024 / image.naturalWidth, 1024 / image.naturalHeight);
    maskCanvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
    maskCanvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
    setMaskSize({ width: maskCanvas.width, height: maskCanvas.height });
    replaceEllipses([]); selectEllipse(null);
    const context = maskCanvas.getContext("2d")!;
    context.clearRect(0, 0, maskCanvas.width, maskCanvas.height);
    if (state.sourceAssetId === sourceAssetId && state.maskUrl) {
      const mask = new Image(); mask.onload = () => {
        context.drawImage(mask, 0, 0, maskCanvas.width, maskCanvas.height);
        renderPreview();
      };
      mask.src = `${state.maskUrl}?v=${Date.now()}`;
    } else renderPreview();
  };
  useEffect(() => initialize(), [sourceAssetId]);
  useEffect(() => renderPreview(), [ellipses, blurStrength, maskSize]);
  const point = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = event.currentTarget, rect = canvas.getBoundingClientRect();
    const x = (event.clientX - rect.left) * canvas.width / rect.width;
    const y = (event.clientY - rect.top) * canvas.height / rect.height;
    return { x: Math.max(0, Math.min(canvas.width, x)),
      y: Math.max(0, Math.min(canvas.height, y)) };
  };
  const paint = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current) return;
    const canvas = event.currentTarget, context = canvas.getContext("2d")!, value = point(event);
    context.globalCompositeOperation = tool === "erase" ? "destination-out" : "source-over";
    context.fillStyle = "#fff"; context.beginPath(); context.arc(value.x, value.y, brushSize / 2, 0, Math.PI * 2); context.fill();
    renderPreview();
  };
  const handles = (ellipse: EllipseRegion): Record<ResizeHandle, MaskPoint> => ({
    n: { x: ellipse.x + ellipse.width / 2, y: ellipse.y },
    ne: { x: ellipse.x + ellipse.width, y: ellipse.y },
    e: { x: ellipse.x + ellipse.width, y: ellipse.y + ellipse.height / 2 },
    se: { x: ellipse.x + ellipse.width, y: ellipse.y + ellipse.height },
    s: { x: ellipse.x + ellipse.width / 2, y: ellipse.y + ellipse.height },
    sw: { x: ellipse.x, y: ellipse.y + ellipse.height },
    w: { x: ellipse.x, y: ellipse.y + ellipse.height / 2 },
    nw: { x: ellipse.x, y: ellipse.y },
  });
  const inside = (value: MaskPoint, ellipse: EllipseRegion) => {
    if (!ellipse.width || !ellipse.height) return false;
    const nx = (value.x - (ellipse.x + ellipse.width / 2)) / (ellipse.width / 2);
    const ny = (value.y - (ellipse.y + ellipse.height / 2)) / (ellipse.height / 2);
    return nx * nx + ny * ny <= 1;
  };
  const updateEllipse = (value: EllipseRegion) => {
    replaceEllipses(ellipsesRef.current.map((item) => item.id === value.id ? value : item));
  };
  const resize = (original: EllipseRegion, handle: ResizeHandle, dx: number, dy: number, width: number, height: number) => {
    const minimum = 4;
    let left = original.x, right = original.x + original.width;
    let top = original.y, bottom = original.y + original.height;
    if (handle.includes("w")) left = Math.max(0, Math.min(right - minimum, original.x + dx));
    if (handle.includes("e")) right = Math.min(width, Math.max(left + minimum, original.x + original.width + dx));
    if (handle.includes("n")) top = Math.max(0, Math.min(bottom - minimum, original.y + dy));
    if (handle.includes("s")) bottom = Math.min(height, Math.max(top + minimum, original.y + original.height + dy));
    return { ...original, x: left, y: top, width: right - left, height: bottom - top };
  };
  const startDrawing = (event: React.PointerEvent<HTMLCanvasElement>) => {
    drawing.current = true;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    if (tool === "ellipse") {
      const start = point(event);
      const active = ellipsesRef.current.find((item) => item.id === activeEllipseIdRef.current);
      const rect = event.currentTarget.getBoundingClientRect();
      const tolerance = 10 * event.currentTarget.width / Math.max(1, rect.width);
      const handle = active && (Object.entries(handles(active)) as [ResizeHandle, MaskPoint][])
        .find(([, value]) => Math.hypot(value.x - start.x, value.y - start.y) <= tolerance)?.[0];
      if (active && handle) {
        interaction.current = { mode: "resize", start, ellipse: { ...active }, handle };
        return;
      }
      const selected = [...ellipsesRef.current].reverse().find((item) => inside(start, item));
      if (selected) {
        selectEllipse(selected.id);
        interaction.current = { mode: "move", start, ellipse: { ...selected } };
        return;
      }
      const created = { id: nextEllipseId.current++, x: start.x, y: start.y, width: 0, height: 0 };
      replaceEllipses([...ellipsesRef.current, created]);
      selectEllipse(created.id);
      interaction.current = { mode: "create", start, ellipse: created };
    } else paint(event);
  };
  const continueDrawing = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current) return;
    if (tool === "ellipse") {
      const current = point(event);
      const action = interaction.current;
      if (!action) return;
      const dx = current.x - action.start.x, dy = current.y - action.start.y;
      if (action.mode === "create") {
        updateEllipse({ ...action.ellipse,
          x: Math.min(action.start.x, current.x), y: Math.min(action.start.y, current.y),
          width: Math.abs(dx), height: Math.abs(dy),
        });
      } else if (action.mode === "move") {
        updateEllipse({ ...action.ellipse,
          x: Math.max(0, Math.min(event.currentTarget.width - action.ellipse.width, action.ellipse.x + dx)),
          y: Math.max(0, Math.min(event.currentTarget.height - action.ellipse.height, action.ellipse.y + dy)),
        });
      } else updateEllipse(resize(action.ellipse, action.handle!, dx, dy, event.currentTarget.width, event.currentTarget.height));
    } else paint(event);
  };
  const finishDrawing = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current) return;
    if (tool === "ellipse") {
      continueDrawing(event);
      const active = ellipsesRef.current.find((item) => item.id === activeEllipseIdRef.current);
      if (active && (active.width < 2 || active.height < 2)) {
        replaceEllipses(ellipsesRef.current.filter((item) => item.id !== active.id));
        selectEllipse(null);
      }
      interaction.current = null;
    }
    drawing.current = false;
  };
  const cancelDrawing = () => { drawing.current = false; interaction.current = null; };
  const flattenEllipses = () => {
    if (!ellipsesRef.current.length) return;
    const raster = canvasRef.current!;
    const context = raster.getContext("2d")!;
    paintEllipses(context);
    replaceEllipses([]); selectEllipse(null);
    renderPreview();
  };
  const selectTool = (value: EditorTool) => {
    cancelDrawing();
    if (value === "erase") flattenEllipses();
    setTool(value);
  };
  const reset = () => {
    const maskCanvas = canvasRef.current!;
    cancelDrawing();
    maskCanvas.getContext("2d")!.clearRect(0, 0, maskCanvas.width, maskCanvas.height);
    replaceEllipses([]); selectEllipse(null); renderPreview();
  };
  const save = async () => {
    const maskCanvas = composedMask();
    if (!maskHasPaint(maskCanvas)) { setError("Paint at least one area to blur before saving."); return; }
    setSaving(true); setError("");
    try {
      const payload = { sourceAssetId, maskData: maskCanvas.toDataURL("image/png"), maskWidth: maskCanvas.width,
        maskHeight: maskCanvas.height, blurStrength };
      if (saveRequest) await saveRequest(payload);
      else {
        const value = await fetch(`/api/v1/assets/photoshoots/${encodeURIComponent(deliverableId)}/bundle-teaser`, {
          method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(payload),
        }).then(read<BundleTeaserReadiness>);
        onSaved(value);
      }
      onClose();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to save teaser."); }
    finally { setSaving(false); }
  };
  return <div className="sale-preparation-dialog bundle-teaser-editor" role="dialog" aria-modal="true" aria-labelledby="teaser-editor-title"><div>
    <header><div><small>Promotional Teaser</small><h2 id="teaser-editor-title">Selective Blur Editor</h2></div></header>
    {error && <p role="alert" className="sale-preparation-error">{error}</p>}
    <div className="bundle-teaser-editor__stage"><img ref={imageRef} src={candidate.imageUrl} onLoad={initialize} alt={`Shot ${candidate.shotOrder} original`} /><canvas ref={previewRef} className="bundle-teaser-editor__preview" aria-label="Live selective blur preview" /><canvas ref={canvasRef} className="bundle-teaser-editor__mask-input" aria-label="Selective blur mask" onPointerDown={startDrawing} onPointerMove={continueDrawing} onPointerUp={finishDrawing} onPointerCancel={cancelDrawing} />{tool === "ellipse" && <svg className="bundle-teaser-editor__ellipse-selection" aria-label="Ellipse selection" viewBox={`0 0 ${maskSize.width} ${maskSize.height}`} width={maskSize.width} height={maskSize.height} preserveAspectRatio="none">{ellipses.map((ellipse) => <g key={ellipse.id} data-ellipse-id={ellipse.id} className={ellipse.id === activeEllipseId ? "is-active" : ""}><ellipse cx={ellipse.x + ellipse.width / 2} cy={ellipse.y + ellipse.height / 2} rx={ellipse.width / 2} ry={ellipse.height / 2} />{ellipse.id === activeEllipseId && Object.entries(handles(ellipse)).map(([name, value]) => <rect aria-label={`Resize ${name}`} key={name} x={value.x - 5} y={value.y - 5} width="10" height="10" />)}</g>)}</svg>}</div>
    <div className="bundle-teaser-editor__controls">
      <div className="bundle-teaser-editor__tools" aria-label="Mask tools">
        <button aria-pressed={tool === "blur"} onClick={() => selectTool("blur")} type="button">Blur Brush</button>
        <button aria-pressed={tool === "ellipse"} onClick={() => selectTool("ellipse")} type="button">Ellipse Blur</button>
        <button aria-pressed={tool === "erase"} onClick={() => selectTool("erase")} type="button">Eraser / Restore</button>
      </div>
      {tool !== "ellipse" && <label>Brush Size <input aria-label="Brush Size" type="range" min="5" max="120" value={brushSize} onChange={(event) => setBrushSize(Number(event.target.value))} /></label>}
      <label>Blur Strength <input aria-label="Blur Strength" type="range" min="1" max="80" value={blurStrength} onChange={(event) => setBlurStrength(Number(event.target.value))} /></label>
      {tool === "erase" && <small>Using Eraser commits current ellipses to the shared mask.</small>}
    </div>
    <footer><button onClick={reset} type="button">Reset</button><button onClick={onClose} type="button">Cancel</button><button disabled={saving} onClick={() => void save()} type="button">{saving ? "Saving..." : "Save Teaser"}</button></footer>
  </div></div>;
}

export function BundlePromotionalTeaser({ deliverableId, initial, onChanged }: { deliverableId: string; initial: BundleTeaserReadiness; onChanged?: (value: BundleTeaserReadiness) => void }) {
  const [state, setState] = useState(initial);
  const [selected, setSelected] = useState(initial.sourceAssetId || initial.candidates[0]?.assetId || null);
  const [editing, setEditing] = useState(false);
  useEffect(() => { setState(initial); setSelected(initial.sourceAssetId || initial.candidates[0]?.assetId || null); }, [initial]);
  return <section className="bundle-promotional-teaser"><header><small>Promotional Teaser</small><h3>{state.statusLabel}</h3></header>
    <p>This separate blurred teaser is promotional only and is not included in the paid Bundle.</p>
    <div className="bundle-teaser-candidates" aria-label="Teaser source images">{state.candidates.map((item) => <button aria-pressed={selected === item.assetId} aria-label={`Select Shot ${item.shotOrder} as teaser source`} key={item.assetId} onClick={() => setSelected(item.assetId)} type="button"><img src={item.imageUrl} alt={`Shot ${item.shotOrder}`} /><span>Shot {item.shotOrder}</span></button>)}</div>
    {state.previewUrl && <div className="bundle-teaser-preview"><strong>Active teaser</strong><img src={`${state.previewUrl}?v=${Date.now()}`} alt="Promotional teaser preview" /></div>}
    <button disabled={!selected} onClick={() => setEditing(true)} type="button">{state.teaserAssetId && selected === state.sourceAssetId ? "Edit Teaser" : "Create Teaser"}</button>
    {editing && selected && <BundleTeaserEditor deliverableId={deliverableId} state={state} sourceAssetId={selected} onClose={() => setEditing(false)} onSaved={(value) => { setState(value); onChanged?.(value); }} />}
  </section>;
}
