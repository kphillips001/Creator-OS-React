import { useMemo, useState, type WheelEvent } from "react";
import type { PhotoshootCurationReview, PhotoshootCurationResult } from "../types";

type Decision = "APPROVED" | "DECLINED";

export function PhotoshootCurationPanel({ busy, review, onConfirm, onOpenAssetLibrary }: {
  busy: boolean; review: PhotoshootCurationReview;
  onConfirm: (selected: string[], decision: Decision) => Promise<PhotoshootCurationResult>;
  onOpenAssetLibrary?: () => void;
}) {
  const [decision, setDecision] = useState<Decision | null>(
    review.photoshoot_decision === "APPROVED" || review.photoshoot_decision === "DECLINED" ? review.photoshoot_decision : null,
  );
  const [selected, setSelected] = useState(() => new Set(review.shots.map((shot) => shot.image_id)));
  const [result, setResult] = useState<PhotoshootCurationResult | null>(null);
  const [error, setError] = useState("");
  const selectedIds = useMemo(() => review.shots.filter((shot) => selected.has(shot.image_id)).map((shot) => shot.image_id), [review.shots, selected]);
  const approvedCount = review.shots.length + (review.seed_image ? 1 : 0);
  const selectedCount = selectedIds.length + (review.seed_image ? 1 : 0);
  const remainingCount = review.shots.length - selectedIds.length;
  const toggleShot = (imageId: string) => setSelected((current) => {
    const next = new Set(current);
    if (next.has(imageId)) next.delete(imageId); else next.add(imageId);
    return next;
  });
  const scrollFilmstrip = (event: WheelEvent<HTMLDivElement>) => {
    if (Math.abs(event.deltaY) <= Math.abs(event.deltaX) || event.currentTarget.scrollWidth <= event.currentTarget.clientWidth) return;
    event.preventDefault();
    event.currentTarget.scrollBy({ left: event.deltaY, behavior: "smooth" });
  };
  if (result) return <section className="photoshoot-card photoshoot-curation-complete" role="status">
    <h2>Review Complete</h2>
    <p>{result.photoshoot_created ? "Photoshoot Asset created in Asset Library." : result.image_asset_generation_ids.length ? `${result.image_asset_generation_ids.length} Image Assets created in Asset Library.` : "Session archived. No Assets were created."}</p>
    {(result.photoshoot_created || result.image_asset_generation_ids.length > 0) && <button className="photoshoot-button photoshoot-button--primary" onClick={onOpenAssetLibrary} type="button">Open Asset Library</button>}
  </section>;
  if (decision === "DECLINED") return <section className="photoshoot-card photoshoot-curation photoshoot-curation--salvage" aria-labelledby="photoshoot-curation-title">
    <header><div><h2 id="photoshoot-curation-title">Keep any individual images?</h2><p>Select generated images to save as standalone Image Assets.</p></div><strong>{selectedIds.length} selected</strong></header>
    <div className="photoshoot-curation__filmstrip" onWheel={scrollFilmstrip} role="list" aria-label="Standalone image salvage">
      {review.shots.map((shot, index) => <article key={shot.image_id} className={selected.has(shot.image_id) ? "photoshoot-curation__shot photoshoot-curation__shot--kept" : "photoshoot-curation__shot"} role="listitem">
        <img src={shot.image_url} alt={shot.title} />
        <div className="photoshoot-curation__caption"><span>Shot {index + 2}</span>{shot.title && <strong>{shot.title}</strong>}</div>
        <label><input type="checkbox" checked={selected.has(shot.image_id)} onChange={() => setSelected((current) => { const next = new Set(current); if (next.has(shot.image_id)) next.delete(shot.image_id); else next.add(shot.image_id); return next; })} />Save as Image Asset</label>
      </article>)}
    </div>
    {error && <p className="photoshoot-curation__error" role="alert">{error}</p>}
    <footer className="photoshoot-curation__salvage-actions"><button className="photoshoot-button" disabled={busy} onClick={() => { setDecision(null); setSelected(new Set()); }} type="button">Back to Photoshoot Review</button><button className="photoshoot-button photoshoot-button--primary" disabled={busy} onClick={() => { setError(""); void onConfirm(selectedIds, "DECLINED").then(setResult).catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to finish curation.")); }} type="button">Finish</button></footer>
  </section>;
  return <section className="photoshoot-card photoshoot-curation" aria-labelledby="photoshoot-curation-title">
    <header><div><h2 id="photoshoot-curation-title">Review &amp; Curate</h2><p>Review the complete Photoshoot sequence from left to right.</p></div></header>
    <div className="photoshoot-curation__filmstrip" onWheel={scrollFilmstrip} role="list" aria-label="Photoshoot sequence">
      {review.seed_image && <article className="photoshoot-curation__shot photoshoot-curation__shot--kept photoshoot-curation__shot--seed" role="listitem">
        <img src={review.seed_image.image_url} alt={review.seed_image.title} /><div className="photoshoot-curation__caption"><span>⭐ Seed Image</span>{review.seed_image.title && <strong>{review.seed_image.title}</strong>}</div>
        <label><input aria-label="Include Seed Image in Photoset" type="checkbox" checked disabled />Required hero</label>
      </article>}
      {review.shots.map((shot, index) => <article key={shot.image_id} className={selected.has(shot.image_id) ? "photoshoot-curation__shot photoshoot-curation__shot--kept" : "photoshoot-curation__shot"} role="listitem">
        <img src={shot.image_url} alt={shot.title} /><div className="photoshoot-curation__caption"><span>Shot {index + 2}</span>{shot.title && <strong>{shot.title}</strong>}</div>
        <label><input aria-label={`Include ${shot.title || `Shot ${index + 2}`} in Photoset`} type="checkbox" checked={selected.has(shot.image_id)} disabled={busy} onChange={() => toggleShot(shot.image_id)} />Include in Photoset</label>
      </article>)}
    </div>
    <div className="photoshoot-curation__counts" aria-label="Photoset membership counts">
      <span><strong>{approvedCount}</strong>Approved</span>
      <span><strong>{selectedCount}</strong>Selected</span>
      <span><strong>{remainingCount}</strong>Remaining Available Inventory</span>
    </div>
    <div className="photoshoot-curation__commitment">
      <p><strong>Selected images:</strong> become part of this Photoset permanently.</p>
      <p><strong>Unselected approved images:</strong> remain Available Inventory for future use.</p>
      <p><strong>Rejected images:</strong> remain excluded.</p>
    </div>
    <fieldset className="photoshoot-curation__modes"><legend>Approve this Photoshoot?</legend>
      <label><input type="radio" name="photoshoot-decision" checked={decision === "APPROVED"} onChange={() => { setDecision("APPROVED"); setSelected(new Set(review.shots.map((shot) => shot.image_id))); }} /><span><strong>Yes</strong></span></label>
      <label><input type="radio" name="photoshoot-decision" checked={false} onChange={() => { setDecision("DECLINED"); setSelected(new Set()); }} /><span><strong>No</strong></span></label>
    </fieldset>
    {error && <p className="photoshoot-curation__error" role="alert">{error}</p>}
    <footer><button className="photoshoot-button photoshoot-button--primary" disabled={busy || decision !== "APPROVED"} onClick={() => { setError(""); void onConfirm(selectedIds, "APPROVED").then((next) => { setResult(next); onOpenAssetLibrary?.(); }).catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to finish curation.")); }} type="button">Finish</button></footer>
  </section>;
}
