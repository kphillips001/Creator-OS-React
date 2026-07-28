import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { navigationGroups } from "../../app/navigation/navigation";
import type { GenerationRecord } from "../generation-library/types";
import { PhotoshootPage } from "./PhotoshootPage";
import { CreativeDirectionPanel } from "./components/CreativeDirectionPanel";

const seed: GenerationRecord = {
  image_id: "seed-1", image_url: "/seed.png", provider_id: "flux", prompt_text: "Seed prompt", creative_mode: "premium",
  generation_date: "2026-07-18T12:00:00Z", status: "pending_photoshoot", generation_job_id: "job-1", generation_request_id: "request-1",
  generation_result_id: "result-1", prompt_plan_id: "plan-1", reference_asset_id: null, imported_asset_id: null,
  provider_metadata: {}, prompt_metadata: {}, generation_metadata: {},
};

function response(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
}

function LibraryDestination() {
  const location = useLocation();
  return <div>Generation Library destination<span>{(location.state as { notification?: string } | null)?.notification}</span></div>;
}

function renderPage() {
  return render(<MemoryRouter initialEntries={["/content/photoshoot"]}><Routes><Route path="/content/photoshoot" element={<PhotoshootPage />} /><Route path="/library/generations" element={<LibraryDestination />} /><Route path="/library/assets" element={<div>Asset Library destination</div>} /></Routes></MemoryRouter>);
}

describe("PhotoshootPage Phase 1", () => {
  it("selects one inspiration idea and renders the backend recommendation contract", () => {
    const select = vi.fn();
    const ideas = Array.from({ length: 10 }, (_, index) => `Next-shot idea ${index + 1}`);
    render(<CreativeDirectionPanel disabled={false} busy={false} guidance="" ideas={ideas} selectedIdea={ideas[1]!} directionApproved={false} recommendation={{ title: "Closer", creative_direction: "Move into a closer portrait", reasoning: "Advances the sequence", emotion: "Confident", camera_framing: "Medium close-up", lighting: "Warm window light", pose_composition: "Turn toward camera", continuity_notes: "Keep wardrobe" }} onGuidance={vi.fn()} onAsk={vi.fn()} onDifferentIdeas={vi.fn()} onSelectIdea={select} onDevelop={vi.fn()} onApprove={vi.fn()} onChooseAnother={vi.fn()} />);
    expect(screen.getAllByRole("radio")).toHaveLength(10);
    expect(screen.getByRole("radio", { name: /Next-shot idea 2/ })).toBeChecked();
    fireEvent.click(screen.getByRole("radio", { name: /^1\. Next-shot idea 1$/ }));
    expect(select).toHaveBeenCalledWith("Next-shot idea 1");
    expect(screen.getByRole("heading", { name: "Closer" })).toBeInTheDocument();
    for (const value of ["Move into a closer portrait", "Advances the sequence", "Confident", "Medium close-up", "Warm window light", "Turn toward camera", "Keep wardrobe"]) expect(screen.getByText(value)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve Direction" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Choose Another Idea" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Ask for Different Ideas" })).toBeEnabled();
  });
  it("uses the Photoshoot route in sidebar navigation", () => {
    const item = navigationGroups.flatMap((group) => group.items).find(({ label }) => label === "Photoshoot Studio");
    expect(item?.path).toBe("/content/photoshoot");
  });

  it("gates on a missing Creator Profile", async () => {
    vi.stubGlobal("fetch", vi.fn(() => response({ creator_profile_exists: false, pending_photoshoot: null, active_session: null, provider_list: [], creative_mode: null, continuity_settings: null, timeline_summary: [] })));
    renderPage();
    expect(await screen.findByText("Creator Profile required before using Photoshoot Studio.")).toBeInTheDocument();
    expect(screen.queryByText("Selected Seed Image")).not.toBeInTheDocument();
  });

  it("gates on a missing pending Photoshoot and returns to Generation Library", async () => {
    vi.stubGlobal("fetch", vi.fn(() => response({ creator_profile_exists: true, pending_photoshoot: null, active_session: null, provider_list: [], creative_mode: null, continuity_settings: null, timeline_summary: [] })));
    renderPage();
    expect(await screen.findByText("Choose an image in Generation Library and click 📸 Photoshoot to begin.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Return to Generation Library" }));
    expect(screen.getByText("Generation Library destination")).toBeInTheDocument();
  });

  it("renders the complete active shell without backend mutations", async () => {
    const fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      void input;
      void init;
      return response({
      creator_profile_exists: true,
      pending_photoshoot: seed,
      provider_list: [{ value: "flux", label: "Flux" }],
      active_session: { session_id: "session-1", title: "Photoshoot Studio", provider_id: "flux", creative_continuity: { session_direction: "Keep the balcony setting", creative_hint: "Stronger eye contact" } },
      creative_mode: "premium",
      continuity_settings: { location: true, wardrobe: false, lighting: true, hairstyle: true, makeup: true, camera_style: false },
      timeline_summary: [{ request_id: "request-1", sequence_index: 1, shot_number: 1, label: "Shot 1 (Seed)", is_seed: true, image: seed }],
      });
    });
    vi.stubGlobal("fetch", fetch);
    renderPage();
    expect(await screen.findByRole("heading", { name: "Selected Seed Image" })).toBeInTheDocument();
    for (const heading of ["Photoshoot Timeline", "Photoshoot Settings", "AI Creative Director", "Prompt", "Generation"]) {
      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: "Generate Shot" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Ask AI" })).toBeEnabled();
    expect(screen.getByText("Renderer")).toBeInTheDocument();
    expect(screen.getByText("Flux")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Premium" })).toBeChecked();
    expect(screen.queryByText("Continuity Locks")).not.toBeInTheDocument();
    for (const label of ["Keep location", "Keep wardrobe", "Keep lighting", "Keep hairstyle", "Keep makeup", "Keep camera style"]) expect(screen.queryByText(label)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Guide the AI (Optional)")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Tell the Creative Director what you would like to change or emphasize...")).toBeInTheDocument();
    expect(screen.queryByText("Session Direction")).not.toBeInTheDocument();
    expect(screen.queryByText("Creative Hint")).not.toBeInTheDocument();
    expect(screen.queryByText("Grok Guidance")).not.toBeInTheDocument();
    expect(screen.getByText("Shot 1 (Seed)")).toBeInTheDocument();
    expect(screen.getByText("This photoshoot grows from left to right.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Candidate Review" })).not.toBeInTheDocument();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    expect(fetch.mock.calls[0]?.[1]).toMatchObject({ method: "GET" });
  });

  it("restores guidance, ten ideas, selection, recommendation, prompt, and mode after refresh", async () => {
    const ideas = Array.from({ length: 10 }, (_, index) => `Recovered idea ${index + 1}`);
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/photoshoot/status")) return response({ request: null, candidate: null });
      if (url.includes("/creative-director/context")) return response({ session_id: "session-1", creative_mode: "explicit", creator_guidance: "Slow the progression", workflow_stage: "direction_approved", current_prompt: "Recovered canonical prompt", recommendation_state: { inspiration_ideas: ideas, selected_inspiration: ideas[4], direction_approved: true, recommendation: { title: "Recovered Direction", creative_direction: "Use a closer photographic setup", reasoning: "Adds framing variety", emotion: "Playful", camera_framing: "Close-up", lighting: "Soft", pose_composition: "Seated turn", continuity_notes: "Keep location" } } });
      return response({ creator_profile_exists: true, pending_photoshoot: seed, provider_list: [{ value: "flux", label: "Flux" }], active_session: { session_id: "session-1", title: "Photoshoot Studio", provider_id: "flux", creative_continuity: {} }, creative_mode: "explicit", continuity_settings: { location: true, wardrobe: true, lighting: true, hairstyle: true, makeup: true, camera_style: true }, timeline_summary: [{ request_id: "request-1", sequence_index: 1, shot_number: 1, label: "Shot 1 (Seed)", is_seed: true, image: seed }] });
    }));
    renderPage();
    expect(await screen.findByDisplayValue("Slow the progression")).toBeInTheDocument();
    expect(screen.getAllByRole("radio", { name: /Recovered idea/ })).toHaveLength(10);
    expect(screen.getByRole("radio", { name: /Recovered idea 5/ })).toBeChecked();
    expect(screen.getByRole("heading", { name: "Recovered Direction" })).toBeInTheDocument();
    expect(screen.getByLabelText("Prompt Editor")).toHaveValue("Recovered canonical prompt");
    expect(screen.getByRole("radio", { name: "Explicit" })).toBeChecked();
    expect(screen.getByRole("button", { name: "Direction Approved" })).toBeDisabled();
  });

  it("restarts status polling after Generate Shot is acknowledged and renders the candidate", async () => {
    let statusCalls = 0;
    const candidate = { ...seed, image_id: "candidate-1", image_url: "/candidate.png", status: "photoshoot_session" };
    const fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/photoshoot/status")) {
        statusCalls += 1;
        return response(statusCalls === 1 ? { request: null, candidate: null } : { request: { request_id: "shot-2", status: "awaiting_review", prompt: "Canonical prompt", provider_id: "flux", generation_job_id: "job-2", failure: null }, candidate });
      }
      if (url.includes("/creative-director/context")) return response({ session_id: "session-1", creative_mode: "premium", creator_guidance: "", workflow_stage: "direction_approved", current_prompt: "Canonical prompt", recommendation_state: { inspiration_ideas: [], selected_inspiration: "", direction_approved: true, recommendation: {} } });
      if (url.endsWith("/photoshoot/generate") && init?.method === "POST") return response({ request_id: "shot-2", status: "generating" }, 202);
      if (url.includes("/creative-director/guidance")) return response({ creator_guidance: "" });
      return response({ creator_profile_exists: true, pending_photoshoot: seed, provider_list: [{ value: "flux", label: "Flux" }], active_session: { session_id: "session-1", title: "Photoshoot Studio", provider_id: "flux", creative_continuity: {} }, creative_mode: "premium", continuity_settings: { location: true, wardrobe: true, lighting: true, hairstyle: true, makeup: true, camera_style: true }, timeline_summary: [{ request_id: "request-1", sequence_index: 1, shot_number: 1, label: "Shot 1 (Seed)", is_seed: true, image: seed }] });
    });
    vi.stubGlobal("fetch", fetch);
    renderPage();
    const generate = await screen.findByRole("button", { name: "Generate Shot" });
    await waitFor(() => expect(generate).toBeEnabled());
    fireEvent.click(generate);
    expect(await screen.findByText("Candidate Shot")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve Shot" })).toBeEnabled();
    expect(statusCalls).toBeGreaterThanOrEqual(2);
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/photoshoot/generate"), expect.objectContaining({ method: "POST" }));
    const generationCall = fetch.mock.calls.find(([input]) => String(input).endsWith("/photoshoot/generate"));
    expect(JSON.parse(String(generationCall?.[1]?.body))).toMatchObject({
      provider_id: "flux",
      creative_mode: "premium",
      continuity_settings: { location: true, wardrobe: true, lighting: true, hairstyle: true, makeup: true, camera_style: true },
    });
  });

  it("approves a candidate, refreshes continuity, and automatically requests the next ten ideas", async () => {
    const approved = { ...seed, image_id: "approved-2", image_url: "/approved-2.png", status: "photoshoot_session" };
    const candidate = { ...seed, image_id: "candidate-2", image_url: "/candidate-2.png", status: "photoshoot_session" };
    const ideas = Array.from({ length: 10 }, (_, index) => `Automatic idea ${index + 1}`);
    let contextCalls = 0;
    let statusCalls = 0;
    const fetch = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/photoshoot/status")) {
        statusCalls += 1;
        return response(statusCalls === 1 ? { request: { request_id: "request-2", status: "awaiting_review" }, candidate } : { request: null, candidate: null });
      }
      if (url.includes("/creative-director/context")) {
        contextCalls += 1;
        return response({ session_id: "session-1", creative_mode: "premium", creator_guidance: "", workflow_stage: "ready_for_next_shot", current_prompt: "", recommendation_state: { inspiration_ideas: [], selected_inspiration: "", direction_approved: false, recommendation: {} } });
      }
      if (url.endsWith("/photoshoot/candidate/approve")) return response({ success: true, status: "approved" });
      if (url.includes("/creative-director/inspiration")) return response({ ideas });
      if (url.includes("/creative-director/guidance")) return response({ creator_guidance: "" });
      const timeline = contextCalls > 0 ? [{ request_id: "request-1", sequence_index: 1, shot_number: 1, label: "Shot 1 (Seed)", is_seed: true, image: seed }, { request_id: "request-2", sequence_index: 2, shot_number: 2, label: "Shot 2", is_seed: false, image: approved }] : [{ request_id: "request-1", sequence_index: 1, shot_number: 1, label: "Shot 1 (Seed)", is_seed: true, image: seed }];
      return response({ creator_profile_exists: true, pending_photoshoot: seed, provider_list: [{ value: "flux", label: "Flux" }], active_session: { session_id: "session-1", title: "Photoshoot Studio", provider_id: "flux", creative_continuity: { workflow_stage: "ready_for_next_shot" } }, creative_mode: "premium", continuity_settings: { location: true, wardrobe: true, lighting: true, hairstyle: true, makeup: true, camera_style: true }, timeline_summary: timeline });
    });
    vi.stubGlobal("fetch", fetch);
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Approve Shot" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Shot Approved");
    expect(screen.getByRole("status")).toHaveTextContent("Updating Photoshoot...");
    await waitFor(() => expect(screen.getAllByRole("radio", { name: /Automatic idea/ })).toHaveLength(10));
    expect(screen.getByText("Shot 2")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Candidate Review" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Finish Photoshoot/ })).toBeEnabled();
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/photoshoot/candidate/approve"), expect.objectContaining({ method: "POST" }));
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/creative-director/inspiration"), expect.objectContaining({ method: "POST" }));
  });

  it("opens Review & Curate and confirms selected deliverables", async () => {
    const approved = { ...seed, image_id: "approved-2", image_url: "/approved-2.png", status: "photoshoot_session" };
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/photoshoot/status")) return response({ request: null, candidate: null });
      if (url.includes("/creative-director/context")) return response({ session_id: "session-1", creative_mode: "safe", creator_guidance: "", workflow_stage: "ready_for_next_shot", current_prompt: "", recommendation_state: { inspiration_ideas: [], selected_inspiration: "", direction_approved: false, recommendation: {} } });
      if (url.endsWith("/photoshoot/finish")) return response({ session_id: "session-1", session_title: "Photoshoot Studio", photoshoot_decision: "PENDING", confirmed: false, curation: {}, seed_image: { image_id: "seed-1", asset_id: 91, shot_number: 0, title: "Canonical Portrait", description: "Seed prompt", image_url: "/seed.png", keep: false, is_seed: true }, shots: [{ image_id: "approved-2", asset_id: 92, shot_number: 1, title: "Window Light", description: "Warm portrait", image_url: "/approved-2.png", keep: true, is_seed: false }] });
      if (url.endsWith("/photoshoot/curation/confirm")) return response({ session_id: "session-1", status: "archived", already_confirmed: false, photoshoot_decision: "APPROVED", photoshoot_decided_at: "2026-07-21T00:00:00Z", selected_image_ids: ["approved-2"], photoshoot_created: true, photoshoot_deliverable_id: "set-1", image_asset_generation_ids: [] });
      return response({ creator_profile_exists: true, pending_photoshoot: seed, provider_list: [{ value: "flux", label: "Flux" }], active_session: { session_id: "session-1", title: "Photoshoot Studio", provider_id: "flux", creative_continuity: { workflow_stage: "ready_for_next_shot" } }, creative_mode: "safe", continuity_settings: { location: true, wardrobe: true, lighting: true, hairstyle: true, makeup: true, camera_style: true }, timeline_summary: [{ request_id: "request-1", sequence_index: 1, shot_number: 1, label: "Shot 1 (Seed)", is_seed: true, image: seed }, { request_id: "request-2", sequence_index: 2, shot_number: 2, label: "Shot 2", is_seed: false, image: approved }] });
    }));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Finish Photoshoot/ }));
    expect(await screen.findByRole("heading", { name: "Review & Curate" })).toBeInTheDocument();
    const sequence = screen.getByRole("list", { name: "Photoshoot sequence" });
    expect(sequence.children[0]).toHaveTextContent("Seed Image");
    expect(sequence.children[1]).toHaveTextContent("Shot 2");
    expect(sequence.children[1]).toHaveTextContent("Window Light");
    fireEvent.click(screen.getByRole("radio", { name: "Yes" }));
    expect(screen.getByRole("checkbox", { name: "Include Seed Image in Photoset" })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: "Include Window Light in Photoset" })).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Finish" }));
    expect(await screen.findByText("Asset Library destination")).toBeInTheDocument();
  });

  it("restores backend-owned Auto Generation progress above the session plan after refresh", async () => {
    const plan = Array.from({ length: 8 }, (_, index) => ({
      shot_number: index + 1, title: index === 4 ? "Panty Peel Nude" : `Frame ${index + 1}`,
      creative_direction: `Direction ${index + 1}`,
    }));
    const fetch = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/photoshoot/status")) return response({ request: null, candidate: null });
      if (url.includes("/creative-director/context")) return response({
        session_id: "session-1", creative_mode: "premium", creator_guidance: "", workflow_stage: "session_plan_running",
        current_prompt: "", recommendation_state: {}, planning_mode: "full_plan", plan_frame_count: 8,
        session_plan: plan, session_plan_index: 4, session_plan_approved: true,
      });
      if (url.includes("/auto-run/runtime")) return response({
        session_id: "session-1", auto_run_state: "GENERATING", is_running: true, is_paused: false, is_failed: false,
        plan_complete: false, photoshoot_complete: false, completed_frames: 4, total_frames: 8, progress_percent: 50,
        current_frame_index: 4, current_frame_number: 5, current_frame_title: "Panty Peel Nude", current_frame_status: "generating",
        current_request_id: "request-5", generation_job_id: "job-5", candidate: null, spinner_active: true,
        waiting_for_review: false, failure: null, last_updated_at: "2026-07-21T12:00:00Z", auto_approve_enabled: true,
        review_mode: "AUTO_APPROVE", available_actions: ["pause", "stop"],
      });
      if (url.includes("/creative-director/guidance")) return response({ creator_guidance: "" });
      return response({ creator_profile_exists: true, pending_photoshoot: seed, provider_list: [{ value: "flux", label: "Flux" }], active_session: { session_id: "session-1", title: "Photoshoot Studio", provider_id: "flux", creative_continuity: {} }, creative_mode: "premium", continuity_settings: { location: true, wardrobe: true, lighting: true, hairstyle: true, makeup: true, camera_style: true }, timeline_summary: [{ request_id: "request-1", sequence_index: 1, shot_number: 1, label: "Shot 1 (Seed)", is_seed: true, image: seed }] });
    });
    vi.stubGlobal("fetch", fetch);
    renderPage();
    expect(await screen.findByText("4 of 8 Complete")).toBeInTheDocument();
    expect(screen.getByText("Frame 5 — Panty Peel Nude")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Generating");
    const progress = screen.getByLabelText("Auto Generation progress");
    expect(progress).toHaveAttribute("value", "50");
    const panel = screen.getByText("Auto Generation").closest(".live-progress");
    const sessionPlan = screen.getByRole("heading", { name: "Session Planning" }).closest("section");
    expect(Boolean(panel && sessionPlan && (panel.compareDocumentPosition(sessionPlan) & Node.DOCUMENT_POSITION_FOLLOWING))).toBe(true);
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/auto-run/runtime?session_id=session-1"), expect.objectContaining({ cache: "no-store" }));
  });

  it("confirms the destructive stop action, supports cancel, and redirects with success feedback", async () => {
    const fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/photoshoot/status")) return response({ request: null, candidate: null });
      if (url.includes("/creative-director/context")) return response({ session_id: "session-1", creative_mode: "premium", creator_guidance: "", workflow_stage: "ready_for_next_shot", current_prompt: "", recommendation_state: { inspiration_ideas: [], selected_inspiration: "", direction_approved: false, recommendation: {} } });
      if (url.endsWith("/photoshoot/stop-and-return-seed") && init?.method === "POST") return response({ success: true, message: "Photoshoot stopped. Seed returned to Generation Library.", redirect: "/library/generations" });
      return response({ creator_profile_exists: true, pending_photoshoot: seed, provider_list: [{ value: "flux", label: "Flux" }], active_session: { session_id: "session-1", title: "Photoshoot Studio", provider_id: "flux", creative_continuity: {} }, creative_mode: "premium", continuity_settings: { location: true, wardrobe: true, lighting: true, hairstyle: true, makeup: true, camera_style: true }, timeline_summary: [{ request_id: "request-1", sequence_index: 1, shot_number: 1, label: "Shot 1 (Seed)", is_seed: true, image: seed }] });
    });
    vi.stubGlobal("fetch", fetch);
    renderPage();

    const stop = await screen.findByRole("button", { name: "Stop Photoshoot & Return Seed" });
    expect(stop).toHaveClass("photoshoot-button--danger");
    expect(screen.getByRole("button", { name: /Finish Photoshoot/ })).toBeEnabled();
    fireEvent.click(stop);
    const dialog = screen.getByRole("dialog", { name: "Stop this Photoshoot?" });
    expect(dialog).toHaveTextContent("return the original seed image to Generation Library");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalledWith(expect.stringContaining("stop-and-return-seed"), expect.anything());

    fireEvent.click(stop);
    const confirm = screen.getAllByRole("button", { name: "Stop Photoshoot & Return Seed" })[1]!;
    expect(confirm).toHaveClass("photoshoot-button--danger");
    fireEvent.click(confirm);
    expect(await screen.findByText("Generation Library destination")).toBeInTheDocument();
    expect(screen.getByText("Photoshoot stopped. Seed returned to Generation Library.")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/photoshoot/stop-and-return-seed"), expect.objectContaining({ method: "POST" }));
  });

  it.each([
    [404, "Photoshoot Studio backend unavailable."],
    [500, "Unable to load Photoshoot Studio."],
  ])("maps HTTP %s to safe UI copy and logs diagnostics", async (status, message) => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.stubGlobal("fetch", vi.fn(() => response({ detail: "raw backend detail" }, status)));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.queryByText("raw backend detail")).not.toBeInTheDocument();
    expect(consoleError).toHaveBeenCalledWith("Photoshoot Studio context request failed", expect.objectContaining({ status }));
  });
});
