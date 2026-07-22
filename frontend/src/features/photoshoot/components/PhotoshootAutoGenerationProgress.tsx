import { LiveProgressPanel, type LiveProgressTone } from "../../../shared/ui/LiveProgressPanel";
import type { PhotoshootAutoRunRuntime } from "../types";

type Props = {
  runtime: PhotoshootAutoRunRuntime;
  busy: boolean;
  onPause: () => void;
  onResume: () => void;
  onRetry: () => void;
  onFinish: () => void;
};

const ACTIVE = new Set(["PREPARING", "GENERATING", "APPROVING", "ADVANCING"]);
const LABELS: Record<PhotoshootAutoRunRuntime["auto_run_state"], string> = {
  READY: "Preparing", PREPARING: "Preparing", GENERATING: "Generating",
  WAITING_FOR_REVIEW: "Waiting for Review", APPROVING: "Approving", ADVANCING: "Advancing",
  PAUSED: "Paused", FAILED: "Analysis Failed", PLAN_COMPLETE: "Auto Generation Complete",
  PHOTOSHOOT_COMPLETE: "Photoshoot Complete",
};

function toneFor(runtime: PhotoshootAutoRunRuntime): LiveProgressTone {
  if (runtime.is_failed) return "failed";
  if (runtime.is_paused) return "paused";
  if (runtime.waiting_for_review) return "waiting";
  if (runtime.plan_complete || runtime.photoshoot_complete) return "complete";
  return "active";
}

export function PhotoshootAutoGenerationProgress({ runtime, busy, onPause, onResume, onRetry, onFinish }: Props) {
  const state = runtime.auto_run_state;
  const active = ACTIVE.has(state);
  const currentFrame = runtime.current_frame_number
    ? `Frame ${runtime.current_frame_number} — ${runtime.current_frame_title || `Frame ${runtime.current_frame_number}`}`
    : "All planned frames complete";
  return (
    <LiveProgressPanel
      actions={<>
        {(active || state === "WAITING_FOR_REVIEW") && <button className="photoshoot-button photoshoot-button--secondary" disabled={busy} onClick={onPause} type="button">Pause Auto Generation</button>}
        {state === "PAUSED" && <button className="photoshoot-button photoshoot-button--primary" disabled={busy} onClick={onResume} type="button">Resume Auto Generation</button>}
        {state === "FAILED" && <button className="photoshoot-button photoshoot-button--primary" disabled={busy} onClick={onRetry} type="button">Retry Frame</button>}
        {state === "PLAN_COMPLETE" && <button className="photoshoot-button photoshoot-button--primary" disabled={busy} onClick={onFinish} type="button">Finish Photoshoot</button>}
      </>}
      active={runtime.spinner_active}
      progressLabel={`${runtime.completed_frames} of ${runtime.total_frames} Complete`}
      progressPercent={runtime.progress_percent}
      status={LABELS[state]}
      title="Auto Generation"
      tone={toneFor(runtime)}
    >
      <div className="photoshoot-auto-progress__current"><small>Current Frame</small><strong>{currentFrame}</strong></div>
      {runtime.failure && <div className="photoshoot-auto-progress__failure" role="alert"><strong>Generation Failed</strong><span>Frame {runtime.current_frame_number ?? "Unknown"}</span><p>{runtime.failure.error_message}</p></div>}
    </LiveProgressPanel>
  );
}
