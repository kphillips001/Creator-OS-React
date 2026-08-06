import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { navigationGroups } from "../../app/navigation/navigation";
import type { GenerationRecord } from "../generation-library/types";
import { PhotoshootPage } from "./PhotoshootPage";
import { CreativeDirectionPanel } from "./components/CreativeDirectionPanel";
import { SessionPlanPanel } from "./components/SessionPlanPanel";
import { PhotoshootTimeline } from "./components/PhotoshootTimeline";
import { CandidatePanel } from "./components/CandidatePanel";

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
  return render(<MemoryRouter initialEntries={["/content/photoshoot"]}><Routes><Route path="/content/photoshoot" element={<PhotoshootPage />} /><Route path="/library/generations" element={<LibraryDestination />} /><Route path="/library/photoshoots" element={<div>Photoshoot Gallery destination</div>} /></Routes></MemoryRouter>);
}

describe("PhotoshootPage Phase 1", () => {
  it("shows continuity drift as a non-blocking candidate warning", () => {
    render(<CandidatePanel busy={false} candidate={{ ...seed, image_id: "candidate" }} current={seed} continuityWarning="This generation may have drifted from the current photoshoot." onApprove={vi.fn()} onEdit={vi.fn()} onRegenerate={vi.fn()} onReject={vi.fn()} />);
    expect(screen.getByText("This generation may have drifted from the current photoshoot.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve Shot" })).toBeEnabled();
  });
  it("offers replacement for approved shots and marks invalidated continuity", () => {
    const onReplace = vi.fn();
    render(<PhotoshootTimeline busy={false} onReplace={onReplace} items={[
      { requestId: "seed-request", sequenceIndex: 1, shotNumber: 1, label: "Shot 1 (Seed)", isSeed: true, status: "approved", image: seed },
      { requestId: "shot-2", sequenceIndex: 2, shotNumber: 2, label: "Shot 2", isSeed: false, status: "approved", image: { ...seed, image_id: "approved-2" } },
      { requestId: "shot-3", sequenceIndex: 3, shotNumber: 3, label: "Shot 3", isSeed: false, status: "continuity_invalidated", image: null },
    ]} />);
    fireEvent.click(screen.getByRole("button", { name: "Select Shot 2" }));
    const replace = screen.getAllByRole("button", { name: "Replace Shot" });
    fireEvent.click(replace[0]!);
    expect(onReplace).toHaveBeenCalledWith("shot-2");
    expect(screen.getByText("Requires regeneration")).toBeInTheDocument();
  });

  it("clears removed-shot planning state and restores the preceding approved position", async () => {
    let replaced = false;
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: vi.fn() });
    const approved = (shot: number) => ({ ...seed, image_id: `approved-${shot}`, image_url: `/approved-${shot}.png` });
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/photoshoot/shot/replace") && init?.method === "POST") {
        replaced = true;
        return response({ success: true, replaced_request_id: "request-4", invalidated_request_ids: [], planning_shot: 4 });
      }
      if (url.includes("/photoshoot/status")) return response({ request: null, candidate: null });
      if (url.includes("/creative-director/context")) return response({
        session_id: "session-1", creative_mode: "premium", creator_guidance: replaced ? "" : "Stale Shot 4 guidance",
        workflow_stage: replaced ? "ready_for_next_shot" : "recommendation_ready", current_prompt: replaced ? "" : "Stale Shot 4 prompt",
        current_shot: replaced ? 3 : 4, planning_shot: replaced ? 4 : 5, target_shot_count: 5, remaining_shots: replaced ? 2 : 1,
        editorial_stage: "Finale", planner_explanation: replaced ? "Continue from approved Shot 3." : "Continue from approved Shot 4.",
        planning_mode: "frame_by_frame",
        recommendation_state: replaced
          ? { inspiration_ideas: [], selected_inspiration: "", direction_approved: false, recommendation: null }
          : { inspiration_ideas: ["Stale Shot 4 idea"], selected_inspiration: "Stale Shot 4 idea", direction_approved: false, recommendation: { title: "Stale Shot 4", creative_direction: "Removed direction" } },
      });
      if (url.includes("/creative-director/guidance")) return response({ creator_guidance: "" });
      const timeline = [
        { request_id: "request-1", sequence_index: 1, shot_number: 1, label: "Shot 1 (Seed)", is_seed: true, status: "approved", image: seed },
        { request_id: "request-2", sequence_index: 2, shot_number: 2, label: "Shot 2", is_seed: false, status: "approved", image: approved(2) },
        { request_id: "request-3", sequence_index: 3, shot_number: 3, label: "Shot 3", is_seed: false, status: "approved", image: approved(3) },
        replaced
          ? { request_id: "request-4", sequence_index: 4, shot_number: 4, label: "Shot 4", is_seed: false, status: "replacement_pending", image: null }
          : { request_id: "request-4", sequence_index: 4, shot_number: 4, label: "Shot 4", is_seed: false, status: "approved", image: approved(4) },
      ];
      return response({ creator_profile_exists: true, pending_photoshoot: seed, provider_list: [{ value: "flux", label: "Flux" }], active_session: { session_id: "session-1", title: "Photoshoot Studio", provider_id: "flux", target_shot_count: 5, creative_continuity: {} }, creative_mode: "premium", continuity_settings: { location: true, wardrobe: true, lighting: true, hairstyle: true, makeup: true, camera_style: true }, timeline_summary: timeline });
    }));
    renderPage();

    expect((await screen.findAllByText("Stale Shot 4 idea")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Select Shot 4" }));
    fireEvent.click(screen.getByRole("button", { name: "Replace Shot" }));

    expect(await screen.findByText("Planning Shot 4 of 5")).toBeInTheDocument();
    expect(screen.queryAllByText("Stale Shot 4 idea")).toHaveLength(0);
    expect(screen.queryByRole("heading", { name: "Stale Shot 4" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Prompt" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Prompt Editor")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Direct the Next Shot (Optional)")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Ask AI" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Direct Shot" })).toBeInTheDocument();
    expect(screen.getByText("Replacement in progress")).toBeInTheDocument();
  });
  it("defaults target length to Standard and supports a custom persisted value", () => {
    const onTargetShotCount = vi.fn();
    const props = {
      autoRunning: false, runtime: null, busy: false, directionApproved: false, disabled: false,
      hasRecommendation: false, onApprovePlan: vi.fn(), onFrameCount: vi.fn(), onGeneratePlan: vi.fn(),
      onPlanningMode: vi.fn(), onResumePlan: vi.fn(), planningMode: "frame_by_frame" as const,
      planFrameCount: 8, sessionPlan: [], sessionPlanApproved: false, sessionPlanIndex: 0,
    };
    const view = render(<SessionPlanPanel {...props} targetShotCount={10} onTargetShotCount={onTargetShotCount} />);
    expect(screen.getByLabelText("Target Photoshoot Length")).toHaveValue("10");
    fireEvent.change(screen.getByLabelText("Target Photoshoot Length"), { target: { value: "custom" } });
    fireEvent.change(screen.getByLabelText("Custom shot count"), { target: { value: "27" } });
    expect(onTargetShotCount).toHaveBeenCalledWith(27);
    view.rerender(<SessionPlanPanel {...props} targetShotCount={27} onTargetShotCount={onTargetShotCount} />);
    expect(screen.getByLabelText("Target Photoshoot Length")).toHaveValue("custom");
    expect(screen.getByLabelText("Custom shot count")).toHaveValue(27);
  });

  it("offers No limit first and emits the explicit zero target", () => {
    const onTargetShotCount = vi.fn();
    render(<SessionPlanPanel
      autoRunning={false} runtime={null} busy={false} directionApproved={false} disabled={false}
      hasRecommendation={false} onApprovePlan={vi.fn()} onFrameCount={vi.fn()} onGeneratePlan={vi.fn()}
      onPlanningMode={vi.fn()} onResumePlan={vi.fn()} planningMode="frame_by_frame" planFrameCount={8}
      sessionPlan={[]} sessionPlanApproved={false} sessionPlanIndex={0} targetShotCount={10}
      onTargetShotCount={onTargetShotCount}
    />);
    const selector = screen.getByLabelText("Target Photoshoot Length");
    expect(within(selector).getAllByRole("option")[0]).toHaveTextContent("0 (No limit)");
    fireEvent.change(selector, { target: { value: "0" } });
    expect(onTargetShotCount).toHaveBeenCalledWith(0);
  });

  it("renders open-ended progress without a zero denominator", () => {
    render(<CreativeDirectionPanel
      disabled={false} busy={false} guidance="" ideas={[]} selectedIdea="" directionApproved={false}
      recommendation={null} onGuidance={vi.fn()} onDirect={vi.fn()} onDirectSelected={vi.fn()}
      onAsk={vi.fn()} onDifferentIdeas={vi.fn()} onSelectIdea={vi.fn()} onGenerateSelected={vi.fn()}
      onChooseAnother={vi.fn()} creativeMode="premium"
      planningStatus={{ currentShot: 3, planningShot: 4, targetShotCount: 0, remainingShots: 0, editorialStage: "Open-ended", explanation: "Natural next shot." }}
    />);
    expect(screen.getByText("Open-ended Photoshoot")).toBeInTheDocument();
    expect(screen.getByText("3 approved")).toBeInTheDocument();
    expect(screen.getByText(/No target length selected/)).toBeInTheDocument();
    expect(screen.queryByText(/of 0/)).not.toBeInTheDocument();
    expect(screen.queryByText(/0 remaining/)).not.toBeInTheDocument();
  });

  it("selects one inspiration idea and renders the backend recommendation contract", () => {
    const select = vi.fn();
    const ideas = Array.from({ length: 10 }, (_, index) => `Next-shot idea ${index + 1}`);
    render(<CreativeDirectionPanel disabled={false} busy={false} guidance="" ideas={ideas} selectedIdea={ideas[1]!} directionApproved={false} recommendation={{ title: "Closer", creative_direction: "Move into a closer portrait", reasoning: "Advances the sequence", emotion: "Confident", camera_framing: "Medium close-up", lighting: "Warm window light", pose_composition: "Turn toward camera", continuity_notes: "Keep wardrobe" }} onGuidance={vi.fn()} onDirect={vi.fn()} onDirectSelected={vi.fn()} onAsk={vi.fn()} onDifferentIdeas={vi.fn()} onSelectIdea={select} onGenerateSelected={vi.fn()} onChooseAnother={vi.fn()} />);
    expect(screen.getAllByRole("radio")).toHaveLength(10);
    expect(screen.getByRole("radio", { name: /Next-shot idea 2/ })).toBeChecked();
    fireEvent.click(screen.getByRole("radio", { name: /^1\. Next-shot idea 1$/ }));
    expect(select).toHaveBeenCalledWith("Next-shot idea 1");
    expect(screen.getByRole("heading", { name: "Closer" })).toBeInTheDocument();
    for (const value of ["Move into a closer portrait", "Advances the sequence", "Confident", "Medium close-up", "Warm window light", "Turn toward camera", "Keep wardrobe"]) expect(screen.getByText(value)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate Selected Shot" })).toBeEnabled();
    expect(screen.getAllByRole("button", { name: "Direct Shot" }).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("button", { name: "Different Ideas" })).toBeEnabled();
    expect(screen.getByText("View Creative Direction")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Choose Another Idea" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Ask for Different Ideas" })).toBeEnabled();
  });

  it("keeps reviewed AI ideas available without exposing the persisted prompt", async () => {
    const ideas = ["Closer window portrait", "Seated profile"];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/photoshoot/status")) return response({ request: null, candidate: null });
      if (url.includes("/creative-director/context")) return response({
        session_id: "session-1", creative_mode: "premium", creator_guidance: "",
        workflow_stage: "inspiration_selected", current_prompt: "Existing manual prompt",
        recommendation_state: { inspiration_ideas: ideas, selected_inspiration: ideas[0], direction_approved: false, recommendation: null },
      });
      if (url.includes("/creative-director/guidance")) return response({ creator_guidance: "" });
      return response({ creator_profile_exists: true, pending_photoshoot: seed, provider_list: [{ value: "flux", label: "Flux" }], active_session: { session_id: "session-1", title: "Photoshoot Studio", provider_id: "flux", creative_continuity: {} }, creative_mode: "premium", continuity_settings: { location: true, wardrobe: true, lighting: true, hairstyle: true, makeup: true, camera_style: true }, timeline_summary: [{ request_id: "request-1", sequence_index: 1, shot_number: 1, label: "Shot 1 (Seed)", is_seed: true, image: seed }] });
    }));
    renderPage();
    expect(await screen.findByRole("radio", { name: /Closer window portrait/ })).toBeChecked();
    const suggestionActions = screen.getByText("Selected Direction").parentElement!;
    fireEvent.click(within(suggestionActions).getByRole("button", { name: "Direct Shot" }));
    expect(screen.queryByRole("heading", { name: "Prompt" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Prompt Editor")).not.toBeInTheDocument();
    expect(screen.queryByText("Existing manual prompt")).not.toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Closer window portrait/ })).toBeChecked();
    expect(screen.getByText("Seated profile")).toBeInTheDocument();
  });

  it("does not offer another Frame-by-Frame shot after the target is reached", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/photoshoot/status")) return response({ request: null, candidate: null });
      if (url.includes("/creative-director/context")) return response({ session_id: "session-1", creative_mode: "premium", creator_guidance: "", workflow_stage: "ready_for_next_shot", current_prompt: "", current_shot: 5, planning_shot: 6, target_shot_count: 5, remaining_shots: 0, editorial_stage: "Finale", planner_explanation: "Target reached.", planning_mode: "frame_by_frame", recommendation_state: { inspiration_ideas: [], selected_inspiration: "", direction_approved: false, recommendation: null } });
      if (url.includes("/creative-director/guidance")) return response({ creator_guidance: "" });
      return response({ creator_profile_exists: true, pending_photoshoot: seed, provider_list: [{ value: "flux", label: "Flux" }], active_session: { session_id: "session-1", title: "Photoshoot Studio", provider_id: "flux", creative_continuity: {} }, creative_mode: "premium", continuity_settings: { location: true, wardrobe: true, lighting: true, hairstyle: true, makeup: true, camera_style: true }, timeline_summary: [{ request_id: "request-1", sequence_index: 1, shot_number: 1, label: "Shot 1 (Seed)", is_seed: true, image: seed }] });
    }));
    renderPage();
    expect(await screen.findByText("Target Photoshoot Length Reached")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask AI" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Direct Shot" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generate Shot" })).not.toBeInTheDocument();
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
    for (const heading of ["Photoshoot Timeline", "Photoshoot Settings", "AI Creative Director", "Generation"]) {
      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    }
    expect(screen.queryByRole("heading", { name: "Prompt" })).not.toBeInTheDocument();
    expect(screen.queryByText("Manual prompt")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Prompt Editor")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate Shot" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Ask AI" })).toBeEnabled();
    expect(screen.getByText("Renderer")).toBeInTheDocument();
    expect(screen.getByText("Flux")).toBeInTheDocument();
    expect(screen.getAllByRole("combobox")).toEqual([screen.getByLabelText("Target Photoshoot Length")]);
    expect(screen.getByRole("radio", { name: "Premium" })).toBeChecked();
    expect(screen.queryByText("Continuity Locks")).not.toBeInTheDocument();
    for (const label of ["Keep location", "Keep wardrobe", "Keep lighting", "Keep hairstyle", "Keep makeup", "Keep camera style"]) expect(screen.queryByText(label)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Direct the Next Shot (Optional)")).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Describe exactly what should happen next/)).toBeInTheDocument();
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
    expect(screen.queryByLabelText("Prompt Editor")).not.toBeInTheDocument();
    expect(screen.queryByText("Recovered canonical prompt")).not.toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Explicit" })).toBeChecked();
    expect(screen.getByText("View Creative Direction")).toBeInTheDocument();
  });

  it("automatically develops, approves, plans, populates the prompt, and submits the selected shot", async () => {
    let statusCalls = 0;
    const calls: string[] = [];
    const candidate = { ...seed, image_id: "candidate-auto", image_url: "/candidate-auto.png", status: "photoshoot_session" };
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/photoshoot/status")) {
        statusCalls += 1;
        return response(statusCalls === 1
          ? { request: null, candidate: null }
          : { request: { request_id: "shot-auto", status: "awaiting_review", prompt: "Final canonical prompt", provider_id: "flux", generation_job_id: "job-auto", failure: null }, candidate });
      }
      if (url.includes("/creative-director/context")) return response({
        session_id: "session-1", creative_mode: "premium", creator_guidance: "", workflow_stage: "inspiration_selected",
        current_prompt: "", recommendation_state: { inspiration_ideas: ["Closer window portrait"], selected_inspiration: "Closer window portrait", direction_approved: false, recommendation: null },
      });
      if (url.endsWith("/creative-director/recommendation")) {
        calls.push("develop");
        return response({ title: "Window turn", creative_direction: "Turn toward the window", continuity_notes: "Keep wardrobe" });
      }
      if (url.endsWith("/creative-director/approve")) {
        calls.push("approve-and-plan");
        return response({ prompt: "Final canonical prompt", workflow_stage: "direction_approved" });
      }
      if (url.endsWith("/photoshoot/generate") && init?.method === "POST") {
        calls.push("generate");
        return response({ request_id: "shot-auto", status: "generating" });
      }
      if (url.includes("/creative-director/guidance")) return response({ creator_guidance: "" });
      return response({ creator_profile_exists: true, pending_photoshoot: seed, provider_list: [{ value: "flux", label: "Flux" }], active_session: { session_id: "session-1", title: "Photoshoot Studio", provider_id: "flux", creative_continuity: {} }, creative_mode: "premium", continuity_settings: { location: true, wardrobe: true, lighting: true, hairstyle: true, makeup: true, camera_style: true }, timeline_summary: [{ request_id: "request-1", sequence_index: 1, shot_number: 1, label: "Shot 1 (Seed)", is_seed: true, image: seed }] });
    }));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Generate Selected Shot" }));
    expect(await screen.findByLabelText("Selected shot progress")).toBeInTheDocument();
    expect((await screen.findAllByText("Rendering complete")).length).toBeGreaterThan(0);
    expect(screen.queryByLabelText("Prompt Editor")).not.toBeInTheDocument();
    expect(screen.queryByText("Final canonical prompt")).not.toBeInTheDocument();
    expect(screen.getByText("View Creative Direction")).toBeInTheDocument();
    expect(calls).toEqual(["develop", "approve-and-plan", "generate"]);
  });

  it("directs a shot from operator text without requesting AI inspiration", async () => {
    let statusCalls = 0;
    const calls: string[] = [];
    const requestBodies: Record<string, unknown>[] = [];
    const candidate = { ...seed, image_id: "candidate-direct", image_url: "/candidate-direct.png", status: "photoshoot_session" };
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/photoshoot/status")) {
        statusCalls += 1;
        return response(statusCalls === 1
          ? { request: null, candidate: null }
          : { request: { request_id: "shot-direct", status: "awaiting_review", prompt: "Directed canonical prompt", provider_id: "flux", generation_job_id: "job-direct", failure: null }, candidate });
      }
      if (url.includes("/creative-director/context")) return response({
        session_id: "session-1", creative_mode: "premium", creator_guidance: "", workflow_stage: "ready_for_direction",
        current_prompt: "", recommendation_state: { inspiration_ideas: [], selected_inspiration: "", direction_approved: false, recommendation: null },
      });
      if (url.endsWith("/creative-director/direct-recommendation")) {
        calls.push("direct-enhancement");
        requestBodies.push(JSON.parse(String(init?.body)));
        return response({ title: "Directed shot", creative_direction: "Lift the shirt naturally", continuity_notes: "Keep continuity" });
      }
      if (url.endsWith("/creative-director/approve")) {
        calls.push("approve-and-plan");
        return response({ prompt: "Directed canonical prompt", workflow_stage: "direction_approved" });
      }
      if (url.endsWith("/photoshoot/generate") && init?.method === "POST") {
        calls.push("generate");
        requestBodies.push(JSON.parse(String(init.body)));
        return response({ request_id: "shot-direct", status: "generating" });
      }
      if (url.includes("/creative-director/inspiration")) {
        calls.push("unexpected-inspiration");
        return response({ ideas: [] });
      }
      if (url.includes("/creative-director/guidance")) return response({ creator_guidance: "" });
      return response({ creator_profile_exists: true, pending_photoshoot: seed, provider_list: [{ value: "flux", label: "Flux" }], active_session: { session_id: "session-1", title: "Photoshoot Studio", provider_id: "flux", creative_continuity: {} }, creative_mode: "premium", continuity_settings: { location: true, wardrobe: true, lighting: true, hairstyle: true, makeup: true, camera_style: true }, timeline_summary: [{ request_id: "request-1", sequence_index: 1, shot_number: 1, label: "Shot 1 (Seed)", is_seed: true, image: seed }] });
    }));
    renderPage();
    const direct = await screen.findByRole("button", { name: "Direct Shot" });
    expect(direct).toBeDisabled();
    const direction = screen.getByLabelText("Direct the Next Shot (Optional)");
    expect(direction).toHaveAttribute("placeholder", expect.stringContaining("Have her lift her shirt."));
    fireEvent.change(direction, { target: { value: "  Have her lift her shirt.  " } });
    expect(direct).toBeEnabled();
    fireEvent.click(direct);
    expect(await screen.findByLabelText("Selected shot progress")).toBeInTheDocument();
    expect((await screen.findAllByText("Rendering complete")).length).toBeGreaterThan(0);
    expect(calls).toEqual(["direct-enhancement", "approve-and-plan", "generate"]);
    expect(requestBodies[0]).toMatchObject({ operator_direction: "Have her lift her shirt." });
    expect(requestBodies[1]).toMatchObject({ creative_hint: "Have her lift her shirt." });
    expect(screen.getByText("View Creative Direction")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Candidate Review" })).toBeInTheDocument();
  });

  it("recovers the persisted canonical prompt when the approve response does not resolve", async () => {
    let contextCalls = 0;
    let statusCalls = 0;
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/photoshoot/status")) {
        statusCalls += 1;
        return response(statusCalls === 1
          ? { request: null, candidate: null }
          : { request: { request_id: "shot-recovered", status: "generating", prompt: "Recovered canonical prompt", provider_id: "flux", generation_job_id: "job-recovered", failure: null }, candidate: null });
      }
      if (url.includes("/creative-director/context")) {
        contextCalls += 1;
        return response(contextCalls === 1
          ? { session_id: "session-1", creative_mode: "premium", creator_guidance: "", workflow_stage: "inspiration_selected", current_prompt: "", recommendation_state: { inspiration_ideas: ["Window portrait"], selected_inspiration: "Window portrait", direction_approved: false, recommendation: null } }
          : { session_id: "session-1", creative_mode: "premium", creator_guidance: "", workflow_stage: "direction_approved", current_prompt: "Recovered canonical prompt", recommendation_state: { inspiration_ideas: ["Window portrait"], selected_inspiration: "Window portrait", direction_approved: true, recommendation: { title: "Window turn", creative_direction: "Turn toward the window" } } });
      }
      if (url.endsWith("/creative-director/recommendation")) {
        calls.push("develop");
        return response({ title: "Window turn", creative_direction: "Turn toward the window" });
      }
      if (url.endsWith("/creative-director/approve")) {
        calls.push("approve");
        return new Promise<Response>(() => undefined);
      }
      if (url.endsWith("/photoshoot/generate") && init?.method === "POST") {
        calls.push("generate");
        return response({ request_id: "shot-recovered", status: "generating" });
      }
      if (url.includes("/creative-director/guidance")) return response({ creator_guidance: "" });
      return response({ creator_profile_exists: true, pending_photoshoot: seed, provider_list: [{ value: "flux", label: "Flux" }], active_session: { session_id: "session-1", title: "Photoshoot Studio", provider_id: "flux", creative_continuity: {} }, creative_mode: "premium", continuity_settings: { location: true, wardrobe: true, lighting: true, hairstyle: true, makeup: true, camera_style: true }, timeline_summary: [{ request_id: "request-1", sequence_index: 1, shot_number: 1, label: "Shot 1 (Seed)", is_seed: true, image: seed }] });
    }));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Generate Selected Shot" }));
    await waitFor(() => expect(calls).toEqual(["develop", "approve", "generate"]), { timeout: 2_000 });
    expect(screen.queryByLabelText("Prompt Editor")).not.toBeInTheDocument();
    expect(screen.queryByText("Recovered canonical prompt")).not.toBeInTheDocument();
    expect(contextCalls).toBeGreaterThanOrEqual(2);
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

  it("approves a candidate, refreshes planning progress, and waits for the operator", async () => {
    const approved = { ...seed, image_id: "approved-2", image_url: "/approved-2.png", status: "photoshoot_session" };
    const candidate = { ...seed, image_id: "candidate-2", image_url: "/candidate-2.png", status: "photoshoot_session" };
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
        return response({ session_id: "session-1", creative_mode: "premium", creator_guidance: "", workflow_stage: "ready_for_next_shot", current_prompt: "", current_shot: 2, planning_shot: 3, target_shot_count: 10, remaining_shots: 8, editorial_stage: "Beginning", planner_explanation: "Planning Shot 3 from the approved continuity reference.", recommendation_state: { inspiration_ideas: [], selected_inspiration: "", direction_approved: false, recommendation: {} } });
      }
      if (url.endsWith("/photoshoot/candidate/approve")) return response({ success: true, status: "approved" });
      if (url.includes("/creative-director/guidance")) return response({ creator_guidance: "" });
      const timeline = contextCalls > 0 ? [{ request_id: "request-1", sequence_index: 1, shot_number: 1, label: "Shot 1 (Seed)", is_seed: true, image: seed }, { request_id: "request-2", sequence_index: 2, shot_number: 2, label: "Shot 2", is_seed: false, image: approved }] : [{ request_id: "request-1", sequence_index: 1, shot_number: 1, label: "Shot 1 (Seed)", is_seed: true, image: seed }];
      return response({ creator_profile_exists: true, pending_photoshoot: seed, provider_list: [{ value: "flux", label: "Flux" }], active_session: { session_id: "session-1", title: "Photoshoot Studio", provider_id: "flux", creative_continuity: { workflow_stage: "ready_for_next_shot" } }, creative_mode: "premium", continuity_settings: { location: true, wardrobe: true, lighting: true, hairstyle: true, makeup: true, camera_style: true }, timeline_summary: timeline });
    });
    vi.stubGlobal("fetch", fetch);
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Approve Shot" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Shot Approved");
    expect(screen.getByRole("status")).toHaveTextContent("Updating Photoshoot...");
    expect(await screen.findByText("Planning Shot 3 of 10")).toBeInTheDocument();
    expect(screen.getByText("Ready for Next Shot")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask AI" })).toBeEnabled();
    expect(screen.getByText("Shot 2")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Candidate Review" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Finish Photoshoot/ })).toBeEnabled();
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/photoshoot/candidate/approve"), expect.objectContaining({ method: "POST" }));
    expect(fetch).not.toHaveBeenCalledWith(expect.stringContaining("/creative-director/inspiration"), expect.anything());
  });

  it.each([
    { source: "AI", ideas: ["Closer portrait", "Window profile"], selected: "Closer portrait", guidance: "" },
    { source: "manual", ideas: [] as string[], selected: "", guidance: "Turn toward the window" },
  ])("rejects an unapproved $source candidate without leaving Planning Shot 5", async ({ ideas, selected, guidance }) => {
    let rejected = false;
    const candidate = { ...seed, image_id: "candidate-5", image_url: "/candidate-5.png", status: "photoshoot_session" };
    const fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/photoshoot/candidate/reject") && init?.method === "POST") {
        rejected = true;
        return response({ success: true, message: "Candidate rejected." });
      }
      if (url.includes("/photoshoot/status")) return response(rejected
        ? { request: null, candidate: null }
        : { request: { request_id: "request-5", status: "awaiting_review", prompt: "Candidate prompt" }, candidate });
      if (url.includes("/creative-director/context")) return response({
        session_id: "session-1", creative_mode: "premium", creator_guidance: guidance,
        workflow_stage: rejected ? "ready_for_next_shot" : "direction_approved", current_prompt: "Candidate prompt",
        current_shot: 4, planning_shot: 5, target_shot_count: 5, remaining_shots: 1,
        editorial_stage: "Hero / Closing", planner_explanation: "Continue from approved Shot 4.",
        planning_mode: "frame_by_frame",
        recommendation_state: { inspiration_ideas: ideas, selected_inspiration: selected, direction_approved: !rejected, recommendation: selected ? { title: "Closer", creative_direction: selected } : null },
      });
      if (url.includes("/creative-director/guidance")) return response({ creator_guidance: guidance });
      return response({ creator_profile_exists: true, pending_photoshoot: seed, provider_list: [{ value: "flux", label: "Flux" }], active_session: { session_id: "session-1", title: "Photoshoot Studio", provider_id: "flux", creative_continuity: {} }, creative_mode: "premium", continuity_settings: { location: true, wardrobe: true, lighting: true, hairstyle: true, makeup: true, camera_style: true }, timeline_summary: [{ request_id: "request-1", sequence_index: 1, shot_number: 1, label: "Shot 1 (Seed)", is_seed: true, image: seed }, { request_id: "request-4", sequence_index: 4, shot_number: 4, label: "Shot 4", is_seed: false, image: { ...seed, image_id: "approved-4" } }] });
    });
    vi.stubGlobal("fetch", fetch);
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Reject Shot" }));

    await waitFor(() => expect(screen.queryByRole("heading", { name: "Candidate Review" })).not.toBeInTheDocument());
    expect(screen.getByText("Planning Shot 5 of 5")).toBeInTheDocument();
    expect(screen.queryByText("Target Photoshoot Length Reached")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask AI" })).toBeEnabled();
    expect(screen.queryByLabelText("Prompt Editor")).not.toBeInTheDocument();
    expect(screen.queryByText("Candidate prompt")).not.toBeInTheDocument();
    if (ideas.length) {
      expect(screen.getByRole("radio", { name: /Closer portrait/ })).toBeChecked();
      expect(screen.getByRole("radio", { name: /Window profile/ })).toBeEnabled();
      expect(screen.getByRole("button", { name: "Different Ideas" })).toBeEnabled();
      expect(screen.getByRole("button", { name: "Generate Selected Shot" })).toBeEnabled();
      expect(screen.getAllByRole("button", { name: "Direct Shot" }).some((button) => !button.hasAttribute("disabled"))).toBe(true);
    } else {
      expect(screen.getByLabelText("Direct the Next Shot (Optional)")).toHaveValue(guidance);
      expect(screen.getByRole("button", { name: "Direct Shot" })).toBeEnabled();
    }
    expect(fetch).not.toHaveBeenCalledWith(expect.stringContaining("/creative-director/inspiration"), expect.anything());
  });

  it("finishes immediately and navigates to Photoshoot Gallery", async () => {
    const approved = { ...seed, image_id: "approved-2", image_url: "/approved-2.png", status: "photoshoot_session" };
    let finished = false;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/photoshoot/status")) return response({ request: null, candidate: null });
      if (url.includes("/creative-director/context")) return response({ session_id: "session-1", creative_mode: "safe", creator_guidance: "", workflow_stage: "ready_for_next_shot", current_prompt: "", recommendation_state: { inspiration_ideas: [], selected_inspiration: "", direction_approved: false, recommendation: {} } });
      if (url.endsWith("/photoshoot/finish")) {
        finished = true;
        return response({ session_id: "session-1", status: "archived", already_confirmed: false, photoshoot_decision: "APPROVED", photoshoot_decided_at: "2026-07-21T00:00:00Z", selected_image_ids: ["approved-2"], photoshoot_created: true, photoshoot_deliverable_id: "set-1", image_asset_generation_ids: [] });
      }
      if (finished && url.endsWith("/photoshoot/context")) return response({ creator_profile_exists: true, pending_photoshoot: null, provider_list: [], active_session: null, creative_mode: null, continuity_settings: null, timeline_summary: [] });
      return response({ creator_profile_exists: true, pending_photoshoot: seed, provider_list: [{ value: "flux", label: "Flux" }], active_session: { session_id: "session-1", title: "Photoshoot Studio", provider_id: "flux", creative_continuity: { workflow_stage: "ready_for_next_shot" } }, creative_mode: "safe", continuity_settings: { location: true, wardrobe: true, lighting: true, hairstyle: true, makeup: true, camera_style: true }, timeline_summary: [{ request_id: "request-1", sequence_index: 1, shot_number: 1, label: "Shot 1 (Seed)", is_seed: true, image: seed }, { request_id: "request-2", sequence_index: 2, shot_number: 2, label: "Shot 2", is_seed: false, image: approved }] });
    }));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Finish Photoshoot/ }));
    expect(await screen.findByText("Photoshoot Gallery destination")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/photoshoot/finish"), expect.objectContaining({ method: "POST" }));
    const calls = vi.mocked(fetch).mock.calls.map(([input]) => String(input));
    expect(calls.lastIndexOf("/api/v1/photoshoot/context")).toBeGreaterThan(calls.findIndex((url) => url.endsWith("/photoshoot/finish")));
    expect(fetch).not.toHaveBeenCalledWith(expect.stringContaining("/curation/confirm"), expect.anything());
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
