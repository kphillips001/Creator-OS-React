import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PhotoshootAutoRunRuntime } from "../types";
import { PhotoshootAutoGenerationProgress } from "./PhotoshootAutoGenerationProgress";

const runtime = (state: PhotoshootAutoRunRuntime["auto_run_state"]): PhotoshootAutoRunRuntime => ({
  session_id: "session-1", auto_run_state: state,
  is_running: ["PREPARING", "GENERATING", "APPROVING", "ADVANCING"].includes(state),
  is_paused: state === "PAUSED", is_failed: state === "FAILED",
  plan_complete: ["PLAN_COMPLETE", "PHOTOSHOOT_COMPLETE"].includes(state),
  photoshoot_complete: state === "PHOTOSHOOT_COMPLETE", completed_frames: state.includes("COMPLETE") ? 8 : 4,
  total_frames: 8, progress_percent: state.includes("COMPLETE") ? 100 : 50,
  current_frame_index: state.includes("COMPLETE") ? null : 4,
  current_frame_number: state.includes("COMPLETE") ? null : 5,
  current_frame_title: state.includes("COMPLETE") ? null : "Panty Peel Nude",
  current_frame_status: "pending", current_request_id: null, generation_job_id: null, candidate: null,
  spinner_active: ["PREPARING", "GENERATING", "APPROVING", "ADVANCING"].includes(state),
  waiting_for_review: state === "WAITING_FOR_REVIEW",
  failure: state === "FAILED" ? { error_code: "provider_failed", error_message: "Backend provider timed out.", stage: "generation" } : null,
  last_updated_at: "2026-07-21T12:00:00Z", auto_approve_enabled: true, review_mode: "AUTO_APPROVE", available_actions: [],
});

function renderProgress(state: PhotoshootAutoRunRuntime["auto_run_state"]) {
  const callbacks = { onPause: vi.fn(), onResume: vi.fn(), onRetry: vi.fn(), onFinish: vi.fn() };
  render(<PhotoshootAutoGenerationProgress busy={false} runtime={runtime(state)} {...callbacks} />);
  return callbacks;
}

describe("PhotoshootAutoGenerationProgress", () => {
  it("uses backend frame progress and plan title while generating", () => {
    const { onPause } = renderProgress("GENERATING");
    expect(screen.getByText("4 of 8 Complete")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("Frame 5 — Panty Peel Nude")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Generating");
    expect(screen.getByRole("img", { name: "Active work" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Pause Auto Generation" }));
    expect(onPause).toHaveBeenCalledOnce();
  });

  it.each(["WAITING_FOR_REVIEW", "PAUSED", "FAILED", "PLAN_COMPLETE"] as const)("does not animate for %s", (state) => {
    renderProgress(state);
    expect(screen.queryByRole("img", { name: "Active work" })).not.toBeInTheDocument();
  });

  it("shows the backend failure and retries the current frame", () => {
    const { onRetry } = renderProgress("FAILED");
    expect(screen.getByRole("alert")).toHaveTextContent("Generation FailedFrame 5Backend provider timed out.");
    fireEvent.click(screen.getByRole("button", { name: "Retry Frame" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("separates Auto Generation Complete from finishing the Photoshoot", () => {
    const { onFinish } = renderProgress("PLAN_COMPLETE");
    expect(screen.getByRole("status")).toHaveTextContent("Auto Generation Complete");
    expect(screen.getByText("8 of 8 Complete")).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Finish Photoshoot" }));
    expect(onFinish).toHaveBeenCalledOnce();
  });
});
