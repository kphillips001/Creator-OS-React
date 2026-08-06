import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { GenerationRecord } from "../../generation-library/types";
import { CandidatePanel } from "./CandidatePanel";

const record = (id: string): GenerationRecord => ({
  image_id: id, image_url: `/api/v1/generation-library/${id}/media`, provider_id: "seedream",
  prompt_text: `${id} prompt`, creative_mode: "premium", generation_date: "2026-08-03T12:00:00Z",
  status: "photoshoot_session", generation_job_id: `job-${id}`, generation_request_id: `request-${id}`,
  generation_result_id: `result-${id}`, prompt_plan_id: `plan-${id}`, reference_asset_id: null, imported_asset_id: null,
  provider_metadata: {}, prompt_metadata: {}, generation_metadata: {},
});

afterEach(() => vi.unstubAllGlobals());

function renderPanel() {
  const callbacks = { onApprove: vi.fn(), onReject: vi.fn(), onRegenerate: vi.fn(), onEdit: vi.fn() };
  render(<CandidatePanel busy={false} candidate={record("candidate")} current={record("approved")} {...callbacks} />);
  return callbacks;
}

describe("CandidatePanel image preview", () => {
  it.each([
    ["Current Approved Shot", "approved"],
    ["Candidate Shot", "candidate"],
  ])("opens the full-resolution %s without changing review state", (label, id) => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const callbacks = renderPanel();

    fireEvent.click(screen.getByRole("button", { name: `Preview ${label}` }));
    expect(screen.getByRole("dialog", { name: `${label} fullscreen preview` })).toBeInTheDocument();
    expect(screen.getByAltText(`${label} full-size preview`)).toHaveAttribute("src", `/api/v1/generation-library/${id}/media`);
    expect(fetch).not.toHaveBeenCalled();
    for (const callback of Object.values(callbacks)) expect(callback).not.toHaveBeenCalled();
  });

  it("closes with the X button, Escape, and the dimmed backdrop", () => {
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Preview Candidate Shot" }));
    fireEvent.click(screen.getByRole("button", { name: "Close preview" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Preview Candidate Shot" }));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Preview Candidate Shot" }));
    fireEvent.mouseDown(screen.getByRole("dialog"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
