import { useId } from "react";

export function DeliveryUncertainBadge({ onClick }: { onClick: () => void }) {
  return <span className="chat-badge is-operational is-delivery_uncertain"
    role="button" tabIndex={0} aria-label="Dismiss Delivery Uncertain warning"
    onClick={event => { event.stopPropagation(); onClick(); }}
    onKeyDown={event => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault(); event.stopPropagation(); onClick();
      }
    }}>DELIVERY UNCERTAIN</span>;
}

export function DeliveryUncertainDismissModal({ busy, error, onCancel, onConfirm }: {
  busy: boolean; error: string; onCancel: () => void; onConfirm: () => void;
}) {
  const id = useId();
  return <div className="takeover-modal" role="dialog" aria-modal="true" aria-labelledby={id}
    onKeyDown={event => { if (event.key === "Escape" && !busy) onCancel(); }}>
    <div>
      <h3 id={id}>Dismiss Delivery Uncertain?</h3>
      <p>This hides this warning after you've reviewed it. It does not mark the historical message as delivered or retry it.</p>
      {error && <p role="alert">{error}</p>}
      <footer>
        <button type="button" autoFocus disabled={busy} onClick={onCancel}>Cancel</button>
        <button type="button" disabled={busy} onClick={onConfirm}>{busy ? "Dismissing…" : "Dismiss"}</button>
      </footer>
    </div>
  </div>;
}
