export function ActivePhotoshootActions({ busy, onFinish, onStop }: { busy: boolean; onFinish: () => void; onStop: () => void }) {
  return <div className="photoshoot-session-actions"><button className="photoshoot-button photoshoot-button--danger" disabled={busy} onClick={onStop} type="button">Stop Photoshoot &amp; Return Seed</button><button className="photoshoot-button photoshoot-button--secondary" disabled={busy} onClick={onFinish} type="button">📸 Finish Photoshoot</button></div>;
}

export function StopPhotoshootDialog({ busy, onCancel, onConfirm }: { busy: boolean; onCancel: () => void; onConfirm: () => void }) {
  return <div className="photoshoot-stop-dialog" role="dialog" aria-modal="true" aria-labelledby="photoshoot-stop-title"><div><h2 id="photoshoot-stop-title">Stop this Photoshoot?</h2><p>This will abandon the current Photoshoot, clear its active workspace, and return the original seed image to Generation Library.</p><p>Any generated Photoshoot shots from this unfinished session will no longer remain in the active Photoshoot workflow.</p><footer><button disabled={busy} onClick={onCancel} type="button">Cancel</button><button className="photoshoot-button--danger" disabled={busy} onClick={onConfirm} type="button">Stop Photoshoot &amp; Return Seed</button></footer></div></div>;
}

export function PhotoshootCompletedPanel({ approvedShotCount, onOpenLibrary }: { approvedShotCount: number; onOpenLibrary: () => void }) {
  return <section className="photoshoot-card photoshoot-shot-approved" aria-labelledby="photoshoot-completed-title" role="status"><div className="photoshoot-shot-approved__check" aria-hidden="true">✓</div><div><h2 id="photoshoot-completed-title">Photoshoot Complete</h2><p>{approvedShotCount} approved {approvedShotCount === 1 ? "shot is" : "shots are"} preserved in this completed session.</p><p>The session is ready for gallery and publishing workflows.</p></div><div className="photoshoot-shot-approved__actions"><button className="photoshoot-button photoshoot-button--primary" onClick={onOpenLibrary} type="button">Open Generation Library</button></div></section>;
}
