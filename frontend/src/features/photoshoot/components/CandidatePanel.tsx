import { useState } from "react";

import type { GenerationRecord } from "../../generation-library/types";
import { LibraryImage } from "../../generation-library/LibraryImage";
import { PhotoshootImagePreview } from "./PhotoshootImagePreview";

export type CandidateRejectionDisposition = "discard" | "save_to_generation_library";

type Props = {
  current: GenerationRecord;
  candidate: GenerationRecord | null;
  continuityWarning?: string;
  busy: boolean;
  onApprove: () => void;
  onRegenerate: () => void;
  onEdit: () => void;
  onReject: (disposition: CandidateRejectionDisposition) => void;
};

export function CandidatePanel({
  current, candidate, continuityWarning, busy, onApprove, onRegenerate, onEdit, onReject,
}: Props) {
  const [preview, setPreview] = useState<{ image: GenerationRecord; label: string } | null>(null);
  const [confirmReject, setConfirmReject] = useState(false);

  if (!candidate) {
    return <section className="photoshoot-card photoshoot-review" aria-labelledby="photoshoot-candidate-title">
      <header><h2 id="photoshoot-candidate-title">Candidate Review</h2><span>Waiting for the next candidate</span></header>
      <div className="photoshoot-candidate">No candidate generated yet.</div>
    </section>;
  }

  const reject = (disposition: CandidateRejectionDisposition) => {
    setConfirmReject(false);
    onReject(disposition);
  };

  return <section className="photoshoot-card photoshoot-review" aria-labelledby="photoshoot-candidate-title">
    <header><h2 id="photoshoot-candidate-title">Candidate Review</h2><span>Compare before approval</span></header>
    {continuityWarning && <div className="photoshoot-continuity-warning" role="status">{continuityWarning}</div>}
    <div className="photoshoot-candidate-compare">
      <article>
        <strong>Current Approved Shot</strong>
        <button aria-label="Preview Current Approved Shot" className="photoshoot-candidate-preview" onClick={() => setPreview({ image: current, label: "Current Approved Shot" })} type="button"><LibraryImage record={current} /></button>
      </article>
      <article>
        <strong>Candidate Shot</strong>
        <button aria-label="Preview Candidate Shot" className="photoshoot-candidate-preview" onClick={() => setPreview({ image: candidate, label: "Candidate Shot" })} type="button"><LibraryImage priority record={candidate} /></button>
      </article>
    </div>
    <div className="photoshoot-candidate-actions">
      <button disabled={busy} onClick={onApprove} type="button">Approve Shot</button>
      <button disabled={busy} onClick={onRegenerate} type="button">Regenerate</button>
      <button disabled={busy} onClick={onEdit} type="button">Edit Prompt</button>
      <button disabled={busy} onClick={() => setConfirmReject(true)} type="button">Reject Shot</button>
    </div>
    {confirmReject && <div aria-labelledby="photoshoot-reject-title" aria-modal="true" className="photoshoot-stop-dialog photoshoot-reject-dialog" role="dialog">
      <div>
        <h2 id="photoshoot-reject-title">Reject this candidate?</h2>
        <p>Either discard it permanently or preserve it as a standalone image in Generation Library.</p>
        <p>Both choices reject the shot. It will not be approved, added to the timeline, used for continuity, or advance the Photoshoot.</p>
        <footer>
          <button disabled={busy} onClick={() => setConfirmReject(false)} type="button">Cancel</button>
          <button className="photoshoot-button--danger" disabled={busy} onClick={() => reject("discard")} type="button">Reject and Discard</button>
          <button disabled={busy} onClick={() => reject("save_to_generation_library")} type="button">Reject but Save to Generation Library</button>
        </footer>
      </div>
    </div>}
    {preview && <PhotoshootImagePreview image={preview.image} label={preview.label} onClose={() => setPreview(null)} />}
  </section>;
}
