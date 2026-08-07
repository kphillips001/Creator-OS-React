import { useState } from "react";
import type { PhotoshootAutoRunRuntime, PlannedShot, PlanningMode } from "../types";

const FRAME_COUNTS = [4, 6, 8, 10, 12] as const;

type Props = {
  disabled: boolean;
  busy: boolean;
  autoRunning: boolean;
  runtime: PhotoshootAutoRunRuntime | null;
  planningMode: PlanningMode;
  planFrameCount: number;
  targetShotCount: number;
  sessionPlan: PlannedShot[];
  sessionPlanIndex: number;
  sessionPlanApproved: boolean;
  hasRecommendation: boolean;
  directionApproved: boolean;
  onPlanningMode: (mode: PlanningMode) => void;
  onFrameCount: (count: number) => void;
  onTargetShotCount: (count: number) => void;
  onGeneratePlan: () => void;
  onApprovePlan: () => void;
  onResumePlan: () => void;
};

export function SessionPlanPanel(props: Props) {
  const [customTargetSelected, setCustomTargetSelected] = useState(![0, 5, 10, 15].includes(props.targetShotCount));
  const remaining = props.sessionPlan.length
    ? Math.max(0, props.sessionPlan.length - props.sessionPlanIndex)
    : 0;
  const current = props.sessionPlan[props.sessionPlanIndex] || null;
  const planComplete = props.sessionPlanApproved && props.sessionPlan.length > 0 && props.sessionPlanIndex >= props.sessionPlan.length;
  const runtime = props.runtime;
  const state = runtime?.auto_run_state || "READY";

  return (
    <section className="photoshoot-card photoshoot-session-plan" aria-labelledby="photoshoot-plan-title">
      <header>
        <h2 id="photoshoot-plan-title">Session Planning</h2>
        <span>How this shoot is directed</span>
      </header>

      <fieldset disabled={props.disabled || props.busy || props.autoRunning}>
        <legend>Planning style</legend>
        <div className="photoshoot-segmented segmented-control">
          <label>
            <input
              checked={props.planningMode === "frame_by_frame"}
              name="photoshoot-planning-mode"
              onChange={() => props.onPlanningMode("frame_by_frame")}
              type="radio"
            />
            <span>Frame by frame</span>
          </label>
          <label>
            <input
              checked={props.planningMode === "full_plan"}
              name="photoshoot-planning-mode"
              onChange={() => props.onPlanningMode("full_plan")}
              type="radio"
            />
            <span>{props.targetShotCount === 0 ? "Plan variety batch" : "Plan entire session"}</span>
          </label>
        </div>
      </fieldset>

      <div className="photoshoot-session-plan__controls photoshoot-session-plan__target">
        <label>
          <span>Target Photoshoot Length</span>
          <select
            aria-label="Target Photoshoot Length"
            disabled={props.disabled || props.busy || props.autoRunning}
            onChange={(event) => {
              if (event.target.value === "custom") {
                setCustomTargetSelected(true);
                return;
              }
              setCustomTargetSelected(false);
              props.onTargetShotCount(Number(event.target.value));
            }}
            value={customTargetSelected ? "custom" : String(props.targetShotCount)}
          >
            <option value="0">Creative Freeflow (No progression)</option>
            <option value="5">Mini (5 shots)</option>
            <option value="10">Standard (10 shots)</option>
            <option value="15">Extended (15 shots)</option>
            <option value="custom">Custom...</option>
          </select>
        </label>
        {customTargetSelected && (
          <label>
            <span>Custom shot count</span>
            <input
              aria-label="Custom shot count"
              disabled={props.disabled || props.busy || props.autoRunning}
              max={100}
              min={2}
              onChange={(event) => {
                const count = Number(event.target.value);
                if (Number.isInteger(count) && count >= 2 && count <= 100) props.onTargetShotCount(count);
              }}
              type="number"
              value={props.targetShotCount}
            />
          </label>
        )}
      </div>

      <div className="photoshoot-creative-structure">
        <strong>{props.targetShotCount === 0 ? "✨ Creative Freeflow" : "🎬 Story Progression Active"}</strong>
        <span>
          {props.targetShotCount === 0
            ? "AI explores varied shots within the same scene without staged progression."
            : "AI advances each approved shot through a planned Photoshoot arc."}
        </span>
      </div>

      {props.planningMode === "frame_by_frame" ? (
        <p className="photoshoot-session-plan__hint">
          {props.targetShotCount === 0
            ? "Default mode. After each approved shot, Ask AI for another distinct photograph in the same visual world."
            : "Default mode. After each approved shot, Ask AI for the next natural frame."}
        </p>
      ) : (
        <>
          <p className="photoshoot-session-plan__hint">
            {props.targetShotCount === 0
              ? "Plan a finite batch of varied photographs, approve once, then Photoshoot generates each frame automatically until the batch is done."
              : "Plan the full arc from the seed, approve once, then Photoshoot generates each frame automatically until the set is done."}
          </p>
          <div className="photoshoot-session-plan__controls">
            <label>
              <span>Number of frames</span>
              <select
                disabled={props.disabled || props.busy || props.sessionPlanApproved || props.autoRunning}
                onChange={(event) => props.onFrameCount(Number(event.target.value))}
                value={props.planFrameCount}
              >
                {FRAME_COUNTS.map((count) => (
                  <option key={count} value={count}>{count} frames</option>
                ))}
              </select>
            </label>
            <div className="photoshoot-creative-actions photoshoot-session-plan__actions">
              <button
                className="photoshoot-button photoshoot-button--secondary"
                disabled={props.disabled || props.busy || props.autoRunning}
                onClick={props.onGeneratePlan}
                type="button"
              >
                {props.targetShotCount === 0
                  ? props.sessionPlan.length ? "Replan Variety Batch" : "Plan Variety Batch"
                  : props.sessionPlan.length ? "Replan Session" : "Plan Entire Session"}
              </button>
              {props.sessionPlan.length > 0 && !props.sessionPlanApproved && (
                <button
                  className="photoshoot-button photoshoot-button--primary"
                  disabled={props.disabled || props.busy || props.autoRunning}
                  onClick={props.onApprovePlan}
                  type="button"
                >
                  Approve Plan &amp; Run
                </button>
              )}
              {props.sessionPlanApproved && !planComplete && state === "READY" && (
                <button
                  className="photoshoot-button photoshoot-button--primary"
                  disabled={props.disabled || props.busy}
                  onClick={props.onResumePlan}
                  type="button"
                >
                  Start Auto Generation
                </button>
              )}
            </div>
          </div>

          {props.sessionPlan.length > 0 && (
            <div className="photoshoot-session-plan__list" aria-label="Session plan">
              <header>
                <strong>
                  {props.sessionPlanApproved
                    ? planComplete
                      ? "Plan complete"
                      : props.autoRunning
                        ? `Auto-running · ${remaining} remaining`
                        : `Plan approved · ${remaining} remaining`
                    : "Review plan, then Approve Plan & Run"}
                </strong>
                {current && props.sessionPlanApproved && !planComplete && (
                  <span>{props.autoRunning ? "Now:" : "Up next:"} {current.title || `Shot ${props.sessionPlanIndex + 1}`}</span>
                )}
              </header>
              <ol>
                {props.sessionPlan.map((shot, index) => {
                  const status = shot.status || (index < props.sessionPlanIndex ? "completed" : index === props.sessionPlanIndex ? "current" : "pending");
                  return (
                    <li
                      className={`photoshoot-session-plan__shot photoshoot-session-plan__shot--${status}`}
                      key={`${shot.shot_number}:${shot.title}:${index}`}
                    >
                      <div>
                        <strong>{shot.shot_number}. {shot.title || `Shot ${shot.shot_number}`}</strong>
                        <em>{status}</em>
                      </div>
                      <p>{shot.creative_direction}</p>
                      {(shot.emotion || shot.pose_composition) && (
                        <small>
                          {[shot.emotion, shot.pose_composition].filter(Boolean).join(" · ")}
                        </small>
                      )}
                    </li>
                  );
                })}
              </ol>
            </div>
          )}
        </>
      )}
    </section>
  );
}
