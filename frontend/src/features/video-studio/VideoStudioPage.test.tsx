import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BackgroundOperationsProvider } from "../background-operations/BackgroundOperationsContext";
import { VideoStudioPage } from "./VideoStudioPage";

const response = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
const provider = { provider_id: "wavespeed_seedance_2_0", display_name: "Seedance 2.0", model_family: "seedance-2.0", min_native_duration: 4, max_native_duration: 15, supported_resolutions: ["720p"], supported_aspect_ratios: ["9:16"], native_audio: true };

function renderPage(path = "/studio/video") {
  return render(<MemoryRouter initialEntries={[path]}><BackgroundOperationsProvider pollMilliseconds={60000}><VideoStudioPage /></BackgroundOperationsProvider></MemoryRouter>);
}

describe("VideoStudioPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("replaces the placeholder with the clean source chooser", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("background-operations") ? response({ success: true, operations: [] }) : String(input).endsWith("/providers") ? response({ providers: [provider] }) : response({ sessions: [] }));
    renderPage();
    expect(screen.getByRole("heading", { name: "Video Studio" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Choose your starting image" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Generation Library/ })).toBeInTheDocument();
    expect(screen.queryByText(/coming soon/i)).not.toBeInTheDocument();
  });

  it("loads an authoritative deep link and exposes creative settings before planning", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("background-operations") ? response({ success: true, operations: [] }) : String(input).endsWith("/providers") ? response({ providers: [provider] }) : response({ sessions: [] }));
    renderPage("/studio/video?sourceType=asset&sourceId=42&preview=%2Fapi%2Fv1%2Fassets%2F42%2Fmedia&label=Hero%20portrait");
    expect(await screen.findByText("Hero portrait")).toBeInTheDocument();
    expect(screen.getByLabelText("Desired runtime")).toHaveValue("15");
    expect(screen.getByRole("button", { name: /Inspire Me/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Develop My Idea" }));
    expect(screen.getByPlaceholderText("Describe the video you'd like...")).toBeInTheDocument();
  });

  it("shows complete concept cards without provider prompts or segments", async () => {
    const concept = { concept_id: "c1", title: "Steamy Shower Escape", overall_theme: "Rest", experience_summary: "A slow cinematic sequence that develops into gentle eye contact.", tone: "intimate", viewer_experience: "calm", pacing: "gradual", narrative_arc: "rest to connection", requested_runtime: 15, origin: "grok_inspiration", timeline: [{ start_second: 0, end_second: 15, phase: "complete", creative_beat: "She relaxes, then meets the viewer's gaze." }] };
    const session = { session_id: "s1", status: "CONCEPTS_READY", source_type: "asset", source_id: "42", source_asset_id: 42, source_media_type: "image", source_snapshot: {}, settings: { desired_runtime: 15, aspect_ratio: "9:16", resolution: "720p", generate_audio: true, video_provider: "wavespeed_seedance_2_0" }, settings_version: 1, provider_id: "wavespeed_seedance_2_0", concept_batches: [{ batch_id: "b1", concepts: [concept] }], selected_concept: null, execution_plan: null, current_generation_run: null, final_generated_media_id: null, final_asset_id: null, created_at: "2026-01-01", updated_at: "2026-01-01" };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("background-operations") ? response({ success: true, operations: [] }) : String(input).endsWith("/providers") ? response({ providers: [provider] }) : String(input).includes("/sessions/s1") ? response(session) : response({ sessions: [session] }));
    renderPage("/studio/video?session=s1");
    expect(await screen.findByText("Steamy Shower Escape")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Choose This Concept/ })).toBeInTheDocument();
    expect(screen.queryByText(/provider prompt|segment 1|prediction/i)).not.toBeInTheDocument();
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
  });

  it("falls back to 9:16 for a reopened session with no persisted ratio and does not save over it", async () => {
    const baseSession = { session_id: "s1", status: "DRAFT", source_type: "asset", source_id: "42", source_asset_id: 42, source_media_type: "image", source_snapshot: {}, settings: { desired_runtime: 15, resolution: "720p", generate_audio: true, video_provider: "wavespeed_seedance_2_0" }, settings_version: 1, provider_id: "wavespeed_seedance_2_0", concept_batches: [], selected_concept: null, execution_plan: null, current_generation_run: null, final_generated_media_id: null, final_asset_id: null, created_at: "2026-01-01", updated_at: "2026-01-01" };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("background-operations") ? response({ success: true, operations: [] }) : String(input).endsWith("/providers") ? response({ providers: [provider] }) : String(input).includes("/sessions/s1") ? response(baseSession) : response({ sessions: [] }));
    renderPage("/studio/video?session=s1");
    expect(await screen.findByLabelText("Aspect ratio")).toHaveValue("9:16");
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);
  });

  it("retains an existing session's persisted aspect ratio", async () => {
    const session = { session_id: "wide", status: "DRAFT", source_type: "asset", source_id: "42", source_asset_id: 42, source_media_type: "image", source_snapshot: {}, settings: { desired_runtime: 15, aspect_ratio: "16:9", resolution: "720p", generate_audio: true, video_provider: "wavespeed_seedance_2_0" }, settings_version: 1, provider_id: "wavespeed_seedance_2_0", concept_batches: [], selected_concept: null, execution_plan: null, current_generation_run: null, final_generated_media_id: null, final_asset_id: null, created_at: "2026-01-01", updated_at: "2026-01-01" };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("background-operations") ? response({ success: true, operations: [] }) : String(input).endsWith("/providers") ? response({ providers: [provider] }) : String(input).includes("/sessions/wide") ? response(session) : response({ sessions: [] }));
    renderPage("/studio/video?session=wide");
    expect(await screen.findByLabelText("Aspect ratio")).toHaveValue("16:9");
  });
});
