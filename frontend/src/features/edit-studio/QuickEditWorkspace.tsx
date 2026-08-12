import { useEffect, useRef, useState } from "react";

import { applyQuickCrop, getQuickEditSourceInfo } from "../../infrastructure/api/editStudioApi";
import type { GenerationRecord } from "../generation-library/types";
import { calculateCropDrag, type CropBox as Box, type CropHandle as Handle } from "./quickEditTools";

const presets = ["Free", "Original", "1:1", "4:5", "3:4", "9:16", "16:9"] as const;

export function CropTool({ source, onBack, onApplied }: { source: GenerationRecord; onBack: () => void; onApplied: (message: string) => void }) {
  const stageRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 1, height: 1 });
  const [box, setBox] = useState<Box>({ x: 0, y: 0, width: 1, height: 1 });
  const [preset, setPreset] = useState<(typeof presets)[number]>("Free");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    getQuickEditSourceInfo(source.image_id).then((info) => {
      if (!active) return;
      const next = { width: info.width, height: info.height };
      setDimensions(next); setBox({ x: 0, y: 0, ...next });
    }).catch((reason) => active && setError(reason instanceof Error ? reason.message : "Unable to inspect source image."));
    return () => { active = false; };
  }, [source.image_id]);

  const reset = () => { setPreset("Free"); setBox({ x: 0, y: 0, ...dimensions }); };
  const choosePreset = (value: (typeof presets)[number]) => {
    setPreset(value);
    if (value === "Free") return;
    const ratio = value === "Original" ? dimensions.width / dimensions.height : ({ "1:1": 1, "4:5": 4 / 5, "3:4": 3 / 4, "9:16": 9 / 16, "16:9": 16 / 9 } as Record<string, number>)[value] ?? 1;
    let width = dimensions.width; let height = Math.round(width / ratio);
    if (height > dimensions.height) { height = dimensions.height; width = Math.round(height * ratio); }
    setBox({ x: Math.round((dimensions.width - width) / 2), y: Math.round((dimensions.height - height) / 2), width, height });
  };

  const beginDrag = (event: React.PointerEvent, handle: Handle) => {
    event.preventDefault();
    const stage = stageRef.current; if (!stage) return;
    const rect = stage.getBoundingClientRect(); const start = { x: event.clientX, y: event.clientY, box };
    const sx = dimensions.width / rect.width; const sy = dimensions.height / rect.height;
    const move = (pointer: PointerEvent) => {
      const dx = Math.round((pointer.clientX - start.x) * sx); const dy = Math.round((pointer.clientY - start.y) * sy);
      setPreset("Free"); setBox(calculateCropDrag(start.box, handle, dx, dy, dimensions));
    };
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  };

  const style = { left: `${box.x / dimensions.width * 100}%`, top: `${box.y / dimensions.height * 100}%`, width: `${box.width / dimensions.width * 100}%`, height: `${box.height / dimensions.height * 100}%` };
  const apply = async () => {
    setBusy(true); setError("");
    try { const result = await applyQuickCrop({ sourceImageId: source.image_id, ...box }); onApplied(result.message); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to apply crop."); setBusy(false); }
  };
  return <section className="edit-studio__section crop-tool" aria-label="Crop tool">
    <div className="edit-studio__nested-heading"><div><h2>Crop</h2><p>Drag an edge, corner, or the crop area itself.</p></div><button className="edit-studio__secondary" onClick={onBack} type="button">Back to Quick Edit</button></div>
    {error && <p className="edit-studio__action-error" role="alert">{error}</p>}
    <div className="crop-tool__stage" ref={stageRef}><img alt="Crop source" draggable={false} src={source.image_url} /><div className="crop-tool__shade" /><div className="crop-tool__selection" onPointerDown={(e) => beginDrag(e, "move")} style={style}>
      {(["n","s","e","w","ne","nw","se","sw"] as Handle[]).map((handle) => <button aria-label={`Resize crop ${handle}`} className={`crop-tool__handle crop-tool__handle--${handle}`} key={handle} onPointerDown={(e) => { e.stopPropagation(); beginDrag(e, handle); }} type="button" />)}
    </div></div>
    <div className="crop-tool__controls"><label><span>Aspect</span><select aria-label="Crop aspect ratio" onChange={(e) => choosePreset(e.target.value as (typeof presets)[number])} value={preset}>{presets.map((item) => <option key={item}>{item}</option>)}</select></label><output>{box.width} × {box.height} px</output></div>
    <div className="crop-tool__actions"><button className="edit-studio__secondary" onClick={reset} type="button">Reset</button><button className="edit-studio__secondary" onClick={onBack} type="button">Cancel</button><button className="edit-studio__primary" disabled={busy} onClick={() => void apply()} type="button">{busy ? "Applying…" : "Apply Crop"}</button></div>
  </section>;
}
