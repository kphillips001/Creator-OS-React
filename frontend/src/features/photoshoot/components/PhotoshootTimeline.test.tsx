import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { GenerationRecord } from "../../generation-library/types";
import { PhotoshootTimeline } from "./PhotoshootTimeline";

const image: GenerationRecord = {
  image_id: "approved-2", image_url: "/api/v1/generation-library/approved-2/media", provider_id: "seedream",
  prompt_text: "Approved timeline image", creative_mode: "premium", generation_date: "2026-08-03T12:00:00Z",
  status: "photoshoot_session", generation_job_id: "job-2", generation_request_id: "request-2",
  generation_result_id: "result-2", prompt_plan_id: "plan-2", reference_asset_id: null, imported_asset_id: null,
  provider_metadata: {}, prompt_metadata: {}, generation_metadata: {},
};

afterEach(() => vi.unstubAllGlobals());

function renderTimeline(onReplace = vi.fn()) {
  render(<PhotoshootTimeline busy={false} onReplace={onReplace} items={[
    { requestId: "request-1", sequenceIndex: 1, shotNumber: 1, label: "Shot 1 (Seed)", isSeed: true, status: "approved", image: { ...image, image_id: "seed", image_url: "/seed-full.png" } },
    { requestId: "request-2", sequenceIndex: 2, shotNumber: 2, label: "Shot 2", isSeed: false, status: "approved", image },
  ]} />);
  return onReplace;
}

describe("PhotoshootTimeline image preview", () => {
  it("opens the full-resolution approved image without requests and preserves Replace Shot selection", () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const onReplace = renderTimeline();

    fireEvent.click(screen.getByRole("button", { name: "Select Shot 2" }));

    const dialog = screen.getByRole("dialog", { name: "Approved Photoshoot image fullscreen preview" });
    expect(screen.getByAltText("Approved Photoshoot image full-size preview")).toHaveAttribute("src", image.image_url);
    expect(screen.getByRole("button", { name: "Replace Shot" })).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Close preview" }));
    expect(dialog).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Replace Shot" }));
    expect(onReplace).toHaveBeenCalledWith("request-2");
  });

  it("closes with Escape and by clicking the dimmed backdrop", () => {
    renderTimeline();
    fireEvent.click(screen.getByRole("button", { name: "Select Shot 2" }));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Approved Photoshoot image fullscreen preview" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Select Shot 2" }));
    fireEvent.mouseDown(screen.getByRole("dialog", { name: "Approved Photoshoot image fullscreen preview" }));
    expect(screen.queryByRole("dialog", { name: "Approved Photoshoot image fullscreen preview" })).not.toBeInTheDocument();
  });
});
